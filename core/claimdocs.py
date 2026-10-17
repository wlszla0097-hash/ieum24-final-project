"""참여사업 관리 — 월별 서류(급여명세서·이체확인증) 사전 점검 (규칙엔진, AI 미사용).

기업이 매월 서류를 올리면 AI가 판독한 값(성명·귀속월·지급액·이체액 등)을 받아 그 달 기준으로 점검한다.
판단(지급 가능 여부)은 하지 않고, 서로 다른 값·빠진 달·지침 기준 미달만 목록으로 알린다.
신청 시기가 되면 이 결과가 담당자 확인 대시보드에 회차별로 모인다.

기준: 2026년 청년일자리도약장려금 운영지침(주 소정근로 28시간 이상, 평균 월 급여 450만원 이하,
      1회차 6개월 지급총액 2,700만원 이하), 최저임금법(연도별 최저임금).
"""
from datetime import date

from labor import MIN_WAGE, monthly_hours

MISMATCH, CHECK, MATCH = "불일치", "확인 필요", "일치"
GUIDE = "2026 청년일자리도약장려금 지침"
MAX_AVG = 4_500_000          # 평균 월 급여 상한
FIRST_ROUND_MAX = 27_000_000  # 1회차(6개월) 지급총액 상한


def _ym(s) -> str:
    s = str(s or "").strip().replace(".", "-").replace("/", "-")
    parts = [p for p in s.split("-") if p]
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[0]):04d}-{int(parts[1]):02d}"
    return ""


def _won(v) -> int | None:
    digits = "".join(ch for ch in str(v if v is not None else "") if ch.isdigit())
    return int(digits) if digits else None


def _name(v) -> str:
    return "".join(str(v or "").split())


def _one_off(a: str, b: str) -> bool:
    """글자 수가 같고 정확히 한 글자만 다름 — AI 판독에서 흔한 오독(다온→다운, 서연→시연)."""
    return len(a) == len(b) and len(a) >= 2 and sum(x != y for x, y in zip(a, b)) == 1


def _skeleton(ch: str):
    """한글 음절 → (초성, 종성). 모음만 다른 오독(온↔운, 물↔몰, 서↔시)을 같은 글자로 보기 위한 자음 골격."""
    c = ord(ch) - 0xAC00
    return (c // 588, c % 28) if 0 <= c < 11172 else ch


def _vowel_slip(a: str, b: str) -> bool:
    """글자 수가 같고, 다른 글자는 모두 한글 모음만 다름 — AI 한글 판독에서 가장 흔한 오차(다온물류 → 다운몰류)."""
    return len(a) == len(b) and a != b and all(x == y or (_skeleton(x) == _skeleton(y) and isinstance(_skeleton(x), tuple)) for x, y in zip(a, b))


CHO, JUNG, JONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ", "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ", " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def _jamo(s: str) -> str:
    out = []
    for ch in s:
        c = ord(ch) - 0xAC00
        out.append(CHO[c // 588] + JUNG[(c % 588) // 28] + JONG[c % 28].strip() if 0 <= c < 11172 else ch)
    return "".join(out)


def _dist(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _corp_slip(a: str, b: str) -> bool:
    """회사명 판독 오차: 같은 글자 수에서 자모 차이가 30% 이내(다온물류→다운몬류). 다온유통처럼 다른 회사는 걸러진다."""
    if len(a) != len(b) or len(b) < 3:
        return False
    ja, jb = _jamo(a), _jamo(b)
    return _dist(ja, jb) <= max(1, int(len(jb) * 0.3))


def _name_slip(a: str, b: str) -> bool:
    """사람 이름: 성(첫 글자)은 같고 이름 쪽 한 글자만 다름. 성이 다르면(김가람↔박가람) 다른 사람으로 본다."""
    return (_one_off(a, b) or _vowel_slip(a, b)) and a[:1] == b[:1]


def _corp(v) -> str:
    """회사명 비교용: 공백·(가상)·주식회사·(주) 표기를 뺀다."""
    s = _name(v)
    for w in ("(가상)", "주식회사", "(주)", "㈜"):
        s = s.replace(w, "")
    return s


def months_between(start_ym: str, end_ym: str) -> list[str]:
    """start_ym ~ end_ym (둘 다 포함) 월 목록."""
    y, m = map(int, start_ym.split("-"))
    ey, em = map(int, end_ym.split("-"))
    out = []
    while (y, m) <= (ey, em) and len(out) < 60:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fix_swap(transfer: dict, worker) -> tuple[dict, bool]:
    """급여 이체에서 근로자가 '보내는 분'일 수 없다 → AI가 보낸 분·받는 분을 바꿔 읽은 것으로 보고 바로잡는다."""
    w = _name(worker)
    if w and _name(transfer.get("sender")) == w and _name(transfer.get("recipient")) not in ("", w):
        return {**transfer, "sender": transfer.get("recipient"), "recipient": transfer.get("sender")}, True
    return transfer, False


def check_month(month: str, payslip: dict, transfer: dict, ctx: dict) -> dict:
    """한 달 서류 점검. ctx: {worker, hire_date, weekly_hours, history: [{ym, gross}] (이전 달까지 첨부분)}"""
    items = []

    def add(level, item, detail, basis=GUIDE):
        items.append({"level": level, "item": item, "detail": detail, "basis": basis})

    worker = _name(ctx.get("worker"))
    transfer, swapped = fix_swap(transfer, ctx.get("worker"))
    swapped = swapped or bool(ctx.get("swapped"))
    p_name, t_name = _name(payslip.get("name")), _name(transfer.get("recipient"))
    names = [n for n in (p_name, t_name) if n]
    if not names:
        add(CHECK, "성명", "서류에서 성명을 읽지 못함 — 원본 확인")
    elif worker and any(n != worker and not _name_slip(n, worker) for n in names):
        add(MISMATCH, "성명", f"근로자 {ctx.get('worker')} / 명세서 {payslip.get('name') or '-'} / 이체 받는 분 {transfer.get('recipient') or '-'}")
    elif worker and any(n != worker for n in names):  # 한 글자 차이: 판독 오차일 수도, 다른 사람일 수도 → 사람이 원본 확인
        add(CHECK, "성명", f"근로자 {ctx.get('worker')} / 이체 받는 분 {transfer.get('recipient') or '-'} — 한 글자 차이(판독 오차 가능), 원본 확인")
    elif p_name and t_name and p_name != t_name:
        add(MISMATCH, "성명", f"명세서 {payslip.get('name')} ≠ 이체 받는 분 {transfer.get('recipient')}")
    else:
        add(MATCH, "성명", f"{payslip.get('name') or transfer.get('recipient')} — 명세서·이체확인증 일치")

    if swapped:  # 판독 오류일 수도, 실제 근로자→회사 이체(반환 등)일 수도 있다 → 자동으로 정상 처리하지 않음
        add(CHECK, "이체 방향", "보내는 분이 근로자로 읽힘 — 보내는 분·받는 분을 바꿔 비교했지만, 판독 오류인지 실제 근로자→회사 이체인지 원본 확인 필요",
            "이음24 판독 점검 (원래 판독값 보존)")
    company = _corp(ctx.get("company"))
    if company:  # 이체자(보내는 분) = 사업주(회사) 명의인지 — 회사명을 알 때만 점검
        sender = _corp(transfer.get("sender"))
        if not sender:
            add(CHECK, "이체자(보내는 분)", "이체확인증에서 보내는 분을 읽지 못함 — 원본 확인")
        elif company in sender or sender in company:
            add(MATCH, "이체자(보내는 분)", f"{transfer.get('sender')} — 사업주(회사) 명의 계좌에서 이체")
        elif len(company) >= 3 and _vowel_slip(sender, company):  # 모음만 다름(다온물류→다운몰류): 한글 판독의 전형적 오차
            add(MATCH, "이체자(보내는 분)", f"{transfer.get('sender')} — 회사 {ctx.get('company')}와 모음만 다름(판독 오차로 보고 일치 처리, 원본 확인 권장)")
        elif len(company) >= 3 and (_one_off(sender, company) or _corp_slip(sender, company)):  # 자음까지 다르면 다른 회사일 수 있음
            add(CHECK, "이체자(보내는 분)", f"보내는 분 {transfer.get('sender')} — 회사 {ctx.get('company')}와 비슷하지만 다른 글자 있음(판독 오차 또는 다른 회사), 원본 확인")
        else:
            add(CHECK, "이체자(보내는 분)", f"보내는 분 {transfer.get('sender')} ≠ 회사 {ctx.get('company')} — 대표자 개인 계좌 등 사업주 명의가 아닌 지급인지 확인")

    p_ym = _ym(payslip.get("ym"))
    add(MATCH if p_ym == month else MISMATCH if p_ym else CHECK, "귀속월",
        f"명세서 귀속월 {p_ym or '판독 안 됨'}" + ("" if p_ym == month else f" — 첨부한 달은 {month}"))

    net, amount = _won(payslip.get("net")), _won(transfer.get("amount"))
    if net is None or amount is None:
        add(CHECK, "실지급액·이체액", "금액을 읽지 못함 — 원본 확인")
    elif net == amount:
        add(MATCH, "실지급액·이체액", f"실지급 {net:,}원 = 이체 {amount:,}원")
    else:
        add(MISMATCH, "실지급액·이체액", f"실지급 {net:,}원 ≠ 이체 {amount:,}원 (차이 {abs(net - amount):,}원) — 분할 지급·정정 여부 확인")

    t_date = str(transfer.get("date") or "")
    if not _ym(t_date):
        add(CHECK, "이체일", "이체일을 읽지 못함 — 원본 확인 (지급일 확인 없이 일치 처리하지 않음)")
    elif _ym(t_date) < month:
        add(CHECK, "이체일", f"이체일 {t_date}이 귀속월({month})보다 앞섬 — 선지급 여부 확인")

    gross = _won(payslip.get("gross"))
    year = int(month[:4])
    rate, weekly = MIN_WAGE.get(year), float(ctx.get("weekly_hours") or 40)
    if gross is None:
        add(CHECK, "최저임금", "지급총액을 읽지 못함", "최저임금법 제6조")
    elif not rate:
        add(CHECK, "최저임금", f"{year}년 최저임금 미등록 — 고시 금액 확인", "최저임금법 제6조")
    else:
        need = rate * monthly_hours(weekly)
        pr, part = ctx.get("prorate"), ""
        if pr:  # 월 중간 입사·종료 달은 근무한 날만큼 일할한 금액과 비교
            need, part = need * pr["days"] // pr["dim"], f", 일할 {pr['days']}/{pr['dim']}일"
        add(MATCH if gross >= need else MISMATCH, "최저임금",
            f"지급총액 {gross:,}원 {'≥' if gross >= need else '<'} 월 환산 {need:,}원 (주 {weekly:g}시간, {year}년 {rate:,}원{part}) — 산입범위는 원본으로 확인",
            "최저임금법 제6조")

    hist = [h for h in (ctx.get("history") or []) if _won(h.get("gross")) is not None and h.get("ym") != month]
    grosses = [_won(h["gross"]) for h in hist] + ([gross] if gross is not None else [])
    if grosses:
        avg = sum(grosses) // len(grosses)
        add(MATCH if avg <= MAX_AVG else MISMATCH, "평균 월 급여 상한", f"지금까지 {len(grosses)}개월 평균 {avg:,}원 (상한 {MAX_AVG:,}원)")
        if len(grosses) <= 6:
            total = sum(grosses)
            add(MATCH if total <= FIRST_ROUND_MAX else MISMATCH, "1회차 지급총액",
                f"{len(grosses)}개월 누적 {total:,}원 (1회차 6개월 상한 {FIRST_ROUND_MAX:,}원)")

    worst = MISMATCH if any(i["level"] == MISMATCH for i in items) else CHECK if any(i["level"] == CHECK for i in items) else MATCH
    return {"month": month, "level": worst, "items": items}


def missing_months(hire_date: str, uploaded: list[str], today: date | None = None) -> list[str]:
    """입사월부터 지난달까지 중 서류가 없는 달 (급여 지급 전인 이번 달은 제외)."""
    today = today or date.today()
    last = f"{today.year - 1:04d}-12" if today.month == 1 else f"{today.year:04d}-{today.month - 1:02d}"
    start = _ym(hire_date)
    if not start or start > last:
        return []
    return [m for m in months_between(start, last) if m not in set(uploaded)]
