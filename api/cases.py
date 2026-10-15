"""채용 확정 → 신청 건(담당자 확인 대시보드용).

POST /api/cases {"posting": {...공고 입력}, "posting_id", "applicant_id", "hire_date", "contract": {...근로조건},
                 "applicant": {"alias", "profile": {...}} (저장된 구직자), "as_of": "YYYY-MM-DD" (시연: 이 날짜 기준으로 고용유지 계산)}
GET  /api/cases 시연용 신청 건 목록

- 근로계약 조건은 규칙엔진(labor.py)으로 점검하고, 공고 점검 항목·고용유지 기간·신청 가능일을 함께 정리한다.
- 참여 이력 근거(사유)는 채용 확정 후, 근로자가 동의한 경우에만 신청 건에 붙는다.
- 이 화면은 판단을 대신하지 않는다. 확인 항목을 모아 보여 주고 최종 결정은 고용센터·운영기관 담당자가 한다.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))  # 공용 모듈 위치

from claimdocs import check_month, missing_months  # noqa: E402
from common import ApiError, JsonHandler, num, text  # noqa: E402
from labor import check as contract_check  # noqa: E402
from rules import BAD, CHECK, GUIDE_YOUTH, d, history_flags, judge, posting_check, schedule  # noqa: E402
from userinput import parse_posting, parse_seeker  # noqa: E402
from synthetic import applicants_for, posting  # noqa: E402

CONTRACT_KEYS = ("employment_type", "wage_type", "start_date", "end_date", "base_wage", "allowances", "weekly_hours", "daily_hours", "break_minutes")
HAS_KEYS = ("has_holiday", "has_leave", "has_place", "has_job", "has_payday")


def resolve_applicant(post: dict, aid: str, mine: dict | None, given: dict | None = None) -> dict | None:
    if isinstance(given, dict) and isinstance(given.get("profile"), dict):  # 구직자 화면에서 저장된 지원자
        me = parse_seeker(given["profile"])
        return {**me, "id": aid, "alias": text(given.get("alias"), 20) or "지원자"}
    if aid.endswith("-ME"):
        if not isinstance(mine, dict) or not isinstance(mine.get("profile"), dict):
            return None
        me = parse_seeker(mine["profile"])
        return {**me, "id": aid, "alias": "구직자 화면 작성자(시연)"}
    return next((a for a in applicants_for(post) if a["id"] == aid), None)


def contract_from(post: dict, hire: date, given: dict | None) -> dict:
    f = {"employment_type": post.get("emp_type") or "정규직", "wage_type": "월급", "start_date": hire.isoformat(), "end_date": "",
         "base_wage": post.get("wage"), "allowances": 0, "weekly_hours": post.get("weekly_hours") or 40, "daily_hours": 8, "break_minutes": 60,
         **{k: True for k in HAS_KEYS}}
    for k, v in (given or {}).items():
        if k in CONTRACT_KEYS:
            f[k] = num(v) if k in ("base_wage", "allowances", "weekly_hours", "daily_hours", "break_minutes") else text(v, 10)
        elif k in HAS_KEYS:
            f[k] = bool(v)
    return f


def build_case(post: dict, app: dict, hire: date, contract: dict | None = None, today: date | None = None) -> dict:
    j = judge(app, post, app.get("consent", False))
    pc = posting_check(post)
    cc = contract_check(contract_from(post, hire, contract))
    sch = schedule(hire, today)
    if j["type"] == "non_capital":
        evidence = {"open": True, "title": "비수도권 유형 — 청년 연령 확인", "lines": ["취업애로 요건 없이 청년(만 15~34세) 채용 시 대상. 연령은 고용24 회원 정보로 확인"]}
    elif j["eligible"] and app.get("detail_consent", app.get("consent")):  # 채용 후 세부정보 열람 동의(지원자 선택)
        evidence = {"open": True, "title": f"취업애로청년 근거: {j['reason']}", "lines": history_flags(app, before=hire)["evidence"]}
    elif j["eligible"]:
        evidence = {"open": False, "title": "근로자 동의 전 — 참여 이력 근거 비공개", "lines": ["지원자가 '채용 후 세부정보 열람'에 동의하지 않았습니다. 신청 시 근로자 본인의 동의가 필요합니다."]}
    else:
        evidence = {"open": True, "title": "취업애로청년 근거 미확인", "lines": ["참여 이력에서 해당 근거가 확인되지 않음 — 다른 요건 해당 여부는 고용센터 확인"]}
    checklist = [i for i in pc["items"] if i["item"] != "지원 유형"]
    checklist.append({"level": "충족" if sch["months_kept"] >= 6 else CHECK, "item": "고용유지 6개월",
                      "detail": f"채용 {sch['hire_date']} → {sch['months_kept']}개월 경과 (6개월 시점 {sch['six_month_date']})", "basis": GUIDE_YOUTH})
    issues = [r for r in cc if r["level"] != "적정"]
    checklist.append({"level": BAD if any(r["level"] == "위반 의심" for r in cc) else CHECK if issues else "충족", "item": "근로계약 점검",
                      "detail": " / ".join(f"{r['item']}: {r['detail']}" for r in issues) or "최저임금·근로시간·휴게·필수 기재사항 이상 없음",
                      "basis": "근로기준법·최저임금법 (규칙 점검)"})
    status = "보완 필요" if any(c["level"] == BAD for c in checklist) else "확인 필요" if any(c["level"] == CHECK for c in checklist) else "검토 대기"
    return {"case_id": f"C-{post['id']}-{app['id'].split('-')[-1]}-{hire:%m%d}", "company": post["company"], "region": post["region"],
            "title": post["title"], "worker": app["alias"], "hire_date": hire.isoformat(), "program": "청년일자리도약장려금",
            "evidence": evidence, "checklist": checklist, "contract": cc, "schedule": sch, "status": status, "source": "합성 데이터(시연)"}


# 시연용 과거 채용 건 (합성). 참여 이력 날짜가 채용일보다 앞서도록 따로 둔다.
DEMO = [
    ("JOB-04", "2026-03-03", {"id": "D-1", "alias": "정○○", "age": 26, "consent": True,
                              "programs": [{"type": "청년도전지원사업", "completed": "2026-01-30", "status": "수료"}], "insurance": []}),
    ("JOB-03", "2026-05-11", {"id": "D-2", "alias": "한○○", "age": 29, "consent": False,
                              "programs": [{"type": "국민취업지원제도", "qualified": "2025-11-03", "iap": "2025-11-17"}], "insurance": []}),
    ("JOB-09", "2026-04-01", {"id": "D-3", "alias": "오○○", "age": 25, "consent": True,
                              "programs": [{"type": "국민취업지원제도", "qualified": "2025-10-13", "iap": "2025-10-27"}], "insurance": []}),
]


def demo_docs(post: dict, hire: date, worker: str, skip: tuple = (), short: tuple = (), today: date | None = None) -> dict:
    """시연용: 기업이 매월 올려 점검한 서류 기록(합성). skip = 안 올린 달 순번, short = 이체액이 적은 달 순번."""
    gross = post.get("wage") or 2_600_000
    net = gross - (gross * 115 // 1000) // 10 * 10
    months_ = missing_months(hire.isoformat(), [], today)  # 입사월~지난달
    hist, rows = [], []
    for i, m in enumerate(months_):
        if i in skip:
            rows.append({"month": m, "level": "미첨부", "note": "서류 미첨부 — 퇴사·휴직 여부 확인"})
            continue
        y, mm = map(int, m.split("-"))
        pay = f"{y + (mm == 12):04d}-{(mm % 12) + 1:02d}-10"
        ps = {"name": worker, "ym": m, "gross": gross, "net": net, "pay_date": pay}
        tr = {"recipient": worker, "amount": net - (30_000 if i in short else 0), "date": pay}
        chk = check_month(m, ps, tr, {"worker": worker, "weekly_hours": post.get("weekly_hours") or 40, "history": hist})
        hist.append({"ym": m, "gross": gross})
        rows.append({"month": m, "level": chk["level"], "note": " / ".join(f"{i_['item']}: {i_['detail']}" for i_ in chk["items"] if i_["level"] != "일치")})
    done = [r for r in rows if r["level"] != "미첨부"]
    return {"program": "청년일자리도약장려금", "expected": len(rows), "uploaded": len(done), "mismatch": sum(r["level"] == "불일치" for r in done),
            "check": sum(r["level"] == "확인 필요" for r in done), "avg": gross if done else 0, "total": gross * len(done), "months": rows}


DEMO_DOCS = {"D-1": {"short": (4,)}, "D-2": {"skip": (3,)}, "D-3": {"short": (2,)}}


def demo_cases(today: date | None = None) -> list[dict]:
    out = []
    for jid, hd, app in DEMO:
        post, hire = posting(jid), d(hd)
        c = build_case(post, app, hire, today=today)
        c["docs"] = demo_docs(post, hire, app["alias"].replace("○○", "가람"), today=today, **DEMO_DOCS[app["id"]])
        if c["docs"]["mismatch"] or c["docs"]["uploaded"] < c["docs"]["expected"]:
            c["checklist"].append({"level": CHECK, "item": "월별 서류 사전 점검", "basis": "기업 첨부 서류 (월별 점검 기록)",
                                   "detail": f"첨부 {c['docs']['uploaded']}/{c['docs']['expected']}개월 · 불일치 {c['docs']['mismatch']}건 — 아래 월별 기록 확인"})
            if c["status"] == "검토 대기":
                c["status"] = "확인 필요"
        out.append(c)
    return out


class handler(JsonHandler):
    def handle_get(self):
        return {"ok": True, "cases": demo_cases()}

    def handle_post(self):
        b = self.read_json(max_body=60_000)
        if not isinstance(b.get("posting"), dict):
            raise ApiError(400, "missing_input", "공고를 먼저 점검하세요.")
        post = parse_posting(b["posting"])
        if b.get("posting_id"):
            post["id"] = text(b["posting_id"], 40)
        app = resolve_applicant(post, text(b.get("applicant_id"), 80), b.get("my_application"), b.get("applicant"))
        if not app:
            raise ApiError(400, "missing_input", "채용할 지원자를 선택하세요.")
        hire = d(b.get("hire_date"))
        if not hire:
            raise ApiError(400, "missing_input", "채용일(입사일)을 입력하세요.")
        contract = b.get("contract") if isinstance(b.get("contract"), dict) else None
        as_of = d(b.get("as_of"))  # 시연: 급여 6개월분을 미리 발급해 본 경우 그 시점 기준으로 계산
        case = build_case(post, app, hire, contract, today=as_of)
        if as_of:
            case["as_of"] = as_of.isoformat()
        return {"ok": True, "case": case}
