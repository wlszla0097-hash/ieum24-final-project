"""이음24 규칙엔진 — '지원제도 활용 가능' 표시(배지) 판단, 공고 점검, 신청 시기 계산.

판단은 전부 이 코드가 한다. AI는 결과를 설명만 하고, 여기서 정한 값을 바꾸지 못한다.
기준: 2026년 청년일자리도약장려금 사업운영 지침 1-3항(취업애로청년) 및 기업 요건.
지침 해석은 실무자가 원문과 대조해 확정한 것만 규칙으로 옮기고, 애매한 항목은 '확인 필요'로 둔다.
"""
from datetime import date

from labor import MIN_WAGE, monthly_hours

GUIDE = "2026 청년일자리도약장려금 지침"
GUIDE_YOUTH = f"{GUIDE} 1-3항 (취업애로청년)"
CAPITAL = ("서울", "경기", "인천")
OK, CHECK, BAD, INFO = "충족", "확인 필요", "미충족", "안내"


def d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def is_capital(region: str | None) -> bool | None:
    if not region:
        return None
    return str(region).strip().startswith(CAPITAL)


def is_youth(age) -> bool:
    return isinstance(age, int) and 15 <= age <= 34


def history_flags(person: dict, before: date | None = None) -> dict:
    """참여 이력·고용보험 이력 → 취업애로청년 근거 (국취 참여 후 최초 취업 / 청년도전 수료)."""
    flags = {"kuchwi_first_job": False, "dojeon_completed": False, "evidence": []}
    ins = person.get("insurance") or []
    for p in person.get("programs") or []:
        if p.get("type") == "국민취업지원제도" and d(p.get("qualified")) and d(p.get("iap")):
            start = d(p["qualified"])
            jobs_after = [i for i in ins if d(i.get("acquired")) and d(i["acquired"]) >= start
                          and (before is None or d(i["acquired"]) < before)]
            if jobs_after:
                flags["evidence"].append(f"국민취업지원제도 참여 후 고용보험 취득 이력 있음({jobs_after[0]['acquired']}) → '최초 취업' 아님")
            else:
                flags["kuchwi_first_job"] = True
                flags["evidence"].append(f"국민취업지원제도 수급자격 인정({p['qualified']})·취업활동계획 수립({p['iap']}), 참여 후 고용보험 취득 이력 없음")
        if p.get("type") == "청년도전지원사업" and d(p.get("completed")) and (before is None or d(p["completed"]) < before):
            flags["dojeon_completed"] = True
            flags["evidence"].append(f"청년도전지원사업 수료({p['completed']})")
    c = person.get("cert")
    if c and c.get("matched"):
        flags["evidence"].append(f"증빙 첨부: {c['program']} 서류({c.get('issuer') or '발급기관 미판독'}) — AI 판독 날짜 {c['date']}가 입력값과 일치")
    elif c:
        flags["evidence"].append(f"증빙 첨부: {c['program']} 서류 — AI 판독값이 입력값과 다름, 원본 확인 필요")
    return flags


def judge(person: dict, post: dict, consent: bool) -> dict:
    """지원자 1명 × 공고 1건에 대한 배지 판단. seeker_text 는 본인에게만, employer 에는 badge 여부만 보낸다."""
    cap = is_capital(post.get("region"))
    flags = history_flags(person)
    youth = is_youth(person.get("age"))
    base = {"badge": False, "eligible": False, "basis": GUIDE_YOUTH, "flags": flags}
    if post.get("emp_type") not in (None, "정규직"):
        return {**base, "type": "not_regular", "seeker_text": "정규직 공고가 아니라서 채용지원금 연계 대상이 아니에요."}
    if post.get("priority") is False:
        return {**base, "type": "company_not_eligible", "seeker_text": "이 기업은 우선지원대상기업이 아니어서 채용지원금 연계가 어려울 수 있어 표시하지 않아요."}
    if cap is False:
        text = "비수도권 기업이라 취업애로 요건 없이 청년 채용 자체로 기업이 지원을 받을 수 있어요. 기업 공고에 안내되므로 별도 표시는 필요 없어요." if youth \
            else "비수도권 기업의 청년 채용 지원 유형이지만, 청년 연령 요건은 고용센터 확인이 필요해요."
        return {**base, "type": "non_capital", "seeker_text": text}
    if cap is None:
        return {**base, "type": "unknown_region", "seeker_text": "근무지역을 확인할 수 없어 판단을 보류했어요."}
    eligible = youth and (flags["kuchwi_first_job"] or flags["dojeon_completed"])
    if not eligible:
        why = "청년 연령 요건 확인 필요" if not youth else "국민취업지원제도 참여 후 최초 취업·청년도전지원사업 수료 이력이 확인되지 않음"
        return {**base, "type": "capital_none",
                "seeker_text": f"수도권 기업 유형의 취업애로청년 근거가 이력에서 확인되지 않아 표시하지 않아요 ({why}). 다른 요건 해당 여부는 고용센터에서 확인할 수 있어요."}
    kind = "국민취업지원제도 참여 후 최초 취업" if flags["kuchwi_first_job"] else "청년도전지원사업 수료"
    text = (f"이 기업이 나를 정규직으로 채용하면 '{kind}' 근거로 기업이 청년일자리도약장려금을 활용할 수 있을 것으로 예상돼요."
            + ("" if consent else " 지금은 동의하지 않아 기업 화면에 표시되지 않아요."))
    return {**base, "type": "capital_eligible", "eligible": True, "badge": bool(consent), "reason": kind, "seeker_text": text}


def posting_check(post: dict) -> dict:
    """기업 공고 점검: 이 공고로 채용하면 청년일자리도약장려금과 연계할 수 있는지 확인 항목을 정리."""
    items = []

    def add(level, item, detail, basis=GUIDE):
        items.append({"level": level, "item": item, "detail": detail, "basis": basis})

    cap = is_capital(post.get("region"))
    if cap is True:
        add(INFO, "지원 유형", "수도권 기업 → 취업애로청년(국민취업지원제도 참여 후 최초 취업, 청년도전지원사업 수료 등)을 채용할 때 대상", GUIDE_YOUTH)
    elif cap is False:
        add(INFO, "지원 유형", "비수도권 기업 → 청년(만 15~34세)을 채용하면 취업애로 요건 없이 대상. 지원자 화면에 별도 표시 없이 공고 단위로 안내", GUIDE_YOUTH)
    else:
        add(CHECK, "지원 유형", "근무지역 정보가 없어 유형을 판단하지 못함")

    et = post.get("emp_type")
    add(OK if et == "정규직" else BAD if et else CHECK, "고용형태", "정규직 채용" if et == "정규직" else f"'{et or '미기재'}' — 정규직 채용만 지원 대상")

    pr = post.get("priority")
    add(OK if pr else CHECK, "우선지원대상기업",
        "우선지원대상기업" if pr else ("우선지원대상기업이 아님 — 지원 제외 또는 예외 업종 여부를 지침으로 확인" if pr is False else "정보 없음 — 기업 규모 확인 필요"))

    n = post.get("insured")
    if n is None:
        add(CHECK, "피보험자 수", "정보 없음 — 피보험자 수 5인 이상인지 확인")
    else:
        add(OK if n >= 5 else CHECK, "피보험자 수", f"{n}명" + ("" if n >= 5 else " — 5인 미만은 일부 예외 업종만 가능하니 지침 확인"))

    wage, hrs = post.get("wage"), post.get("weekly_hours") or 40
    rate = MIN_WAGE.get(date.today().year) or MIN_WAGE[max(MIN_WAGE)]
    if wage:
        hourly = wage / monthly_hours(hrs)
        add(OK if hourly + 0.5 >= rate else BAD, "임금(최저임금)",
            f"월 {wage:,}원 ÷ {monthly_hours(hrs)}시간 = 시급 {hourly:,.0f}원 " + ("≥" if hourly + 0.5 >= rate else "<") + f" 최저임금 {rate:,}원",
            "최저임금법 제6조")
    else:
        add(CHECK, "임금(최저임금)", "임금 정보 없음", "최저임금법 제6조")

    if post.get("arrears"):
        add(BAD, "임금체불 명단공개", "명단공개 사업주에 해당 — 지원 제한 대상 여부 확인, 구직자 추천에서 제외", "고용24 임금체불 명단공개 사업주 여부")
    elif post.get("arrears") is False:
        add(OK, "임금체불 명단공개", "해당 없음", "고용24 임금체불 명단공개 사업주 여부")
    else:
        add(INFO, "임금체불 명단공개", "고용24 OpenAPI 연동 후 자동 확인", "고용24 임금체불 명단공개 사업주 여부")

    if post.get("discrim"):
        add(CHECK, "채용 차별 소지 표현", "공고에 '" + "', '".join(post["discrim"]) + "' 표현 — 합리적 이유 없는 연령·성별 제한은 금지되므로 삭제·수정 검토",
            "고용상 연령차별금지법 제4조의4, 남녀고용평등법 제7조")

    bad = sum(1 for i in items if i["level"] == BAD)
    chk = sum(1 for i in items if i["level"] == CHECK)
    verdict = "연계 어려움" if bad else "확인 필요" if chk else "연계 가능성 높음"
    return {"verdict": verdict, "region_type": "capital" if cap else "non_capital" if cap is False else "unknown", "items": items}


def add_months(day: date, months: int) -> date:
    y, m = divmod(day.month - 1 + months, 12)
    y, m = day.year + y, m + 1
    for dd in (day.day, 30, 29, 28):
        try:
            return date(y, m, dd)
        except ValueError:
            continue
    raise ValueError("날짜 계산 오류")


def schedule(hire: date, today: date | None = None) -> dict:
    """채용일 → 6개월 고용유지 시점(신청 가능일)과 알림일. 신청 기한·지급 주기는 지침 확인 항목으로 둔다."""
    today = today or date.today()
    kept = add_months(hire, 6)
    notify = date.fromordinal(kept.toordinal() - 7)
    left = (kept - today).days
    months = (today.year - hire.year) * 12 + today.month - hire.month - (1 if today.day < hire.day else 0)
    return {"hire_date": hire.isoformat(), "six_month_date": kept.isoformat(), "notify_date": notify.isoformat(),
            "days_left": left, "months_kept": max(months, 0),
            "state": "신청 가능" if left <= 0 else "알림 예정" if left <= 7 else "고용유지 중",
            "note": "채용 후 6개월 고용유지 후 신청. 신청 기한·지급 주기는 해당 연도 지침에서 확인"}
