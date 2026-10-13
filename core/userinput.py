"""이용자가 직접 입력한 구직자 이력·기업 공고를 검증하고 규칙엔진이 쓰는 형태로 바꾼다.

- 지원제도 판단에 쓰는 사실(참여 사업·날짜·참여 후 취업 여부·청년 여부)은 이용자가 '선택·날짜'로 입력한다.
  AI가 자유 서술에서 뽑아낸 값으로 판단하지 않는다 (본인 입력값 → 실제 서비스에서는 고용24 이력으로 대체·확인).
- 자유 서술(경험, 공고 본문)은 AI가 정리하는 재료로만 쓴다.
"""
import re
from datetime import date

from common import ApiError, num, text
from rules import d

SIDO = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
SEEK_REGIONS = SIDO + ["무관"]
EMP_TYPES = ["정규직", "계약직", "기타"]


def _date(v, label: str, today: date) -> str:
    day = d(v)
    if not day:
        raise ApiError(400, "missing_input", f"필수값을 입력하세요: {label}")
    if day > today:
        raise ApiError(400, "invalid_input", f"{label}은(는) 오늘 이후 날짜일 수 없습니다.")
    return day.isoformat()


CONSENT_VERSION = "2026-10-10-v1"
# 채용 전 기업 화면에 보내는 글에서 가리는 표현 (참여 사업 = 지원제도 사유)
PROGRAM_WORDS = re.compile(r"국민취업지원제도|국민취업지원|국취|청년도전지원사업|청년도전|취업활동계획|수급자격")


def redact_programs(s: str) -> str:
    """채용 전 기업 화면용: 참여 사업명이 들어간 문장은 통째로 뺀다 ('[비공개]'로 남기면 참여 사실이 짐작되므로)."""
    out = []
    for line in (s or "").split("\n"):
        parts = re.split(r"(?<=[.!?。])\s+", line)
        kept = " ".join(p for p in parts if not PROGRAM_WORDS.search(p))
        if kept.strip() or not line.strip():
            out.append(kept)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def has_program_words(s: str) -> bool:
    return bool(PROGRAM_WORDS.search(s or ""))


def parse_cert(c, form: dict, today: date) -> dict | None:
    """수료증 AI 판독값(본인이 확인한 것) → 폼 값과 일치하는지 표시. 판단 자체는 폼 값으로 한다."""
    if not isinstance(c, dict) or not c.get("program"):
        return None
    prog, day = text(c.get("program"), 20), d(c.get("date"))
    if prog not in ("청년도전지원사업", "국민취업지원제도", "기타") or (day and day > today):
        return None
    target = {"청년도전지원사업": form.get("dojeon_completed"), "국민취업지원제도": form.get("kuchwi_qualified")}.get(prog)
    return {"program": prog, "date": day.isoformat() if day else "", "issuer": text(c.get("issuer"), 40), "course": text(c.get("course"), 80),
            "matched": bool(day and target and day.isoformat() == str(target)[:10])}


def parse_seeker(b: dict, today: date | None = None) -> dict:
    """구직자 입력 → person(dict). 연령은 '청년 여부'만 받고 숫자 나이는 받지 않는다."""
    today = today or date.today()
    if not isinstance(b, dict):
        raise ApiError(400, "bad_json", "요청 형식이 올바르지 않습니다.")
    if not b.get("agree_privacy"):
        raise ApiError(400, "need_consent", "[필수] 개인정보 수집·이용에 동의해야 이용할 수 있습니다.")
    exp = text(b.get("experience"), 1500)
    job = text(b.get("job"), 30)
    region = text(b.get("region"), 10) or "무관"
    missing = [label for v, label in ((exp, "내 경험"), (job, "희망 직무")) if not v]
    if missing:
        raise ApiError(400, "missing_input", "필수값을 입력하세요: " + ", ".join(missing))
    if len(exp) < 10:
        raise ApiError(400, "invalid_input", "내 경험을 조금 더 자세히(10자 이상) 적어 주세요.")
    if region not in SEEK_REGIONS:
        raise ApiError(400, "invalid_input", "희망 지역을 목록에서 선택하세요.")
    programs, insurance = [], []
    if b.get("kuchwi"):
        q = _date(b.get("kuchwi_qualified"), "국민취업지원제도 수급자격 인정일", today)
        prog = {"type": "국민취업지원제도", "qualified": q, "status": "참여"}
        if b.get("kuchwi_iap"):
            prog["iap"] = q  # 취업활동계획 수립 여부만 받으므로 인정일로 기록 (실제 서비스는 고용24 이력)
        programs.append(prog)
        if b.get("kuchwi_job_after"):
            insurance.append({"company": "참여 후 취업(본인 입력)", "acquired": q, "lost": ""})
    if b.get("dojeon"):
        programs.append({"type": "청년도전지원사업", "completed": _date(b.get("dojeon_completed"), "청년도전지원사업 수료일", today), "status": "수료"})
    youth = bool(b.get("youth"))
    points = [text(x, 160) for x in (b.get("points") or [])[:8] if text(x, 160)] if isinstance(b.get("points"), list) else []
    return {"id": "ME", "alias": text(b.get("alias"), 10) or "나", "youth": youth, "age": 25 if youth else 40,  # age는 규칙 계산용 대표값
            "programs": programs, "insurance": insurance, "experience": exp, "extra": "",
            "desire": {"job": job, "region": region},
            "consent": bool(b.get("consent")),                 # [선택] 지원제도 활용 가능 표시 공개
            "ai_consent": bool(b.get("agree_ai")),             # [필수: AI 기능] 처리위탁·국외이전 고지 동의
            "detail_consent": bool(b.get("agree_detail")),     # [선택] 채용 확정 후 세부정보 열람
            "cert": parse_cert(b.get("cert"), b, today) if b.get("agree_cert") else None,
            "points": points, "portfolio": text(b.get("portfolio"), 4000)}


def seeker_history_lines(p: dict) -> list[str]:
    out = []
    for g in p.get("programs") or []:
        if g["type"] == "국민취업지원제도":
            out.append(f"국민취업지원제도 (수급자격 인정 {g['qualified']}" + (", 취업활동계획 수립" if g.get("iap") else "") + ")")
        else:
            out.append(f"청년도전지원사업 (수료 {g['completed']})")
    return out


DISCRIM = re.compile(r"\d+\s*세\s*(이하|미만|이상|까지)|(남성|여성|남자|여자)\s*(만|우대|지원|채용)|용모\s*단정")


def parse_posting(b: dict) -> dict:
    """기업 공고 입력 → posting(dict)."""
    if not isinstance(b, dict):
        raise ApiError(400, "bad_json", "요청 형식이 올바르지 않습니다.")
    p = {"id": "CUSTOM", "company": text(b.get("company"), 40) or "우리 회사", "sido": text(b.get("sido"), 5), "sigungu": text(b.get("sigungu"), 15),
         "title": text(b.get("title"), 60), "job": text(b.get("job"), 30), "emp_type": text(b.get("emp_type"), 5),
         "wage": num(b.get("wage")), "weekly_hours": num(b.get("weekly_hours")) or 40, "insured": num(b.get("insured")),
         "description": text(b.get("description"), 1500), "close": text(b.get("close"), 10), "url": "", "source": "user"}
    missing = [label for k, label in (("sido", "근무지(시·도)"), ("title", "공고 제목"), ("job", "직무"), ("emp_type", "고용형태")) if not p[k]]
    if p["wage"] is None:
        missing.append("월 임금")
    if missing:
        raise ApiError(400, "missing_input", "필수값을 입력하세요: " + ", ".join(missing))
    if p["sido"] not in SIDO or p["emp_type"] not in EMP_TYPES:
        raise ApiError(400, "invalid_input", "근무지와 고용형태는 목록에서 선택하세요.")
    if p["wage"] <= 0 or not (0 < p["weekly_hours"] <= 52):
        raise ApiError(400, "invalid_input", "월 임금은 0보다 크고, 주 소정근로시간은 52시간 이하로 입력하세요.")
    p["region"] = f"{p['sido']} {p['sigungu']}".strip()
    p["wage"] = int(p["wage"])
    p["insured"] = int(p["insured"]) if p["insured"] is not None else None
    p["priority"] = {"예": True, "아니오": False}.get(text(b.get("priority"), 5))  # 모름 → None (확인 필요)
    p["arrears"] = None  # 임금체불 명단 여부는 고용24 연동 후 확인
    p["skills"] = []
    p["discrim"] = sorted({m.group(0) for m in DISCRIM.finditer(f"{p['title']} {p['description']}")})
    return p


def posting_to_form(post: dict) -> dict:
    """합성 공고 → 입력 폼 예시값."""
    sido, _, sigungu = post["region"].partition(" ")
    return {"company": post["company"], "sido": sido, "sigungu": sigungu, "title": post["title"], "job": post["job"],
            "emp_type": post["emp_type"] if post["emp_type"] in EMP_TYPES else "기타", "wage": post["wage"], "weekly_hours": post["weekly_hours"],
            "insured": post["insured"], "priority": "예" if post["priority"] else "아니오",
            "description": f"{post['title']} 채용. 주요 업무와 우대 기술: {', '.join(post['skills'])}. 신입 지원 가능, 주 5일 근무."}


def persona_to_form(p: dict) -> dict:
    """합성 인물 → 입력 폼 예시값 (예시 불러오기 버튼용)."""
    f = {"alias": p["alias"], "youth": 15 <= p["age"] <= 34, "job": p["desire"]["job"], "region": p["desire"]["region"],
         "experience": "\n".join(f"- {a['name']}" + (f" ({a['hours']}시간)" if a.get("hours") else "") + f", {a['done'][:7]}" for a in p["activities"]),
         "kuchwi": False, "dojeon": False}
    for g in p["programs"]:
        if g["type"] == "국민취업지원제도":
            f.update(kuchwi=True, kuchwi_qualified=g["qualified"], kuchwi_iap=bool(g.get("iap")),
                     kuchwi_job_after=any(d(i["acquired"]) and d(i["acquired"]) >= d(g["qualified"]) for i in p["insurance"]))
        if g["type"] == "청년도전지원사업":
            f.update(dojeon=True, dojeon_completed=g["completed"])
    return f
