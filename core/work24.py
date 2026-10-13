"""고용24 OpenAPI 채용정보 연동 (선택).

WORK24_KEY 환경 변수(고용24 OpenAPI 인증키)가 있으면 채용정보 목록을 불러오고,
없거나 실패하면 합성 공고(synthetic.POSTINGS)로 동작한다. 화면에는 출처를 항상 표시한다.

※ 엔드포인트·응답 항목은 고용24 OpenAPI 이용 승인 후 개발명세서로 다시 확인해야 한다.
   주소는 WORK24_BASE_URL 로 바꿀 수 있게 두었다.
"""
import http.client
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from synthetic import POSTINGS

BASE = os.environ.get("WORK24_BASE_URL") or "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
CACHE_SECONDS = 3600
_cache: dict = {"at": 0.0, "items": None, "source": None}
REGULAR_CODES = {"10", "11"}  # 고용형태 코드: 기간의 정함이 없는 근로계약(시간선택제 포함)


def _parse(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for w in root.iter("wanted"):
        g = lambda tag: (w.findtext(tag) or "").strip()  # noqa: E731
        sal = "".join(ch for ch in g("sal").split("~")[0] if ch.isdigit())
        out.append({"id": "W24-" + g("wantedAuthNo"), "company": g("company"), "region": g("region"), "title": g("title"),
                    "job": g("jobsNm") or g("title"), "emp_type": "정규직" if g("empTpCd") in REGULAR_CODES else ("계약직" if g("empTpCd") else None),
                    "wage": int(sal) * (10000 if len(sal) <= 4 else 1) if sal and g("salTpNm") == "월급" else None,
                    "weekly_hours": None, "insured": None, "priority": None, "arrears": None,
                    "skills": [s for s in g("title").replace("/", " ").split() if len(s) > 1][:6],
                    "close": g("closeDt"), "url": g("wantedInfoUrl"), "source": "live"})
    return [o for o in out if o["id"] != "W24-"]


def load_postings(keyword: str = "") -> tuple[list[dict], str]:
    """(공고 목록, 'live'|'synthetic'). 키가 있어도 실패하면 합성 공고로 대체."""
    key = os.environ.get("WORK24_KEY")
    if not key:
        return POSTINGS, "synthetic"
    if _cache["items"] is not None and time.time() - _cache["at"] < CACHE_SECONDS and not keyword:
        return _cache["items"], _cache["source"]
    q = urllib.parse.urlencode({"authKey": key, "callTp": "L", "returnType": "XML", "startPage": 1, "display": 50, "keyword": keyword})
    try:
        with urllib.request.urlopen(f"{BASE}?{q}", timeout=8) as r:
            items = _parse(r.read())
    except (OSError, http.client.HTTPException, ET.ParseError, ValueError) as e:
        print("[work24] 실패 → 합성 공고 사용:", repr(e))
        items = []
    result = (items, "live") if items else (POSTINGS, "synthetic")
    if not keyword:
        _cache.update(at=time.time(), items=result[0], source=result[1])
    return result
