"""생성형 AI 호출 (Claude · OpenAI · Gemini). 키는 환경 변수에서만 읽고, 코드에 넣지 않는다.

우선순위: ANTHROPIC_API_KEY → OPENAI_API_KEY → GEMINI_API_KEY (먼저 있는 키 하나만 사용).
교육용 게이트웨이처럼 중계 주소를 쓰면 ANTHROPIC_BASE_URL / OPENAI_BASE_URL 에 넣는다.
외부 패키지 없이 표준 라이브러리(urllib)로 호출한다.
"""
import http.client
import json
import os
import re
import urllib.error
import urllib.request

from common import ApiError

TIMEOUT = 25  # 초. Vercel 함수 제한 시간(vercel.json maxDuration) 안에서 끝나도록


def _key(name: str) -> str:
    """키 앞뒤 공백·줄바꿈·따옴표 제거 (붙여넣기 실수로 인증 실패하는 것 방지)."""
    return os.environ.get(name, "").strip().strip('"').strip("'").strip()


def provider() -> str | None:
    if _key("ANTHROPIC_API_KEY"):
        return "claude"
    if _key("OPENAI_API_KEY"):
        return "openai"
    if _key("GEMINI_API_KEY"):
        return "gemini"
    return None


def model_name() -> str:
    p = provider()
    if os.environ.get("AI_MODEL", "").strip():
        return os.environ["AI_MODEL"].strip()
    return {"claude": "claude-haiku-4-5-20251001", "openai": "gpt-4o-mini", "gemini": "gemini-flash-latest"}.get(p, "-")


def base_url(p: str | None = None) -> str:
    """호출 주소. 끝에 /v1 을 붙여 넣어도, 빼고 넣어도 동작하도록 /v1 은 떼어 둔다(Gemini 제외)."""
    p = p or provider()
    env, default = {"claude": ("ANTHROPIC_BASE_URL", "https://api.anthropic.com"), "openai": ("OPENAI_BASE_URL", "https://api.openai.com"),
                    "gemini": ("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")}.get(p, ("", ""))
    base = (os.environ.get(env, "") if env else "").strip().rstrip("/") or default
    return base[:-3] if p != "gemini" and base.endswith("/v1") else base


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "ignore")
        print(f"[ai] HTTP {e.code}: {detail}")
        if e.code in (401, 403):
            raise ApiError(502, "ai_auth", f"AI 서비스 인증에 실패했습니다(HTTP {e.code}). 관리자가 API 키 설정을 확인해야 합니다.")
        if e.code == 404:
            raise ApiError(502, "ai_model", "AI 모델 이름을 찾을 수 없습니다. 관리자가 AI_MODEL 환경 변수를 확인해야 합니다.")
        if e.code == 429:
            raise ApiError(503, "ai_quota", "AI 사용량 한도에 도달했습니다. 잠시 후 다시 시도하세요.")
        raise ApiError(502, "ai_error" if e.code != 400 else "ai_bad_request", f"AI 서비스 오류({e.code})가 발생했습니다. 잠시 후 다시 시도하세요.")
    except TimeoutError as e:
        print("[ai] timeout:", repr(e))
        raise ApiError(504, "ai_timeout", "AI 응답이 지연되고 있습니다. 잠시 후 다시 시도하세요.")
    except (urllib.error.URLError, OSError, http.client.HTTPException, json.JSONDecodeError) as e:
        print("[ai] network:", repr(e))
        if "timed out" in str(e):
            raise ApiError(504, "ai_timeout", "AI 응답이 지연되고 있습니다. 잠시 후 다시 시도하세요.")
        raise ApiError(502, "ai_unreachable", "AI 서비스에 연결하지 못했습니다. 잠시 후 다시 시도하세요.")


def generate_json(system: str, user: str, max_tokens: int = 1500, file: dict | list | None = None) -> dict:
    """AI에게 JSON 하나를 받아 dict로 돌려준다.

    file: {"media_type": "image/png|image/jpeg|application/pdf", "data": base64 문자열} 또는 그 목록 — 서류 판독용 (선택)
    """
    files = [f for f in (file if isinstance(file, list) else [file]) if f]
    p = provider()
    if not p:
        raise ApiError(503, "ai_not_configured", "AI 기능이 아직 설정되지 않았습니다. (관리자: 환경 변수에 AI API 키 등록 필요)")
    if p == "claude":
        res = _post(f"{base_url(p)}/v1/messages",
                    {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
                    {"model": model_name(), "max_tokens": max_tokens, "system": system,
                     "messages": [{"role": "user", "content": _claude_content(user, files)}]})
        out = "".join(b.get("text", "") for b in res.get("content", []))
    elif p == "openai":
        body = {"model": model_name(), "messages": [{"role": "system", "content": system}, {"role": "user", "content": _openai_content(user, files)}],
                "response_format": {"type": "json_object"}}
        # 최신 모델(gpt-5·o 계열)은 max_completion_tokens 만 받고 temperature 조절을 막는다
        body.update({"max_completion_tokens": max_tokens} if _openai_new(model_name()) else {"max_tokens": max_tokens, "temperature": 0.2})
        url, auth = f"{base_url(p)}/v1/chat/completions", {"authorization": f"Bearer {_key('OPENAI_API_KEY')}"}
        try:
            res = _post(url, auth, body)
        except ApiError as e:
            if e.code != "ai_bad_request":
                raise
            body.pop("response_format", None)  # 중계 서버가 JSON 응답 옵션을 모르면 옵션 없이 한 번 더 (지시문으로 JSON 요청)
            res = _post(url, auth, body)
        choices = res.get("choices") or []
        msg = (choices[0].get("message") or {}) if choices else {}
        c = msg.get("content")
        out = c if isinstance(c, str) else "".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
    else:
        res = _post(f"{base_url(p)}/v1beta/models/{model_name()}:generateContent",
                    {"x-goog-api-key": _key("GEMINI_API_KEY")},
                    {"systemInstruction": {"parts": [{"text": system}]},
                     "contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": f["media_type"], "data": f["data"]}} for f in files]
                                   + [{"text": user}]}],
                     "generationConfig": {"maxOutputTokens": max_tokens, "responseMimeType": "application/json", "temperature": 0.2}})
        cands = res.get("candidates") or []
        out = "".join(p.get("text", "") for p in ((cands[0].get("content") or {}).get("parts") or [])) if cands else ""
    return parse_json(out)


def _claude_content(user: str, files: list):
    if not files:
        return user
    return [{"type": "document" if f["media_type"] == "application/pdf" else "image",
             "source": {"type": "base64", "media_type": f["media_type"], "data": f["data"]}} for f in files] + [{"type": "text", "text": user}]


def _openai_new(model: str) -> bool:
    m = (model or "").lower().split("/")[-1]
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def _openai_content(user: str, files: list):
    """OpenAI Chat Completions 형식: 이미지는 image_url(data URL), PDF는 file(file_data)."""
    if not files:
        return user
    parts = []
    for i, f in enumerate(files):
        url = f"data:{f['media_type']};base64,{f['data']}"
        parts.append({"type": "file", "file": {"filename": f"document{i + 1}.pdf", "file_data": url}} if f["media_type"] == "application/pdf"
                     else {"type": "image_url", "image_url": {"url": url}})
    return parts + [{"type": "text", "text": user}]


def parse_json(out: str) -> dict:
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        raise ApiError(502, "ai_bad_output", "AI 응답을 해석하지 못했습니다. 다시 시도하세요.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        raise ApiError(502, "ai_bad_output", "AI 응답을 해석하지 못했습니다. 다시 시도하세요.")
