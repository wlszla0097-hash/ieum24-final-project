"""시연 데이터 저장소 — 구직자 이력·지원·공고·근로계약서·급여명세서·신청 건을 JSON으로 저장한다.

- 저장하는 것: 화면에서 입력한 합성(가상) 데이터의 JSON. 서류는 그림 파일이 아니라 값(JSON)으로 저장하고, 화면에서 다시 그린다.
  예외: 근로자 서명·인장 이미지(작게 줄인 PNG)만 계약서 JSON 안에 들어간다.
- 저장하지 않는 것: 이체확인증·외부 서류 원본 파일(판독값만 기록), 실제 개인정보(입력 금지 안내).
- 모든 묶음은 마지막 저장 후 30일이 지나면 자동 삭제된다(EXPIRE). [시연 데이터 초기화]로 바로 지울 수도 있다.

배포: Vercel → Storage → Upstash for Redis 를 연결하면 KV_REST_API_URL / KV_REST_API_TOKEN 이 자동으로 들어온다.
로컬 개발: 저장소가 없으면 서버 메모리에 저장(서버를 끄면 사라짐).
배포 환경(VERCEL=1)에서 저장소가 없으면 "off" — 화면은 각 브라우저(localStorage)에 저장한다.
"""
import json
import os
import urllib.request

from common import ApiError

PREFIX = "ieum24:demo:"
COLLECTIONS = ("seekers", "companies", "applications", "postings", "contracts", "payslips", "cases")
TTL = 30 * 24 * 3600  # 30일
MAX_VALUE = {"contracts": 200_000}  # 서명 이미지가 들어가는 계약서만 크게
MAX_DEFAULT = 40_000
MAX_ITEMS = 300  # 묶음당 최대 건수 (공개 시연 남용 방지)

_mem: dict[str, dict[str, str]] = {}


def _conf():
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return (url.rstrip("/"), token) if url and token else (None, None)


def mode() -> str:
    url, _ = _conf()
    if url:
        return "upstash"
    return "off" if os.environ.get("VERCEL") else "memory"


def _post(path: str, payload):
    url, token = _conf()
    req = urllib.request.Request(url + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:  # 저장소 장애
        print("[store error]", repr(e))
        raise ApiError(503, "store_error", "저장소에 연결하지 못했습니다. 잠시 후 다시 시도하세요.")


def _pipe(*cmds):
    """여러 명령을 한 번에 (Upstash REST pipeline). 메모리 모드는 하나씩 처리."""
    m = mode()
    if m == "off":
        raise ApiError(503, "store_off", "서버 저장소가 연결되지 않았습니다. 이 브라우저에만 저장합니다.")
    if m == "memory":
        return [_mem_cmd(*c) for c in cmds]
    return [x.get("result") for x in _post("/pipeline", [list(c) for c in cmds])]


def _mem_cmd(op, key, *rest):
    h = _mem.setdefault(key, {})
    if op == "HSET":
        h[rest[0]] = rest[1]
        return 1
    if op == "HGETALL":
        out = []
        for k, v in h.items():
            out += [k, v]
        return out
    if op == "HGET":
        return h.get(rest[0])
    if op == "HDEL":
        return 1 if h.pop(rest[0], None) is not None else 0
    if op == "HLEN":
        return len(h)
    if op in ("DEL", "EXPIRE"):
        if op == "DEL":
            _mem.pop(key, None)
        return 1
    raise ValueError(op)


def _key(col: str) -> str:
    if col not in COLLECTIONS:
        raise ApiError(400, "invalid_input", "알 수 없는 저장 묶음입니다.")
    return PREFIX + col


def _clean_id(item_id) -> str:
    s = str(item_id or "").strip()
    if not s or len(s) > 80 or any(c in s for c in "\r\n\t"):
        raise ApiError(400, "invalid_input", "저장 id가 올바르지 않습니다.")
    return s


def list_items(col: str) -> list[dict]:
    raw = _pipe(("HGETALL", _key(col)))[0] or []
    out = []
    for i in range(0, len(raw) - 1, 2):
        try:
            v = json.loads(raw[i + 1])
            if isinstance(v, dict):
                out.append(v)
        except (TypeError, json.JSONDecodeError):
            continue
    return out


def get(col: str, item_id: str) -> dict | None:
    v = _pipe(("HGET", _key(col), _clean_id(item_id)))[0]
    return json.loads(v) if v else None


def put(col: str, item_id: str, value: dict) -> dict:
    if not isinstance(value, dict):
        raise ApiError(400, "invalid_input", "저장할 값은 JSON 객체여야 합니다.")
    key, iid = _key(col), _clean_id(item_id)
    value = {**value, "id": iid}
    raw = json.dumps(value, ensure_ascii=False)
    if len(raw.encode()) > MAX_VALUE.get(col, MAX_DEFAULT):
        raise ApiError(413, "too_large", "저장할 내용이 너무 큽니다. (서명·인장 이미지는 작게 줄여 저장합니다)")
    count, exists = _pipe(("HLEN", key), ("HGET", key, iid))
    if not exists and (count or 0) >= MAX_ITEMS:
        raise ApiError(429, "store_full", "시연 저장 건수가 가득 찼습니다. [시연 데이터 초기화] 후 다시 시도하세요.")
    _pipe(("HSET", key, iid, raw), ("EXPIRE", key, TTL))
    return value


def delete(col: str, item_id: str) -> None:
    _pipe(("HDEL", _key(col), _clean_id(item_id)))


def reset() -> None:
    _pipe(*[("DEL", PREFIX + c) for c in COLLECTIONS])
