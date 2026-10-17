"""이음24 MVP 사전 검증 (합성데이터) — 서비스 기획서의 검증 지표를 실제 코드로 측정한다. AI 호출 없음(토큰 0).

실행: python3 tools/eval_mvp.py   → 결과를 표준출력과 tools/eval_result.md 로 남긴다.

1. 배지 판정 일치율: 합성 지원자 100명 × 공고 조건을 '지침 정답표'(시나리오별로 미리 정한 정답)와 비교
2. 근로계약 의도적 오류 탐지율: 오류 6종을 심은 계약 60건 + 정상 계약 40건(경계값 포함)
3. 기업 화면 노출 점검: 배지 대상자의 기업 화면 응답에 연령·참여 사업명·사유가 없는지
4. AI 문장 차단: 근거 없는 숫자·지원금·연령 언급 문장 차단율, 정상 문장 통과율
5. 목록 제한: 후보에 없는 사업 ID를 AI가 답했을 때 제거율
"""
import json
import os
import random
import sys
os.environ["IEUM_BUILTIN_ONLY"] = "1"  # data/synthetic 파일과 무관하게 내장 합성데이터로 검증
from datetime import date
from itertools import product

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
sys.path.insert(0, os.path.join(ROOT, "api"))

import rules  # noqa: E402
import labor  # noqa: E402
from match import guard  # noqa: E402
from userinput import has_program_words  # noqa: E402

rnd = random.Random(2026)

# ───────── 1. 배지 판정 ─────────
# 이력 시나리오와 '취업애로청년 근거' 정답 (2026 지침 Ⅲ-1-3: 국민취업지원제도 참여 후 최초 취업 / 청년도전지원사업 수료)
HIST = {
    "국취 참여·이후 취업 이력 없음": (lambda: {"programs": [{"type": "국민취업지원제도", "qualified": "2026-03-02", "iap": "2026-03-16"}], "insurance": []}, True),
    "국취 참여·참여 전에만 취업": (lambda: {"programs": [{"type": "국민취업지원제도", "qualified": "2026-03-02", "iap": "2026-03-16"}], "insurance": [{"acquired": "2024-05-01", "lost": "2025-02-28"}]}, True),
    "국취 참여·참여 후 이미 취업": (lambda: {"programs": [{"type": "국민취업지원제도", "qualified": "2026-03-02", "iap": "2026-03-16"}], "insurance": [{"acquired": "2026-06-01", "lost": "2026-08-31"}]}, False),
    "국취 자격만·취업활동계획 없음": (lambda: {"programs": [{"type": "국민취업지원제도", "qualified": "2026-03-02"}], "insurance": []}, False),
    "청년도전 수료": (lambda: {"programs": [{"type": "청년도전지원사업", "started": "2026-03-01", "completed": "2026-08-29"}], "insurance": []}, True),
    "청년도전 참여 중(미수료)": (lambda: {"programs": [{"type": "청년도전지원사업", "started": "2026-07-01"}], "insurance": []}, False),
    "참여 이력 없음": (lambda: {"programs": [], "insurance": []}, False),
    "국취 이후 취업 + 청년도전 수료": (lambda: {"programs": [{"type": "국민취업지원제도", "qualified": "2025-09-01", "iap": "2025-09-10"}, {"type": "청년도전지원사업", "started": "2026-03-01", "completed": "2026-08-29"}], "insurance": [{"acquired": "2025-11-01", "lost": "2026-01-31"}]}, True),
}
AGES = [15, 22, 34, 35, 41]                     # 경계값: 15·34 포함, 35부터 청년 아님
REGIONS = {"서울 마포구": True, "경기 성남시": True, "인천 남동구": True, "경북 구미시": False, "부산 강서구": False, "": None}
EMP = ["정규직", "계약직"]
PRIORITY = [True, False]


def truth(hist_ok, age, cap, emp, pri):
    """지침 정답표: 수도권 + 정규직 + 우선지원대상 + 만 15~34세 + 취업애로 근거 → 배지 대상. 비수도권은 공고 단위 안내(개인 배지 없음)."""
    if emp != "정규직" or pri is False:
        return False, "대상 아님(고용형태·기업)"
    if cap is None:
        return False, "판단 보류(지역 미상)"
    if cap is False:
        return False, "비수도권(공고 단위 안내)"
    ok = 15 <= age <= 34 and hist_ok
    return ok, "수도권 취업애로청년" if ok else "수도권·근거 없음"


grid = list(product(HIST.items(), AGES, REGIONS.items(), EMP, PRIORITY))
rnd.shuffle(grid)
# 경계 조합이 빠지지 않게: 수도권·정규직·우선지원 조합을 먼저 40건 채우고 나머지 60건은 무작위
core_cases = [g for g in grid if g[2][1] is True and g[3] == "정규직" and g[4] is True][:40]
rest = [g for g in grid if g not in core_cases][:60]
cases = core_cases + rest

badge_rows, wrong, leaks, consent_off_badges = [], [], 0, 0
for n, ((hname, (mk, hok)), age, (region, cap), emp, pri) in enumerate(cases, 1):
    person = {"id": f"S-{n:03d}", "alias": f"합성 {n}", "age": age, **mk()}
    post = {"region": region, "emp_type": emp, "priority": pri}
    exp, why = truth(hok, age, cap, emp, pri)
    got = rules.judge(person, post, consent=True)
    off = rules.judge(person, post, consent=False)
    consent_off_badges += bool(off["badge"])
    if bool(got["badge"]) != exp:
        wrong.append({"case": n, "hist": hname, "age": age, "region": region or "미상", "emp": emp, "priority": pri, "expected": exp, "got": got["badge"], "type": got["type"]})
    # 기업 화면 노출 점검 (배지 대상자만)
    if got["badge"]:
        from employer import employer_view  # noqa: E402
        app = {**person, "consent": True, "headline": f"{hname} 경험을 살린 지원자", "points": ["국민취업지원제도 상담으로 진로 설정", "엑셀 실무 과정 수료"], "applied": "2026-10-20"}
        view = employer_view(app, post)
        text = json.dumps(view, ensure_ascii=False)
        if "age" in view or "reason" in view or has_program_words(text) or str(age) + "세" in text:
            leaks += 1
    badge_rows.append(exp)

badge_total = len(cases)
badge_acc = (badge_total - len(wrong)) / badge_total * 100

# ───────── 2. 근로계약 오류 탐지 ─────────
RATE = labor.MIN_WAGE[2026]
BASE = {"employment_type": "정규직", "weekly_hours": 40, "daily_hours": 8, "break_minutes": 60, "base_wage": 2600000, "wage_type": "월급",
        "start_date": "2026-11-01", "has_holiday": True, "has_leave": True, "has_place": True, "has_job": True, "has_payday": True}
MIN_MONTH = RATE * labor.monthly_hours(40)  # 2,156,880
ERRORS = {
    "최저임금 미달": lambda f, i: {**f, "base_wage": MIN_MONTH - (i + 1) * 1000},
    "휴게시간 부족": lambda f, i: {**f, "daily_hours": 8, "break_minutes": [0, 30, 45, 50, 59][i % 5]},
    "주 40시간 초과": lambda f, i: {**f, "weekly_hours": 41 + i, "daily_hours": 8},
    "1일 8시간 초과": lambda f, i: {**f, "daily_hours": 8.5 + i * 0.5, "break_minutes": 60},
    "필수 기재사항 누락": lambda f, i: {**f, ["has_holiday", "has_leave", "has_place", "has_job", "has_payday"][i % 5]: False},
    "기간제 종료일 없음": lambda f, i: {**f, "employment_type": "기간제"},
}
ITEM = {"최저임금 미달": "최저임금", "휴게시간 부족": "휴게시간", "주 40시간 초과": "주 소정근로시간", "1일 8시간 초과": "1일 소정근로시간",
        "필수 기재사항 누락": "필수 기재사항", "기간제 종료일 없음": "근로계약기간"}
contract_rows, missed = [], []
for kind, mk in ERRORS.items():
    for i in range(10):
        f = mk(dict(BASE), i)
        res = labor.check(f, today=date(2026, 10, 11))
        hit = any(r["item"] == ITEM[kind] and r["level"] in (labor.VIOLATION, labor.CHECK) for r in res)
        contract_rows.append((kind, hit))
        if not hit:
            missed.append({"kind": kind, "input": {k: f[k] for k in f if f[k] != BASE.get(k)}})
clean_fp = 0
CLEAN = [MIN_MONTH, MIN_MONTH + 1, 2300000, 2600000, 3200000]
for i in range(40):
    f = {**BASE, "base_wage": CLEAN[i % 5], "daily_hours": [8, 8, 7.5, 6, 4][i % 5], "break_minutes": [60, 90, 30, 30, 30][i % 5],
         "weekly_hours": [40, 40, 37.5, 30, 20][i % 5]}
    if f["weekly_hours"] < 40:
        f["base_wage"] = max(f["base_wage"], RATE * labor.monthly_hours(f["weekly_hours"]))
    res = labor.check(f, today=date(2026, 10, 11))
    if any(r["level"] == labor.VIOLATION for r in res):
        clean_fp += 1
detect = sum(h for _, h in contract_rows) / len(contract_rows) * 100

# ───────── 3. AI 문장 차단 ─────────
SOURCE = "웹 프론트엔드 개발자 양성과정 480시간 수료(2026.09), React로 지역 축제 안내 웹앱 화면 구현, 진로상담 5회"
BAD = ["이 지원자를 채용하면 장려금을 받을 수 있습니다.", "만 27세 청년으로 지원금 대상입니다.", "React 경력 3년의 숙련 개발자입니다.",
       "480시간 과정을 수료하고 프로젝트 12건을 완수했습니다.", "월 600만원 지원 가능 인재입니다.", "취업애로 요건을 충족한 지원자입니다.",
       "나이가 젊어 성장 가능성이 높습니다.", "수급 자격이 있어 기업 부담이 줄어듭니다.", "TOEIC 900점 수준의 영어 실력을 갖췄습니다.",
       "2025년부터 실무 경험 2년을 쌓았습니다."]
GOOD = ["480시간 웹 프론트엔드 과정을 수료하며 HTML·CSS·JavaScript를 익혔습니다.", "React로 지역 축제 안내 웹앱의 화면을 직접 구현했습니다.",
        "진로상담 5회로 웹 개발 직무 목표를 구체화했습니다.", "팀 프로젝트에서 화면 설계와 구현을 맡았습니다.", "2026년 9월 과정을 마치고 바로 실무에 투입될 준비가 되어 있습니다."]
bad_blocked = sum(guard(t, SOURCE) is None for t in BAD)
good_passed = sum(guard(t, SOURCE) is not None for t in GOOD)

# ───────── 4. 목록 제한 (공고 추천: 후보 목록 밖 ID 차단) ─────────
sys.path.insert(0, os.path.join(ROOT, "api"))
import seeker as _sk  # noqa: E402
from synthetic import PERSONAS  # noqa: E402
from userinput import parse_seeker, persona_to_form  # noqa: E402
_form = {**persona_to_form(PERSONAS[0]), "agree_privacy": True, "agree_ai": True, "consent": True}
_prof = parse_seeker(_form)
_cands = [r["post"]["id"] for r in _sk.rank(_sk.load_postings()[0], _prof["experience"], _prof["desire"]["job"], _prof["desire"]["region"])[0]]
fake = [f"FAKE-{i}" for i in range(6)]
_sk.provider = lambda: "claude"
_sk.generate_json = lambda *a, **k: {"picks": [{"id": x, "reason": "웹 개발 과정을 수료했습니다."} for x in _cands[:2] + fake]}
_out = _sk.run(_prof)
kept_fake = [j["id"] for j in _out["jobs"] if j["id"] not in _cands]
dropped = _out["meta"]["guard_blocked"]

# ───────── 5. 월별 서류 점검 (판독값 기준 규칙 점검) ─────────
from claimdocs import check_month  # noqa: E402
DOC_ERR = {
    "실지급액·이체액": lambda p, t, i: (p, {**t, "amount": str(int(t["amount"]) - (i + 1) * 10_000)}),
    "성명": lambda p, t, i: (p, {**t, "recipient": "박가람"}),
    "귀속월": lambda p, t, i: ({**p, "ym": "2026-0" + str(4 + i % 3)}, t),
    "최저임금": lambda p, t, i: ({**p, "gross": str(MIN_MONTH - (i + 1) * 5_000)}, t),
    "평균 월 급여 상한": lambda p, t, i: ({**p, "gross": str(4_600_000 + i * 10_000)}, t),
}
doc_rows, doc_fp = [], 0
for kind, mk in DOC_ERR.items():
    for i in range(10):
        p0 = {"name": "김가람", "ym": "2026-07", "gross": "2800000", "net": "2472510"}
        t0 = {"recipient": "김가람", "amount": "2472510", "date": "2026-08-10"}
        ps, tr = mk(p0, t0, i)
        if kind == "평균 월 급여 상한":
            tr = {**tr}
        res = check_month("2026-07", ps, tr, {"worker": "김가람", "weekly_hours": 40, "history": [{"ym": "2026-06", "gross": ps["gross"]}]})
        doc_rows.append((kind, any(x["item"] == kind and x["level"] == "불일치" for x in res["items"])))
for i in range(50):
    g = [MIN_MONTH, 2_300_000, 2_800_000, 3_500_000, 4_500_000][i % 5]
    res = check_month("2026-07", {"name": "김가람", "ym": "2026-07", "gross": str(g), "net": str(g - 300_000)},
                      {"recipient": "김 가람", "amount": f"{g - 300_000:,}", "date": "2026-08-10"},
                      {"worker": "김가람", "weekly_hours": 40, "history": [{"ym": "2026-06", "gross": g}]})
    doc_fp += res["level"] != "일치"
doc_detect = sum(h for _, h in doc_rows) / len(doc_rows) * 100

# ───────── 결과 ─────────
from collections import Counter  # noqa: E402
by_kind = Counter(k for k, h in contract_rows if h)
report = f"""# 이음24 MVP 사전 검증 결과 (합성데이터, {date.today().isoformat()})

AI 호출 없이 규칙엔진·검증 코드만으로 측정. 재현: `python3 tools/eval_mvp.py`

| 지표 | 목표(기획서) | 측정 결과 |
|---|---|---|
| 배지 판정 일치율 (지침 정답표 대비) | 98% 이상 | **{badge_acc:.1f}%** ({badge_total - len(wrong)}/{badge_total}건) |
| 동의 철회 시 배지 노출 | 0건 | **{consent_off_badges}건** |
| 근로계약 의도적 오류 탐지율 | 95% 이상 | **{detect:.1f}%** ({sum(h for _, h in contract_rows)}/{len(contract_rows)}건) |
| 정상 계약 오탐(위반 의심 표시) | — | **{clean_fp}/40건** (경계값: 최저임금 정확히 {MIN_MONTH:,}원 포함) |
| 기업 화면 사유·연령·참여사업명 노출 | 0건 | **{leaks}건** (배지 대상 {sum(badge_rows)}명 점검) |
| AI 문장: 근거 없는 수치·지원금·연령 차단 | 100% | **{bad_blocked}/{len(BAD)}건 차단** |
| AI 문장: 정상 문장 통과 | — | **{good_passed}/{len(GOOD)}건 통과** |
| 추천 공고 중 후보 목록 외 ID | 0건 잔존 | **{len(kept_fake)}건 잔존** (AI가 낸 목록 외 ID {len(fake)}건 차단) |
| 월별 서류 의도적 불일치 탐지율 (판독값 기준, 5종 × 10건) | 95% 이상 | **{doc_detect:.1f}%** ({sum(h for _, h in doc_rows)}/{len(doc_rows)}건) |
| 정상 월별 서류 오탐 | — | **{doc_fp}/50건** |

## 배지 판정 표본 구성 (100명)
- 이력 시나리오 {len(HIST)}종: {", ".join(HIST)}
- 연령 {AGES} (경계 15·34·35세 포함), 지역 수도권 3·비수도권 2·미상 1, 고용형태 정규직/계약직, 우선지원대상 여부
- 정답 배지 대상 {sum(badge_rows)}명 / 비대상 {badge_total - sum(badge_rows)}명

## 계약 오류 유형별 탐지 (각 10건)
{chr(10).join(f"- {k}: {by_kind.get(k, 0)}/10" for k in ERRORS)}
"""
if wrong:
    report += "\n## 배지 불일치 사례\n" + "\n".join(json.dumps(w, ensure_ascii=False) for w in wrong) + "\n"
if missed:
    report += "\n## 계약 오류 미탐지 사례\n" + "\n".join(json.dumps(m, ensure_ascii=False) for m in missed) + "\n"
print(report)
with open(os.path.join(ROOT, "tools", "eval_result.md"), "w", encoding="utf-8") as fp:
    fp.write(report)
