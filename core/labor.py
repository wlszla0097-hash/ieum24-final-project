"""근로계약 조건 1차 점검 (규칙 기반). 판단은 코드가, AI는 결과 설명만 한다."""
from datetime import date

from common import num

MIN_WAGE = {2024: 9860, 2025: 10030, 2026: 10320}  # 시급(원). 매년 고시 후 추가
VIOLATION, CHECK, OK = "위반 의심", "확인 필요", "적정"


def monthly_hours(weekly: float) -> int:
    """월 환산 유급시간 = (주 소정근로시간 + 주휴시간) × 365/7/12. 주 40시간 → 209시간."""
    weekly = min(weekly, 40)
    holiday = weekly / 40 * 8 if weekly >= 15 else 0
    return round((weekly + holiday) * 365 / 7 / 12)


def check(f: dict, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []

    def add(level, item, detail, basis):
        out.append({"level": level, "item": item, "detail": detail, "basis": basis})

    etype = f.get("employment_type") or "정규직"
    weekly, daily, brk = num(f.get("weekly_hours")), num(f.get("daily_hours")), num(f.get("break_minutes"))
    wage, allow = num(f.get("base_wage")), num(f.get("allowances")) or 0
    wtype = f.get("wage_type") or "월급"
    try:
        year = int(str(f.get("start_date") or "")[:4]) or today.year
    except ValueError:
        year = today.year

    missing = [label for key, label in (("has_holiday", "주휴일"), ("has_leave", "연차유급휴가"), ("has_place", "근무 장소"), ("has_job", "업무 내용"), ("has_payday", "임금 지급일·방법")) if not f.get(key)]
    if missing:
        add(CHECK, "필수 기재사항", "계약서에서 확인되지 않음: " + ", ".join(missing), "근로기준법 제17조")
    else:
        add(OK, "필수 기재사항", "주휴일·연차·장소·업무·지급일 기재 확인", "근로기준법 제17조")

    if etype == "기간제" and not f.get("end_date"):
        add(VIOLATION, "근로계약기간", "기간제인데 계약 종료일이 없음", "기간제법 제17조")

    if weekly and weekly > 40:
        add(VIOLATION, "주 소정근로시간", f"주 {weekly:g}시간 — 법정 40시간 초과 (연장근로는 별도 합의, 주 12시간 한도)", "근로기준법 제50조·제53조")
    if daily and daily > 8:
        add(VIOLATION, "1일 소정근로시간", f"1일 {daily:g}시간 — 법정 8시간 초과", "근로기준법 제50조")

    if daily:
        need = 60 if daily >= 8 else 30 if daily >= 4 else 0
        if need and brk is None:
            add(CHECK, "휴게시간", f"1일 {daily:g}시간 근로 — 휴게 {need}분 이상 필요하나 미기재", "근로기준법 제54조")
        elif need and brk < need:
            add(VIOLATION, "휴게시간", f"휴게 {brk:g}분 — {need}분 이상 필요", "근로기준법 제54조")
        elif need:
            add(OK, "휴게시간", f"휴게 {brk:g}분 (기준 {need}분 이상)", "근로기준법 제54조")

    rate = MIN_WAGE.get(year)
    hourly, how = None, ""
    if wage is None:
        how = "기본급 미입력"
    elif wtype == "시급":
        hourly, how = wage, "시급"
    elif not weekly:
        how = "주 소정근로시간 미입력"
    else:
        monthly = (wage / 12 if wtype == "연봉" else wage) + allow
        hrs = monthly_hours(weekly)
        hourly, how = monthly / hrs, f"월 {monthly:,.0f}원 ÷ {hrs}시간"
    if hourly is None:
        add(CHECK, "최저임금", f"계산 불가 ({how})", "최저임금법 제6조")
    elif not rate:
        add(CHECK, "최저임금", f"{year}년 최저임금 미등록 — 고시 금액 확인 필요 (환산 시급 {hourly:,.0f}원)", "최저임금법 제6조")
    elif hourly + 0.5 < rate:
        need = f" — 월 환산 최소 {rate * monthly_hours(weekly):,}원 필요" if wtype != "시급" and weekly else ""
        add(VIOLATION, "최저임금", f"환산 시급 {hourly:,.0f}원 < {year}년 최저임금 {rate:,}원 [{how}]{need}", "최저임금법 제6조")
    else:
        add(OK, "최저임금", f"환산 시급 {hourly:,.0f}원 ≥ {year}년 최저임금 {rate:,}원 [{how}]", "최저임금법 제6조")

    if weekly and weekly >= 15 and not f.get("has_holiday"):
        add(CHECK, "주휴일", "주 15시간 이상 — 유급 주휴일 기재 필요", "근로기준법 제55조")
    return out
