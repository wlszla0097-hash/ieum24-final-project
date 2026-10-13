"""생성형 AI 호출 (Claude 또는 Gemini). 키는 환경 변수에서만 읽고, 코드에 넣지 않는다.

ANTHROPIC_API_KEY 가 있으면 Claude, 없고 GEMINI_API_KEY 가 있으면 Gemini 를 사용.
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
    if _key("GEMINI_API_KEY"):
        return "gemini"
    return None


def model_name() -> str:
    p = provider()
    if os.environ.get("AI_MODEL"):
        return os.environ["AI_MODEL"]
    return {"claude": "claude-haiku-4-5-20251001", "gemini": "gemini-flash-latest"}.get(p, "-")


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
        raise ApiError(502, "ai_error", f"AI 서비스 오류({e.code})가 발생했습니다. 잠시 후 다시 시도하세요.")
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
        base = (os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").strip().rstrip("/")
        base = base[:-3] if base.endswith("/v1") else base  # 주소 끝에 /v1을 붙여 넣어도 동작하도록
        res = _post(f"{base}/v1/messages",
                    {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
                    {"model": model_name(), "max_tokens": max_tokens, "system": system,
                     "messages": [{"role": "user", "content": _claude_content(user, files)}]})
        out = "".join(b.get("text", "") for b in res.get("content", []))
    else:
        base = (os.environ.get("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com").strip().rstrip("/")
        res = _post(f"{base}/v1beta/models/{model_name()}:generateContent",
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


def parse_json(out: str) -> dict:
    m = re.search(r"\{.*\}", out or "", re.S)
    if not m:
        raise ApiError(502, "ai_bad_output", "AI 응답을 해석하지 못했습니다. 다시 시도하세요.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        raise ApiError(502, "ai_bad_output", "AI 응답을 해석하지 못했습니다. 다시 시도하세요.")
