"""공고 매칭(코드 계산)과 AI 문장 검증 가드."""
import re
from datetime import date

from labor import MIN_WAGE, monthly_hours
from rules import d

STOP = {"및", "등", "과정", "관련", "직무", "실무", "기초", "담당", "신입", "사원", "관리"}


def persona_text(p: dict, extra: str = "") -> str:
    acts = " ".join(a["name"] for a in p.get("activities") or [])
    return f"{acts} {p.get('desire', {}).get('job', '')} {extra}"


def _words(s: str) -> set[str]:
    return {w for w in re.split(r"[\s·,/()\[\]:]+", s) if len(w) > 1 and w not in STOP}


def rank(postings: list[dict], profile_text: str, job: str, region: str, today: date | None = None, limit: int = 5):
    """희망 직무·지역과 참여 이력 키워드로 점수 계산. 임금체불 명단공개·마감 공고는 제외."""
    today = today or date.today()
    blob = profile_text.lower()
    job_words = _words(job)
    ranked, excluded = [], {"arrears": 0, "closed": 0, "min_wage": 0}
    rate = MIN_WAGE.get(today.year) or MIN_WAGE[max(MIN_WAGE)]
    for p in postings:
        if p.get("arrears"):
            excluded["arrears"] += 1
            continue
        if p.get("wage") and p["wage"] / monthly_hours(p.get("weekly_hours") or 40) + 0.5 < rate:
            excluded["min_wage"] += 1  # 최저임금 미달로 보이는 공고는 추천하지 않음
            continue
        if d(p.get("close")) and d(p["close"]) < today:
            excluded["closed"] += 1
            continue
        skills = [s for s in p.get("skills") or [] if s.lower() in blob]
        jobhit = sum(1 for w in job_words if w in f"{p.get('job', '')} {p.get('title', '')}")
        reg = 1 if region and region != "무관" and str(p.get("region", "")).startswith(region) else 0
        score = len(skills) * 2 + jobhit * 3 + reg * 2
        if skills or jobhit:  # 지역만 맞는 공고는 추천하지 않음
            ranked.append({"post": p, "score": score, "matched": skills, "region_match": bool(reg)})
    ranked.sort(key=lambda r: (-r["score"], r["post"]["id"]))
    return ranked[:limit], excluded


# AI가 써서는 안 되는 내용: 지원금·자격 판단과 연령은 규칙엔진·고용센터 몫이고, 기업 차별 우려가 있다.
FORBIDDEN = re.compile(r"장려금|지원금|수급|자격 요건|취업애로|연령|나이|\d+\s*세")


THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")


def _ints(s: str) -> set[int]:
    """문장 속 숫자를 정수 집합으로 (천 단위 쉼표 제거, '2026.08'·'2026-08'은 2026과 8로 나눔)."""
    return {int(n) for n in re.findall(r"\d+", THOUSANDS.sub("", s))}


def guard(text: str, source: str, limit: int = 300, forbid: bool = True) -> str | None:
    """AI 문장 검증: 금지 내용이 있거나(forbid=True일 때), 입력에 없던 숫자가 새로 나오면 None(차단)."""
    t = str(text or "").strip()[:limit]
    if not t or (forbid and FORBIDDEN.search(t)):
        return None
    if not _ints(t) <= _ints(source):
        return None
    return t
