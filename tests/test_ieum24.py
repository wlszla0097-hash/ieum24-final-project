"""이음24 규칙엔진·차별 방지·AI 가드 테스트: python -m pytest tests"""
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "api"))
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "WORK24_KEY"):
    os.environ.pop(k, None)

import pytest  # noqa: E402

import cases as case  # noqa: E402
import employer  # noqa: E402
import rules  # noqa: E402
import userinput as profile  # noqa: E402
import certificate  # noqa: E402
import seeker  # noqa: E402
from common import ApiError  # noqa: E402
from match import guard  # noqa: E402
from synthetic import posting  # noqa: E402

SEOUL = {"region": "서울 마포구", "emp_type": "정규직", "priority": True}
GUMI = {"region": "경북 구미시", "emp_type": "정규직", "priority": True}


def who(programs, insurance=(), age=27):
    return {"age": age, "programs": list(programs), "insurance": list(insurance)}


KUCHWI = {"type": "국민취업지원제도", "qualified": "2026-04-20", "iap": "2026-05-02"}
DOJEON = {"type": "청년도전지원사업", "completed": "2026-08-29"}


@pytest.mark.parametrize("person,expected", [
    (who([KUCHWI]), True),                                                     # 국취 참여 후 최초 취업
    (who([KUCHWI], [{"acquired": "2026-07-01", "lost": "2026-08-31"}]), False),  # 참여 후 취업 이력 있음
    (who([KUCHWI], [{"acquired": "2024-03-02", "lost": "2024-12-31"}]), True),   # 참여 전 이력은 무관
    (who([{"type": "국민취업지원제도", "qualified": "2026-04-20"}]), False),     # 취업활동계획 미수립
    (who([DOJEON]), True),                                                     # 청년도전 수료
    (who([]), False),                                                          # 일반 훈련만
    (who([DOJEON], age=36), False),                                            # 청년 연령 아님
])
def test_capital_badge_rule(person, expected):
    assert rules.judge(person, SEOUL, consent=True)["eligible"] is expected


def test_badge_requires_consent():
    j = rules.judge(who([DOJEON]), SEOUL, consent=False)
    assert j["eligible"] and not j["badge"]


def test_non_capital_and_non_regular_show_no_badge():
    assert rules.judge(who([DOJEON]), GUMI, True)["type"] == "non_capital"
    assert not rules.judge(who([DOJEON]), {**SEOUL, "emp_type": "계약직"}, True)["badge"]
    assert not rules.judge(who([DOJEON]), {**SEOUL, "priority": False}, True)["badge"]


PROFILE = {"experience": "웹 개발 과정 수료 (HTML, CSS, JavaScript, React), 팀 프로젝트 화면 담당", "job": "웹 개발", "region": "서울",
           "kuchwi": True, "kuchwi_qualified": "2026-04-20", "kuchwi_iap": True, "youth": True, "consent": True,
           "agree_privacy": True, "agree_detail": True}
POST_FORM = {"company": "테스트랩", "sido": "서울", "sigungu": "마포구", "title": "웹 프론트엔드 개발자", "job": "웹 개발",
             "emp_type": "정규직", "wage": 2800000, "insured": 18, "priority": "예", "description": "React, JavaScript 개발"}


def test_employer_view_hides_reason_and_age():
    out = employer.build({"posting": POST_FORM, "my_application": {"profile": PROFILE}})
    raw = json.dumps(out["applicants"], ensure_ascii=False)
    for word in ("국민취업", "청년도전", "age", "programs", "insurance", "reason", "youth"):
        assert word not in raw
    assert [a["applied"] for a in out["applicants"]] == sorted(a["applied"] for a in out["applicants"])  # 지원일 순 고정
    me = [a for a in out["applicants"] if a["is_me"]][0]
    assert me["badge"] is True


def test_posting_check_flags():
    assert rules.posting_check(posting("JOB-09"))["verdict"] == "연계 어려움"   # 최저임금 미달
    assert rules.posting_check(posting("JOB-01"))["verdict"] == "연계 가능성 높음"
    assert rules.posting_check(posting("JOB-08"))["verdict"] == "확인 필요"      # 피보험자 5인 미만


def test_schedule_six_months():
    s = rules.schedule(date(2026, 8, 31), today=date(2026, 10, 10))
    assert s["six_month_date"] == "2027-02-28" and s["state"] == "고용유지 중"
    assert rules.schedule(date(2026, 3, 3), today=date(2026, 10, 10))["state"] == "신청 가능"


@pytest.mark.parametrize("text,ok", [
    ("React로 화면을 구현할 수 있습니다.", True),
    ("채용 시 지원금을 받을 수 있습니다.", False),   # 지원금 언급
    ("만 27세 청년입니다.", False),                  # 연령 언급
    ("480시간 훈련을 수료했습니다.", True),           # 입력에 있는 숫자
    ("3년 실무 경력이 있습니다.", False),             # 입력에 없는 숫자
])
def test_ai_guard(text, ok):
    assert (guard(text, "웹 개발 과정 480시간") is not None) is ok


def test_seeker_user_input_without_ai():
    out = seeker.run(profile.parse_seeker({**PROFILE, "region": "무관", "job": "품질", "experience": "품질관리 실무 과정, 측정기 사용, QC 도구"}))
    assert out["meta"]["ai_used"] is False and out["activities"] and out["competencies"]
    assert "JOB-10" not in [j["id"] for j in out["jobs"]] and out["meta"]["excluded"]["arrears"] == 1


def test_seeker_input_validation():
    for bad in ({**PROFILE, "experience": ""}, {**PROFILE, "job": ""}, {**PROFILE, "kuchwi_qualified": ""},
                {**PROFILE, "kuchwi_qualified": "2099-01-01"}, {**PROFILE, "region": "화성"}):
        with pytest.raises(ApiError):
            profile.parse_seeker(bad)


def test_user_profile_rules():
    p = profile.parse_seeker(PROFILE)
    assert rules.judge(p, SEOUL, True)["badge"] is True
    assert rules.judge(profile.parse_seeker({**PROFILE, "kuchwi_job_after": True}), SEOUL, True)["eligible"] is False
    assert rules.judge(profile.parse_seeker({**PROFILE, "kuchwi_iap": False}), SEOUL, True)["eligible"] is False
    assert rules.judge(profile.parse_seeker({**PROFILE, "youth": False}), SEOUL, True)["eligible"] is False


def test_posting_discrimination_and_validation():
    post = profile.parse_posting({**POST_FORM, "description": "30세 이하, 남성 우대"})
    items = {i["item"]: i["level"] for i in rules.posting_check(post)["items"]}
    assert items["채용 차별 소지 표현"] == "확인 필요"
    with pytest.raises(ApiError):
        profile.parse_posting({**POST_FORM, "sido": ""})


def test_case_discloses_reason_only_with_consent():
    post = profile.parse_posting(POST_FORM)
    hire = date(2026, 10, 12)
    me = case.resolve_applicant(post, "CUSTOM-ME", {"profile": PROFILE})
    assert case.build_case(post, me, hire)["evidence"]["open"] is True
    me2 = case.resolve_applicant(post, "CUSTOM-ME", {"profile": {**PROFILE, "agree_detail": False}})
    closed = case.build_case(post, me2, hire)["evidence"]
    assert closed["open"] is False and not any("국민취업" in line for line in closed["lines"])


def test_demo_cases_statuses():
    st = {c["company"]: c["status"] for c in case.demo_cases(today=date(2026, 10, 10))}
    # 세진정밀: 계약·요건은 충족이지만 월별 서류 7월분 이체액 불일치 → 확인 필요
    assert st["가온유통 (가상)"] == "보완 필요" and st["세진정밀 (가상)"] == "확인 필요"


def test_contract_guard_blocks_invented_numbers():
    src = "최저임금: 환산 시급 9,569원 < 2026년 최저임금 10,320원 — 월 환산 최소 2,156,880원 필요"
    assert guard("월 2,150,000원 이상으로 인상하세요.", src, forbid=False) is None
    assert guard("월 2,156,880원 이상으로 인상하세요.", src, forbid=False)
    assert guard("최저임금 10,320원 미달이라 지원금 대상 확인 필요", src, forbid=False)  # 근로계약 설명은 금지어 검사 제외


def test_guard_number_formats():
    src = "데이터 분석 과정 320시간, 2026년 8월, 최저 월 2,156,880원"
    assert guard("2026.08 수료 (320시간)", src)          # 표기 형식이 달라도 같은 숫자는 통과
    assert guard("월 2,156,880원", src, forbid=False)
    assert guard("월 2,150,000원", src, forbid=False) is None
    assert guard("3년 경력", src) is None


def test_min_wage_posting_not_recommended():
    out = seeker.run(profile.parse_seeker({**PROFILE, "experience": "엑셀로 재고 관리, 사무 보조 경험", "job": "사무", "region": "서울"}))
    assert "JOB-09" not in [j["id"] for j in out["jobs"]] and out["meta"]["excluded"]["min_wage"] == 1


def test_privacy_consent_required_and_ai_gate():
    with pytest.raises(ApiError):
        profile.parse_seeker({**PROFILE, "agree_privacy": False})
    out = seeker.run(profile.parse_seeker({**PROFILE, "agree_ai": False}))
    assert out["meta"]["ai_used"] is False and "AI 서버로 전송되지 않았습니다" in out["meta"]["ai_error"]


def test_cert_evidence_and_match():
    p = profile.parse_seeker({**PROFILE, "agree_cert": True, "cert": {"program": "국민취업지원제도", "date": "2026-04-20", "issuer": "고용센터"}})
    assert p["cert"]["matched"] is True
    assert any("AI 판독 날짜" in e for e in rules.history_flags(p)["evidence"])
    p2 = profile.parse_seeker({**PROFILE, "agree_cert": False, "cert": {"program": "국민취업지원제도", "date": "2026-04-20"}})
    assert p2["cert"] is None  # 판독 동의가 없으면 증빙값을 쓰지 않음


def test_certificate_requires_consent_and_type():
    with pytest.raises(ApiError):
        certificate.read({"media_type": "image/png", "data": "aGVsbG8=", "consent": False})
    with pytest.raises(ApiError):
        certificate.read({"media_type": "text/plain", "data": "aGVsbG8=", "consent": True})
    assert certificate.classify("2026년 청년도전 지원사업", "") == "청년도전지원사업"
    assert certificate.classify("", "국민취업지원제도 직업훈련") == "국민취업지원제도"


def test_employer_sees_points_with_program_names_hidden():
    prof = {**PROFILE, "points": ["청년도전지원사업 프로그램 수료", "React 웹앱 화면 구현"], "portfolio": "국민취업지원제도 상담으로 목표를 세웠습니다.\nReact로 구현"}
    out = employer.build({"posting": POST_FORM, "my_application": {"profile": prof}})
    me = [a for a in out["applicants"] if a["is_me"]][0]
    raw = json.dumps(me, ensure_ascii=False)
    assert "청년도전" not in raw and "국민취업" not in raw and "비공개" not in raw and me["points"] == ["React 웹앱 화면 구현"]
    assert "React로 구현" in me["portfolio"]


def test_mvp_eval_targets():
    """기획안 'MVP 검증 지표'를 합성데이터로 측정 (tools/eval_mvp.py) — 목표 미달이면 실패."""
    import runpy
    g = runpy.run_path(str(Path(__file__).resolve().parent.parent / "tools" / "eval_mvp.py"))
    assert g["badge_acc"] >= 98 and g["detect"] >= 95
    assert g["leaks"] == 0 and g["consent_off_badges"] == 0 and g["clean_fp"] == 0
    assert g["bad_blocked"] == len(g["BAD"]) and not g["kept_fake"]
    assert g["doc_detect"] >= 95 and g["doc_fp"] == 0


def test_claimdocs_month_check():
    """⑦ 월별 서류 점검: 이체액 차이·성명 불일치·최저임금 미달·누락 월을 잡고, 정상 서류는 일치."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
    from claimdocs import check_month, missing_months
    ctx = {"worker": "김가람", "weekly_hours": 40, "history": []}
    ok = check_month("2026-07", {"name": "김가람", "ym": "2026-07", "gross": "2,800,000", "net": "2,478,000"},
                     {"recipient": "김 가람", "amount": "2478000", "date": "2026-08-10"}, ctx)
    assert ok["level"] == "일치"
    bad = check_month("2026-07", {"name": "김가람", "ym": "2026-06", "gross": "2,000,000", "net": "1,800,000"},
                      {"recipient": "박가람", "amount": "1,770,000", "date": "2026-08-10"}, ctx)
    got = {i["item"]: i["level"] for i in bad["items"]}
    assert got["성명"] == got["귀속월"] == got["실지급액·이체액"] == got["최저임금"] == "불일치"
    avg = check_month("2026-07", {"name": "김가람", "ym": "2026-07", "gross": "5,000,000", "net": "4,300,000"},
                      {"recipient": "김가람", "amount": "4,300,000"}, {**ctx, "history": [{"ym": "2026-06", "gross": 4_200_000}]})
    assert {i["item"]: i["level"] for i in avg["items"]}["평균 월 급여 상한"] == "불일치"  # 평균 460만원 > 450만원
    assert missing_months("2026-04-15", ["2026-04", "2026-06"], date(2026, 8, 3)) == ["2026-05", "2026-07"]


def test_certificate_claimdoc_without_ai_uses_sample_truth():
    import base64
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
    import certificate
    img = {"media_type": "image/jpeg", "data": base64.b64encode(b"x").decode()}
    truth = {"payslip": {"name": "김가람", "ym": "2026-05", "gross": "2600000", "net": "2300000"}, "transfer": {"recipient": "김가람", "amount": "2300000"}}
    r = certificate.claimdoc({"kind": "claimdoc", "month": "2026-05", "files": [img, img], "sample_truth": truth, "ctx": {"worker": "김가람"}})
    assert r["source"] == "synthetic_truth" and r["check"]["level"] == "일치"
    with pytest.raises(ApiError):
        certificate.claimdoc({"kind": "claimdoc", "month": "2026-05", "files": [img, img]})  # 실제 서류는 AI 없이 판독 불가
