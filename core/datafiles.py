"""data/synthetic/ 의 합성데이터 파일 읽기 (형식: docs/data-spec.md).

파일이 없으면 빈 값을 돌려주고, 기존 내장 합성데이터(synthetic.py)만으로 동작한다.
고용24 응답 형식(XML) 해석은 실제 API(work24.py)와 같은 함수를 쓴다 → 키 승인 후 데이터만 바꿔 끼우면 된다.
"""
import json
import os
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data", "synthetic")
REGULAR_CODES = {"10", "11"}  # 고용형태 코드: 기간의 정함이 없는 근로계약(시간선택제 포함)

WANTED_TAGS = ["wantedAuthNo", "company", "busino", "indTpNm", "title", "salTpNm", "sal", "minSal", "maxSal", "region",
               "holidayTpNm", "minEdubg", "maxEdubg", "career", "regDt", "closeDt", "infoSvc", "wantedInfoUrl",
               "wantedMobileInfoUrl", "zipCd", "strtnmCd", "basicAddr", "detailAddr", "empTpCd", "jobsCd", "smodifyDtm"]
ARREARS_TAGS = ["lnkReqNo", "lnkSucsYn", "brno", "bzmn", "judgReltYn", "errMsgCd", "errMsg"]


def path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _ymd(s: str) -> str:
    s = "".join(ch for ch in str(s or "") if ch.isdigit())
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else ""


def _digits(s) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def parse_wanted(xml_bytes: bytes, source: str = "live") -> list[dict]:
    """고용24 채용정보 목록 응답(XML) → 공고 목록. 실제 API 응답과 합성 파일이 같은 함수를 쓴다."""
    root = ET.fromstring(xml_bytes)
    out = []
    for w in root.iter("wanted"):
        g = lambda tag: (w.findtext(tag) or "").strip()  # noqa: E731
        wage = None
        if g("salTpNm") == "월급":
            if _digits(g("minSal")):
                wage = int(_digits(g("minSal")))
            else:
                sal = _digits(g("sal").split("~")[0])
                wage = int(sal) * (10000 if len(sal) <= 4 else 1) if sal else None
        emp = g("empTpCd")
        out.append({"id": "W24-" + g("wantedAuthNo"), "company": g("company"), "busino": _digits(g("busino")),
                    "industry": g("indTpNm"), "region": g("region"), "title": g("title"),
                    "job": g("jobsNm") or g("title"), "emp_type": "정규직" if emp in REGULAR_CODES else ("계약직" if emp else None),
                    "wage": wage, "weekly_hours": None, "insured": None, "priority": None, "arrears": None,
                    "skills": [s for s in g("title").replace("/", " ").replace("(", " ").replace(")", " ").split() if len(s) > 1][:6],
                    "close": _ymd(g("closeDt")), "url": g("wantedInfoUrl"), "source": source})
    return [o for o in out if o["id"] != "W24-"]


def _read(name: str):
    p = path(name)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def load_json(name: str) -> list:
    raw = _read(name)
    if raw is None:
        return []
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, list) else []


def load_companies() -> dict:
    return {_digits(c.get("busino")): c for c in load_json("companies.json") if _digits(c.get("busino"))}


def load_arrears() -> dict:
    """사업자번호 → True(명단공개 대상) / False(비대상) / None(조회 실패)."""
    raw = _read("work24_arrears.xml")
    if raw is None:
        return {}
    root = ET.fromstring(raw)
    rows = [root] if root.tag == "jdgnList" else list(root.iter("jdgnList"))
    out = {}
    for r in rows:
        g = lambda tag: (r.findtext(tag) or "").strip()  # noqa: E731
        b = _digits(g("brno"))
        if b:
            out[b] = None if g("lnkSucsYn") != "Y" else g("judgReltYn") == "Y"
    return out


def enrich(post: dict, companies: dict, arrears: dict) -> dict:
    """공고에 기업 정보(피보험자 수·우선지원·주 소정근로시간)와 임금체불 조회 결과를 사업자번호로 붙인다."""
    c = companies.get(post.get("busino") or "", {})
    post["insured"] = c.get("insured")
    post["priority"] = c.get("priority")
    post["weekly_hours"] = c.get("weekly_hours") or 40
    post["region"] = post.get("region") or c.get("region") or ""
    post["industry"] = post.get("industry") or c.get("indTpNm") or ""
    post["tax_arrears"] = bool(c.get("tax_arrears"))
    if post.get("busino") in arrears:
        post["arrears"] = arrears[post["busino"]]
    return post


def lookup_company(busino) -> dict | None:
    """사업자번호 → 공공데이터 조회 결과(합성). 실제 연동 시 고용24 임금체불 API·국민연금 사업장 등으로 교체.
    반환: {industry, insured, priority, arrears(True/False/None), tax_arrears} 또는 None(등록되지 않은 번호)."""
    b = _digits(busino)
    companies = load_companies()
    if b not in companies:
        return None
    c, arrears = companies[b], load_arrears()
    return {"industry": c.get("indTpNm") or "", "insured": c.get("insured"), "priority": c.get("priority"),
            "arrears": arrears.get(b), "tax_arrears": bool(c.get("tax_arrears"))}


def load_postings() -> list[dict]:
    raw = _read("work24_postings.xml")
    if raw is None:
        return []
    companies, arrears = load_companies(), load_arrears()
    return [enrich(p, companies, arrears) for p in parse_wanted(raw, source="synthetic_file")]


def load_seekers() -> list[dict]:
    return [p for p in load_json("seekers.json") if p.get("id") and p.get("alias")]
