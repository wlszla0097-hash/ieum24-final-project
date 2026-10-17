"""이음24 규칙엔진 — '지원제도 활용 가능' 표시(배지) 판단, 공고 점검, 신청 시기 계산.

판단은 전부 이 코드가 한다. AI는 결과를 설명만 하고, 여기서 정한 값을 바꾸지 못한다.
기준: 2026년 청년일자리도약장려금 사업운영 지침 Ⅲ-1-3(취업애로청년) 및 기업 요건.
지침 해석은 실무자가 원문과 대조해 확정한 것만 규칙으로 옮기고, 애매한 항목은 '확인 필요'로 둔다.
"""
from datetime import date

from labor import MIN_WAGE, monthly_hours

GUIDE = "2026 청년일자리도약장려금 지침"
GUIDE_YOUTH = f"{GUIDE} Ⅲ-1-3 (취업애로청년 ❹ 국취·❺ 청년도전)"
CAPITAL = ("서울", "경기", "인천")
OK, CHECK, BAD, INFO = "충족", "확인 필요", "미충족", "안내"

# 지원 제외 업종 (업종명 키워드, 띄어쓰기 무시). 2026 지침 Ⅱ-2-1·별첨 9의 소비·향락업, 청소년유해업소·풍속영업 대표 업종.
# ※ 업종코드 대조가 아니라 이름 비교라 '해당 없음'은 자동 점검 범위에서만 — 최종 확인은 업종코드로
EXCLUDED_INDUSTRIES = ("유흥주점", "무도유흥", "기타주점", "단란주점", "무도장", "사행시설", "카지노", "노래연습장", "비디오감상실",
                       "복권발행", "복권판매", "경마", "경륜", "경정")
# 2026 지침 Ⅱ-1-1: 수도권 중 인구감소지역은 비수도권으로 본다
CAPITAL_EXCEPT = ("강화군", "옹진군", "가평군", "연천군")
WEEKLY_MIN, WAGE_MAX = 28, 4_500_000  # 2026 지침 Ⅲ-1-4: 주 소정근로 28시간 이상, 평균 월 급여 450만원 이하
GUIDE_HIRE = f"{GUIDE} Ⅲ-1-4 (채용 요건)"


def excluded_industry(ind: str | None) -> str | None:
    s = str(ind or "").replace(" ", "")
    return next((w for w in EXCLUDED_INDUSTRIES if w in s), None)


def min_wage_ok(monthly: float, weekly_hours, rate: int) -> bool:
    """월급 ≥ 최저임금 × 월 환산시간 (원 단위, 반올림 여유 없음)"""
    return monthly >= round(rate * monthly_hours(weekly_hours or 40))


def d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def is_capital(region: str | None) -> bool | None:
    if not region:
        return None
    r = str(region).strip()
    if any(x in r for x in CAPITAL_EXCEPT):
        return False
    return r.startswith(CAPITAL)


YOUTH_MAX, YOUTH_MAX_MIL = 34, 39  # 청년 만 15~34세, 군필자는 의무복무기간만큼 연동해 최고 만 39세 (2026 지침·사업 공고)
MIL_NOTE = "군 복무기간 연동 — 생년월일·전역일 기준 최종 확인은 고용센터"


def mil_youth(age, months) -> bool:
    """군필자 연령 연동: 만 나이에서 의무복무기간을 뺀 나이가 만 34세 이하(만 35세 미만)이면 청년. 최고 만 39세.
    나이를 '만 N세' 정수로만 받으므로 N세 0개월로 계산한다(생일에 따라 경계는 고용센터 확인)."""
    if not (isinstance(age, int) and isinstance(months, int)) or months <= 0 or not (YOUTH_MAX < age <= YOUTH_MAX_MIL):
        return False
    return age * 12 - months < (YOUTH_MAX + 1) * 12


def is_youth(age, military_months: int = 0) -> bool:
    if not isinstance(age, int):
        return False
    return 15 <= age <= YOUTH_MAX or mil_youth(age, military_months)


def history_flags(person: dict, before: date | None = None) -> dict:
    """참여 이력·고용보험 이력 → 취업애로청년 근거 (국취 참여 후 최초 취업 / 청년도전 수료).
    before = 채용일: 주면 '참여(인정) 후 채용', '수료 후 채용'인지까지 본다(채용 확정 뒤 판정). 없으면 지원 단계 예상 판정."""
    flags = {"kuchwi_first_job": False, "dojeon_completed": False, "evidence": []}
    ins = person.get("insurance") or []
    for p in person.get("programs") or []:
        if p.get("type") == "국민취업지원제도" and d(p.get("qualified")) and d(p.get("iap")) and before and d(p["qualified"]) >= before:
            flags["evidence"].append(f"국민취업지원제도 수급자격 인정({p['qualified']})이 채용일({before}) 이후 → '참여 후 취업' 아님")
        elif p.get("type") == "국민취업지원제도" and d(p.get("iap")) and before and not p.get("iap_unknown") and d(p["iap"]) >= before:
            flags["evidence"].append(f"취업활동계획 수립({p['iap']})이 채용일({before}) 이후 → 지침상 '참여'(인정+계획 수립) 전 채용")
        elif p.get("type") == "국민취업지원제도" and d(p.get("qualified")) and d(p.get("iap")):
            start = d(p["qualified"])
            jobs_after = [i for i in ins if d(i.get("acquired")) and d(i["acquired"]) >= start
                          and (before is None or d(i["acquired"]) < before)]
            if jobs_after:
                flags["evidence"].append(f"국민취업지원제도 참여 후 고용보험 취득 이력 있음({jobs_after[0]['acquired']}) → '최초 취업' 아님")
            else:
                flags["kuchwi_first_job"] = True
                flags["evidence"].append(f"국민취업지원제도 수급자격 인정({p['qualified']})·취업활동계획 수립"
                                         + (" (수립일 미입력 — 채용 전 수립 여부 확인 필요)" if p.get("iap_unknown") else f"({p['iap']})")
                                         + ", 참여 후 고용보험 취득 이력 없음 (일경험 연계 취득 등 예외는 담당자 확인)")
        if p.get("type") == "청년도전지원사업" and d(p.get("completed")) and (before is None or d(p["completed"]) < before):
            flags["dojeon_completed"] = True
            flags["evidence"].append(f"청년도전지원사업 수료({p['completed']})")
        elif p.get("type") == "청년도전지원사업" and d(p.get("completed")):
            flags["evidence"].append(f"청년도전지원사업 수료({p['completed']})가 채용일({before}) 이후 → '수료 후 채용' 아님")
    c = person.get("cert")
    if c and c.get("matched"):
        flags["evidence"].append(f"증빙 첨부: {c['program']} 서류({c.get('issuer') or '발급기관 미판독'}) — AI 판독 날짜 {c['date']}가 입력값과 일치")
    elif c:
        flags["evidence"].append(f"증빙 첨부: {c['program']} 서류 — AI 판독값이 입력값과 다름, 원본 확인 필요")
    return flags


def judge(person: dict, post: dict, consent: bool, hire: date | None = None) -> dict:
    """지원자 1명 × 공고 1건에 대한 배지 판단. seeker_text 는 본인에게만, employer 에는 badge 여부만 보낸다."""
    cap = is_capital(post.get("region"))
    flags = history_flags(person, before=hire)  # 채용 확정 뒤에는 채용일 기준(참여·수료가 채용보다 먼저인지)
    youth = is_youth(person.get("age"), person.get("military_months") or 0)
    mil = youth and mil_youth(person.get("age"), person.get("military_months") or 0)
    base = {"badge": False, "eligible": False, "basis": GUIDE_YOUTH, "flags": flags}
    if post.get("emp_type") not in (None, "정규직"):
        return {**base, "type": "not_regular", "seeker_text": "정규직 공고가 아니라서 채용지원금 연계 대상이 아니에요."}
    hrs, wage = post.get("weekly_hours"), post.get("wage")
    if isinstance(hrs, (int, float)) and hrs < WEEKLY_MIN:
        return {**base, "type": "condition_fail", "seeker_text": f"주 {hrs}시간 근무라 채용지원금 요건(주 {WEEKLY_MIN}시간 이상)에 해당하지 않아요."}
    if isinstance(wage, (int, float)) and wage > WAGE_MAX:
        return {**base, "type": "condition_fail", "seeker_text": "월 급여가 450만원을 넘어 채용지원금 요건(평균 월 급여 450만원 이하)에 해당하지 않아요."}
    ind = str(post.get("industry") or "")
    if excluded_industry(ind):  # 지원 제외 업종: 채용 공고는 추천하되 지원제도 표시는 하지 않음
        return {**base, "type": "excluded_industry", "seeker_text": "이 기업은 채용지원금 지원 제외 업종이라 연계 대상이 아니에요. 채용 공고 자체는 지원할 수 있어요."}
    if post.get("arrears") or post.get("tax_arrears"):
        return {**base, "type": "company_restricted", "seeker_text": "이 기업은 지원 제한 사유(임금체불·체납)가 확인되어 채용지원금 연계 표시를 하지 않아요."}
    if post.get("priority") is False:
        return {**base, "type": "company_not_eligible", "seeker_text": "이 기업은 우선지원대상기업이 아니어서 채용지원금 연계가 어려울 수 있어 표시하지 않아요."}
    n = post.get("insured")
    if isinstance(n, int) and n < 5:  # 공고 점검의 '확인 필요'와 맞춤: 기업 요건이 확인되지 않으면 배지도 달지 않는다
        return {**base, "type": "company_check", "seeker_text": "기업 요건(기준 피보험자 수 5인 이상, 일부 업종 예외)을 확인해야 해서 표시하지 않아요."}
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
            + (f" (청년 연령은 채용일 기준 예상 — {MIL_NOTE})" if mil else "")
            + " 사전 안내이며, 기업의 사업 참여신청·나머지 요건·실제 고용유지까지 확인돼야 지원이 결정돼요."
            + ("" if consent else " 지금은 동의하지 않아 기업 화면에 표시되지 않아요."))
    return {**base, "type": "capital_eligible", "eligible": True, "badge": bool(consent), "reason": kind + (" · 군필 연령 연동" if mil else ""), "seeker_text": text}


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
    add(OK if et == "정규직" else BAD if et else CHECK, "고용형태", "정규직 채용" if et == "정규직"
        else f"'{et or '미기재'}' — 기간의 정함 없는 계약이 원칙 (수습 3개월 이내·기간제 후 3개월 이내 정규직 전환 등 예외는 지침 Ⅲ-3-1 확인)")

    pr = post.get("priority")
    add(OK if pr else CHECK, "우선지원대상기업",
        "우선지원대상기업" if pr else ("우선지원대상기업이 아님 — 지원 제외 또는 예외 업종 여부를 지침으로 확인" if pr is False else "정보 없음 — 기업 규모 확인 필요"))

    n = post.get("insured")
    if n is None:
        add(CHECK, "피보험자 수", "정보 없음 — 피보험자 수 5인 이상인지 확인")
    else:
        add(OK if n >= 5 else CHECK, "피보험자 수", f"{n}명" + ("" if n >= 5 else " — 5인 미만은 일부 예외 업종만 가능하니 지침 확인"))

    whole = lambda v: int(v) if isinstance(v, float) and v.is_integer() else v  # noqa: E731 — 계약서 값(2300000.0)을 '2,300,000원'으로
    wage, raw_hrs = whole(post.get("wage")), whole(post.get("weekly_hours"))
    hrs = raw_hrs or 40
    if isinstance(raw_hrs, (int, float)):
        add(OK if raw_hrs >= WEEKLY_MIN else BAD, "주 소정근로시간",
            f"주 {raw_hrs}시간" + ("" if raw_hrs >= WEEKLY_MIN else f" — 주 {WEEKLY_MIN}시간 미만은 지원 대상 아님"), GUIDE_HIRE)
    else:
        add(CHECK, "주 소정근로시간", f"미기재 — 주 {WEEKLY_MIN}시간 이상인지 확인", GUIDE_HIRE)
    rate = MIN_WAGE.get(date.today().year) or MIN_WAGE[max(MIN_WAGE)]
    if wage:
        need, ok_w = round(rate * monthly_hours(hrs)), min_wage_ok(wage, hrs, rate)
        add(OK if ok_w else BAD, "임금(최저임금)",
            f"월 {wage:,}원 " + ("≥" if ok_w else "<") + f" 최저 월 {need:,}원 [최저임금 {rate:,}원 × {monthly_hours(hrs)}시간]"
            + ("" if ok_w else f" — 환산 시급 {wage / monthly_hours(hrs):,.0f}원"), "최저임금법 제6조")
        add(OK if wage <= WAGE_MAX else BAD, "월 급여 상한",
            f"월 {wage:,}원" + (" ≤ 450만원" if wage <= WAGE_MAX else " — 평균 월 급여 450만원 초과는 지원 대상 아님"), GUIDE_HIRE)
    else:
        add(CHECK, "임금(최저임금)", "임금 정보 없음", "최저임금법 제6조")

    if post.get("arrears"):
        add(BAD, "임금체불 명단공개", "명단공개 사업주에 해당 — 지원 제한 대상 여부 확인, 구직자 추천에서 제외", "고용24 임금체불 명단공개 사업주 여부")
    elif post.get("arrears") is False:
        add(OK, "임금체불 명단공개", "해당 없음", "고용24 임금체불 명단공개 사업주 여부")
    else:
        add(INFO, "임금체불 명단공개", "고용24 OpenAPI 연동 후 자동 확인", "고용24 임금체불 명단공개 사업주 여부")

    ind = str(post.get("industry") or "")
    if ind:
        hit = excluded_industry(ind)
        add(BAD if hit else OK, "업종", f"'{ind}' — 지원 제외 업종에 해당 (지침 원문으로 최종 확인)" if hit
            else f"{ind} — 자동 점검한 주요 제외 업종(유흥·사행 등)에 해당 없음, 업종코드로 최종 확인", f"{GUIDE} Ⅱ-2-1 지원 제외 업종")

    if post.get("tax_arrears"):
        add(BAD, "고액·상습 체납", "고액·상습 체납 명단(모의)에 해당 — 이음24 자체 기준으로 구직자 추천에서 제외. 지침상 제한 사유는 고용보험료 체납(Ⅱ-2-6)이므로 별도 확인",
            "이음24 추천 기준 (국세청 고액·상습체납자 명단공개 모의)")

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
            "state": "6개월 경과 — 1회차 지급신청 검토" if left <= 0 else "6개월 임박" if left <= 7 else "고용유지 중",
            "note": "사업 참여신청을 마친 기업이 6개월 고용유지 후 1회차 지급신청. 지급신청 기한은 지침 Ⅲ-4-1 확인, 실제 고용유지는 담당자 확인"}
