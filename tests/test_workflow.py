"""시연 흐름(저장 → 지원 → 채용 확정 → 근로계약 → 급여명세서 대조) 서버 쪽 테스트. AI 호출 없음."""
import base64
import os
import sys
from datetime import date
from pathlib import Path

os.environ["IEUM_BUILTIN_ONLY"] = "1"
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "VERCEL"):
    os.environ.pop(k, None)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "core"))

import pytest  # noqa: E402

import cases  # noqa: E402
import certificate  # noqa: E402
import employer  # noqa: E402
import labor  # noqa: E402
import seeker  # noqa: E402
import demostore as store  # noqa: E402  (api/store.py 와 이름이 겹치지 않게)
from common import ApiError  # noqa: E402
from userinput import parse_posting  # noqa: E402

SEEK = {"alias": "정다온", "agree_privacy": True, "youth": True, "experience": "- 웹 개발 과정 수료 (HTML, CSS, JavaScript, React)\n- 팀 프로젝트 화면 담당",
        "job": "웹 개발", "region": "무관", "dojeon": True, "dojeon_completed": "2026-05-29", "consent": True, "agree_detail": True,
        "points": ["웹 개발 과정 수료", "팀 프로젝트 화면 담당"], "portfolio": "웹 개발 과정에서 화면을 맡았습니다."}
POST = {"company": "한빛소프트랩(가상)", "busino": "000-81-00012", "sido": "서울", "sigungu": "마포구", "title": "웹 개발자 신입 React", "job": "웹 개발",
        "emp_type": "정규직", "wage": "2,800,000", "weekly_hours": 40, "priority": "예", "description": "React 화면 개발", "close": "2026-12-31"}


def test_store_memory_roundtrip_and_limits():
    store.reset()
    store.put("applications", "U-1~abc", {"posting_id": "U-1", "seeker_id": "abc"})
    assert store.get("applications", "U-1~abc")["seeker_id"] == "abc"
    assert [x["id"] for x in store.list_items("applications")] == ["U-1~abc"]
    with pytest.raises(ApiError):
        store.put("unknown", "x", {})
    with pytest.raises(ApiError):
        store.put("seekers", "big", {"t": "가" * 20000})  # 묶음당 크기 제한
    store.put("contracts", "ct", {"sign": "x" * 50000})  # 서명 이미지가 들어가는 계약서는 크게 허용
    store.reset()
    assert store.list_items("applications") == []


def test_store_off_on_vercel_without_redis(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert store.mode() == "off"
    with pytest.raises(ApiError) as e:
        store.put("seekers", "a", {})
    assert e.value.code == "store_off"  # 화면은 브라우저 저장으로 전환


def test_employer_lists_companies_and_stored_applicants_without_ai():
    comps = employer.companies()
    assert comps and all(c["postings"] and c["postings"][0]["form"]["title"] for c in comps)
    r = employer.build({"posting": POST, "posting_id": "U-test", "analyze": False, "skills": ["React"],
                        "applicants_extra": [{"seeker_id": "abc", "alias": "정다온", "applied": "2026-10-15", "headline": "웹 개발 지망", "profile": SEEK}]})
    assert r["analysis"] is None and r["ai_error"] is None  # 공고 확인 화면은 AI를 다시 부르지 않음
    me = next(a for a in r["applicants"] if a["stored"])
    assert me["id"] == "U-test-Sabc" and me["alias"] == "정다온" and me["seeker_id"] == "abc"
    syn = next(a for a in r["applicants"] if a["id"] == "U-test-A")
    assert syn["alias"] == "지원자 A" and syn["hire_name"] == "강민서"  # 채용 전에는 '지원자 A', 계약서에는 가상 성명
    assert "청년도전" not in me["headline"] + me["portfolio"]


def test_case_for_stored_applicant_with_demo_as_of():
    post = parse_posting(POST)
    post["id"] = "U-test"
    app = cases.resolve_applicant(post, "U-test-Sabc", None, {"alias": "정다온", "profile": SEEK})
    assert app["alias"] == "정다온"
    hire = date(2026, 10, 15)
    now = cases.build_case(post, app, hire, today=hire)
    later = cases.build_case(post, app, hire, today=date(2027, 4, 15))
    assert now["schedule"]["months_kept"] == 0 and later["schedule"]["months_kept"] == 6
    assert later["schedule"]["state"] == "신청 가능"
    assert later["evidence"]["open"] and "청년도전지원사업" in later["evidence"]["title"]  # 수료일이 채용일보다 앞서고 세부정보 동의


def test_claimdoc_checks_issued_payslip_against_transfer_only():
    f = {"media_type": "image/jpeg", "data": base64.b64encode(b"x" * 10).decode()}
    issued = {"name": "정다온", "ym": "2026-11", "pay_date": "2026-12-10", "gross": "2800000", "deduction": "300000", "net": "2500000"}
    body = {"month": "2026-11", "files": [f], "issued_payslip": issued, "ctx": {"worker": "정다온", "hire_date": "2026-10-15", "weekly_hours": 40}}
    ok = certificate.claimdoc({**body, "sample_truth": {"transfer": {"recipient": "정다온", "date": "2026-12-10", "amount": "2500000", "sender": "회사"}}})
    assert ok["payslip_source"] == "issued" and ok["payslip"]["net"] == "2500000" and ok["check"]["level"] == "일치"
    short = certificate.claimdoc({**body, "sample_truth": {"transfer": {"recipient": "정다온", "date": "2026-12-10", "amount": "2470000", "sender": "회사"}}})
    assert {i["item"]: i["level"] for i in short["check"]["items"]}["실지급액·이체액"] == "불일치"
    with pytest.raises(ApiError):
        certificate.claimdoc({"month": "2026-11", "files": [f]})  # 발급 명세서가 없으면 두 장 필요


def test_employer_posted_jobs_reach_seeker_recommendations():
    from userinput import parse_seeker
    extra = seeker.extra_postings([{"id": "U-x", "form": POST, "skills": ["React"]}, {"id": "U-bad", "form": {"title": ""}}])
    assert [p["id"] for p in extra] == ["U-x"]  # 형식이 틀린 공고는 버림
    r = seeker.run(parse_seeker(SEEK), extra)
    job = next(j for j in r["jobs"] if j["id"] == "U-x")
    assert job["source"] == "employer" and job["busino"] == "0008100012"


def test_min_wage_2027_registered():
    assert labor.MIN_WAGE[2027] == 10700


def test_transfer_sender_and_recipient_checked():
    from claimdocs import check_month
    ps = {"name": "정다온", "ym": "2026-11", "gross": "2800000", "net": "2500000"}
    ctx = {"worker": "정다온", "company": "바른정밀(가상)", "weekly_hours": 40}
    lv = lambda tr: {i["item"]: i["level"] for i in check_month("2026-11", ps, tr, ctx)["items"]}  # noqa: E731
    ok = lv({"recipient": "정다온", "amount": "2,500,000원", "date": "2026-12-10", "sender": "주식회사 바른정밀"})
    assert ok["이체자(보내는 분)"] == "일치" and ok["성명"] == "일치" and ok["실지급액·이체액"] == "일치"
    assert lv({"recipient": "정다온", "amount": "2500000", "date": "2026-12-10", "sender": "김바른"})["이체자(보내는 분)"] == "확인 필요"
    assert lv({"recipient": "박서연", "amount": "2500000", "date": "2026-12-10", "sender": "바른정밀"})["성명"] == "불일치"
    no_company = {i["item"] for i in check_month("2026-11", ps, {"recipient": "정다온", "amount": "2500000"}, {"worker": "정다온"})["items"]}
    assert "이체자(보내는 분)" not in no_company  # 회사명을 모르면 점검하지 않음 (기존 월별 점검 호환)


def test_self_registered_company_industry_is_checked():
    from rules import posting_check
    p = parse_posting({**POST, "busino": "000-12-34567", "company": "새벽라운지(가상)", "industry": "일반 유흥 주점업"})
    assert p["lookup"].startswith("등록되지 않은") and p["industry"] == "일반 유흥 주점업"
    assert {i["item"]: i["level"] for i in posting_check(p)["items"]}["업종"] == "미충족"
    q = parse_posting({**POST, "industry": "엉뚱한 업종"})  # 공공데이터 조회 결과가 있으면 그 값이 우선
    assert q["industry"] == "소프트웨어 개발 및 공급업"


def test_companies_collection_stored():
    store.reset()
    store.put("companies", "C-0001234567", {"busino": "0001234567", "company": "바른정밀(가상)"})
    assert store.list_items("companies")[0]["company"] == "바른정밀(가상)"
    store.reset()
