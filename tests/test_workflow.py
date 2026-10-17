"""시연 흐름(저장 → 지원 → 채용 확정 → 근로계약 → 급여명세서 대조) 서버 쪽 테스트. AI 호출 없음."""
import base64
import json
import os
import sys
from datetime import date
from pathlib import Path

os.environ["IEUM_BUILTIN_ONLY"] = "1"
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "VERCEL"):
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


def test_recommendation_excludes_tax_arrears_but_keeps_excluded_industry():
    from match import rank
    from rules import judge
    base = {"region": "서울 강남구", "emp_type": "정규직", "priority": True, "wage": 2600000, "weekly_hours": 40, "skills": [], "close": "2099-12-31"}
    bar = {**base, "id": "X1", "company": "라운지(가상)", "title": "매장 관리", "job": "매장 관리", "industry": "일반 유흥 주점업"}
    tax = {**base, "id": "X2", "company": "건설(가상)", "title": "매장 관리", "job": "매장 관리", "industry": "건물 건설업", "tax_arrears": True}
    picks, ex = rank([bar, tax], "매장 관리", "매장 관리", "무관")
    assert [r["post"]["id"] for r in picks] == ["X1"] and ex["tax_arrears"] == 1  # 체납은 추천 제외, 제외 업종은 추천
    person = {"age": 26, "programs": [{"type": "청년도전지원사업", "completed": "2026-05-29", "status": "수료"}], "insurance": []}
    j = judge(person, bar, True)
    assert j["badge"] is False and j["type"] == "excluded_industry"  # 지원제도 표시만 막음
    assert judge(person, {**bar, "industry": "소프트웨어 개발 및 공급업"}, True)["badge"] is True


def test_prorated_first_month_min_wage_compares_worked_days():
    """D3: 15일 입사 첫 달(일할 17/31일)은 일할한 최저임금과 비교 — 한 달치 기준으로 '불일치'가 나오면 안 됨."""
    f = {"media_type": "image/jpeg", "data": base64.b64encode(b"x" * 10).decode()}
    gross = 2800000 * 17 // 31 // 10 * 10
    issued = {"name": "정다온", "ym": "2026-07", "pay_date": "2026-08-10", "gross": str(gross), "deduction": "0", "net": str(gross)}
    tr = {"transfer": {"recipient": "정다온", "date": "2026-08-10", "amount": str(gross), "sender": "회사"}}
    body = {"month": "2026-07", "files": [f], "issued_payslip": issued, "sample_truth": tr,
            "ctx": {"worker": "정다온", "hire_date": "2026-07-15", "weekly_hours": 40}}
    lv = lambda r: {i["item"]: i["level"] for i in r["check"]["items"]}["최저임금"]  # noqa: E731
    assert lv(certificate.claimdoc(body)) == "불일치"  # 일할 정보 없으면 한 달치와 비교
    r = certificate.claimdoc({**body, "ctx": {**body["ctx"], "prorate": {"days": 17, "dim": 31}}})
    assert lv(r) == "일치" and "일할 17/31일" in str(r["check"]["items"])
    bad = certificate.claimdoc({**body, "ctx": {**body["ctx"], "prorate": {"days": 40, "dim": 31}}})  # 잘못된 값은 무시
    assert lv(bad) == "불일치"


def test_contract_below_min_wage_is_rejected_with_basis():
    """지원사업과 무관하게 최저임금 미달 근로계약서는 저장 거부 + 근거(계산·조항) 반환"""
    h = cases.handler.__new__(cases.handler)
    base = {"posting": POST, "posting_id": "U-test", "applicant_id": "U-test-Sabc", "applicant": {"alias": "정다온", "profile": SEEK}, "hire_date": "2026-10-15"}
    ok_ct = {"employment_type": "정규직", "wage_type": "월급", "start_date": "2026-10-01", "end_date": "", "base_wage": 2500000, "allowances": 0,
             "weekly_hours": 40, "daily_hours": 8, "break_minutes": 60, "has_holiday": True, "has_leave": True, "has_place": True, "has_job": True, "has_payday": True}
    h.read_json = lambda max_body=0: {**base, "contract": ok_ct}
    assert h.handle_post()["ok"]
    h.read_json = lambda max_body=0: {**base, "contract": {**ok_ct, "base_wage": 1500000}}
    with pytest.raises(ApiError) as e:
        h.handle_post()
    assert e.value.status == 422 and e.value.code == "min_wage"
    d = e.value.detail
    assert "최저임금" in d["detail"] and "제6조" in d["law"] and "제28조" in d["penalty"]


def test_transfer_rows_fix_ai_field_mixups(monkeypatch):
    """실제 배포에서 Haiku가 보낸 분 자리에 은행 이름을 넣거나 보낸 분·받는 분을 뒤바꿈 → 표 항목 이름으로 바로잡음"""
    rows = [{"label": "거래일시", "value": "2026-05-10 09:12:30"}, {"label": "출금계좌", "value": "110-***-***090"},
            {"label": "보내는 분(예금주)", "value": "김대표"}, {"label": "입금은행", "value": "가람은행(가상)"},
            {"label": "받는 분(예금주)", "value": "서지우"}, {"label": "이체금액", "value": "2,030,970원"},
            {"label": "받는 분 통장 표시", "value": "4월 급여"}]
    assert certificate._from_rows(rows) == {"sender": "김대표", "recipient": "서지우", "amount": "2030970", "date": "2026-05-10"}
    assert certificate._from_rows([{"label": "받는 분 통장 표시", "value": "급여"}]) == {}  # 메모 줄은 받는 분이 아님
    assert certificate._from_rows(None) == {} and certificate._from_rows([{"label": 1}]) == {}
    swapped = {"transfer": {"recipient": "김대표", "sender": "서지우", "amount": "2030970", "date": "2026-05-10"}, "rows": rows}
    monkeypatch.setattr(certificate, "provider", lambda: "claude")
    monkeypatch.setattr(certificate, "generate_json", lambda *a, **k: json.loads(json.dumps(swapped)))
    f = {"media_type": "image/jpeg", "data": base64.b64encode(b"x" * 10).decode()}
    r = certificate.claimdoc({"month": "2026-04", "files": [f], "ctx": {"worker": "서지우", "company": "다온물류(가상)"},
                              "issued_payslip": {"name": "서지우", "ym": "2026-04", "pay_date": "2026-05-10", "gross": "2300000", "deduction": "269030", "net": "2030970"}})
    assert r["transfer"]["sender"] == "김대표" and r["transfer"]["recipient"] == "서지우"
    lv = {i["item"]: i["level"] for i in r["check"]["items"]}
    assert lv["성명"] == "일치" and lv["이체자(보내는 분)"] == "확인 필요"  # 대표 개인 계좌 사례가 의도대로


def test_portfolio_keeps_program_paragraph_masked_and_structured(monkeypatch):
    import seeker
    ai_out = {"headline": "엑셀로 사무 업무를 처리하는 신입", "summary": "사무행정 실무 훈련 160시간을 수료했습니다. 행사 명단을 관리했습니다.",
              "strengths": [{"title": "문서 작성", "evidence": "사무행정 실무 훈련"}, {"title": "꼼꼼함", "evidence": "명단 관리"}],
              "sections": [{"title": "진로 상담", "body": "국민취업지원제도 상담에서 취업활동계획을 세웠습니다."},
                           {"title": "사무행정 훈련", "body": "엑셀을 300시간 배웠습니다."},  # 원문에 없는 숫자 → 차단
                           {"title": "복지관 행사 보조", "body": "참가자 명단과 물품을 관리했습니다."}],
              "fit": "사무 직무에서 명단·자료 관리 경험을 활용할 수 있습니다.", "skills": ["엑셀", "파이썬"]}
    monkeypatch.setattr(seeker, "generate_json", lambda *a, **k: ai_out)
    p = {"ai_consent": True, "desire": {"job": "사무"}, "points": ["사무행정 실무 훈련", "복지관 행사 보조"],
         "experience": "- 진로상담 4회 (취업활동계획 수립)\n- 사무행정 실무 (엑셀·문서) 160시간\n- 복지관 행사 명단·물품 관리"}
    r = seeker.portfolio(p)
    doc = r["portfolio"]
    assert "■ 강점\n문서 작성 · 꼼꼼함" in doc and "■ 사무 직무에서" in doc
    assert "• 진로 상담 — 고용서비스 프로그램 상담에서 취업 계획을" in doc  # 문단을 버리지 않고 사업명만 바꿈
    assert "국민취업" not in doc and "취업활동계획" not in doc and "300시간" not in doc
    assert "엑셀" in doc and "파이썬" not in doc and r["meta"]["guard_blocked"] == 1


def test_portfolio_drops_repeats_puffery_and_invented_tech(monkeypatch):
    """배포 실측(하윤서): 같은 사실이 2~3번 반복되고 '실무 중심…능력을 키웠습니다' 같은 평가 문장이 붙음 → 문장 단위로 거름"""
    import seeker
    exp = ("- K-디지털 웹 개발 부트캠프 수료 (HTML, CSS, JavaScript, React), 480시간\n"
           "- 팀 프로젝트: 지역 축제 일정 안내 웹사이트, 4인 팀에서 메인 화면과 일정 필터 기능 담당\n"
           "- 개인 프로젝트: 할 일 관리 웹앱 (React, 로컬 저장), 깃허브에 코드 공개\n- 카페 아르바이트 1년: 주문 응대, 신규 직원 교육")
    ai_out = {"headline": "React로 화면을 만들어 본 신입 웹 개발 지원자",
              "summary": "부트캠프 480시간 동안 HTML, CSS, JavaScript, React를 배웠습니다. 팀과 개인 프로젝트로 화면을 직접 만들었습니다.",
              "strengths": [{"title": "화면 구현", "evidence": "팀 프로젝트"}, "협업", "뛰어난 소통"],
              "sections": [
                  {"title": "웹 개발 부트캠프", "body": "부트캠프 480시간 동안 HTML, CSS, JavaScript, React를 배웠습니다. 실무 중심의 프론트엔드 개발 능력을 키웠습니다."},
                  {"title": "지역 축제 웹사이트", "body": "4인 팀에서 메인 화면과 일정 필터 기능을 맡았습니다. Redux로 상태를 관리했습니다."},
                  {"title": "할 일 관리 웹앱", "body": "React로 할 일 관리 웹앱을 만들고 깃허브에 코드를 공개했습니다."},
                  {"title": "카페 아르바이트", "body": "1년간 주문을 응대하고 신규 직원을 교육했습니다."}],
              "fit": "4인 팀에서 메인 화면과 일정 필터 기능을 맡은 경험이 있습니다. 화면 개발 업무를 바로 거들 수 있습니다.", "skills": ["React", "Redux"]}
    monkeypatch.setattr(seeker, "generate_json", lambda *a, **k: ai_out)
    r = seeker.portfolio({"ai_consent": True, "desire": {"job": "웹 개발"}, "points": [], "experience": exp})
    doc, rm = r["portfolio"], r["meta"]["removed"]
    assert doc.count("480시간") == 1 and doc.count("메인 화면과 일정 필터") == 1  # 같은 사실은 한 번만
    assert "실무 중심" not in doc and "Redux" not in doc and "뛰어난" not in doc
    assert rm == {"duplicate": 2, "puffery": 1, "unknown_term": 1}
    assert "■ 강점\n화면 구현 · 협업" in doc and "• 카페 아르바이트 — 1년간 주문을 응대하고 신규 직원을 교육했습니다." in doc
    assert r["meta"]["chars"] == len(doc) < 700


def test_one_char_ocr_slips_are_not_false_alarms():
    """배포 실측: Haiku가 '다온물류'를 '다운물류', '박서연'을 '박시연'으로 읽음 → 회사는 일치(표시), 근로자 이름은 확인 필요, 전혀 다르면 그대로"""
    from claimdocs import check_month
    ps = {"name": "서지우", "ym": "2026-04", "net": "2030970"}
    lv = lambda tr: {i["item"]: (i["level"], i["detail"]) for i in check_month("2026-04", ps, tr, {"worker": "서지우", "company": "다온물류 (가상)"})["items"]}  # noqa: E731
    r = lv({"recipient": "서지우", "sender": "다운물류 (가상)", "amount": "2030970", "date": "2026-05-10"})
    assert r["이체자(보내는 분)"][0] == "일치" and "판독 오차" in r["이체자(보내는 분)"][1]
    assert lv({"recipient": "서지우", "sender": "다운몰류 (가상)", "amount": "2030970"})["이체자(보내는 분)"][0] == "일치"  # 실측: 모음 두 개 오독
    assert lv({"recipient": "서지우", "sender": "다온유통", "amount": "2030970"})["이체자(보내는 분)"][0] == "확인 필요"  # 자음이 다르면 다른 회사
    assert lv({"recipient": "서지우", "sender": "김대표", "amount": "2030970"})["이체자(보내는 분)"][0] == "확인 필요"
    assert lv({"recipient": "서지운", "sender": "다온물류", "amount": "2030970"})["성명"][0] == "확인 필요"
    assert lv({"recipient": "박서연", "sender": "다온물류", "amount": "2030970"})["성명"][0] == "불일치"
    assert lv({"recipient": "허지우", "sender": "다온물류", "amount": "2030970"})["성명"][0] == "불일치"  # 성이 다르면 다른 사람


def test_case_eligibility_uses_hire_date():
    """채용 확정 뒤 판정은 채용일 기준: 국취 인정·청년도전 수료가 채용보다 먼저여야 근거 (지원 단계 예상 판정은 그대로)"""
    from rules import judge
    post = {"emp_type": "정규직", "region": "서울 강남구", "priority": True, "industry": "소프트웨어"}
    kuchwi = {"age": 27, "programs": [{"type": "국민취업지원제도", "qualified": "2026-04-20", "iap": "2026-05-02"}], "insurance": []}
    dojeon = {"age": 26, "programs": [{"type": "청년도전지원사업", "completed": "2026-05-29"}], "insurance": []}
    for p in (kuchwi, dojeon):
        assert judge(p, post, True)["eligible"]                                  # 지원 단계: 예상 대상
        assert judge(p, post, True, hire=date(2026, 6, 1))["eligible"]           # 참여·수료 뒤 채용
        early = judge(p, post, True, hire=date(2026, 4, 1))                      # 참여·수료 전에 채용
        assert not early["eligible"] and "채용일" in " ".join(early["flags"]["evidence"])
    case = cases.build_case(parse_posting(POST), {**cases.resolve_applicant({**parse_posting(POST), "id": "U-t"}, "U-t-Sx", None, {"alias": "가", "profile": SEEK}), "programs": dojeon["programs"]},
                            date(2026, 4, 1), today=date(2026, 10, 17))
    assert case["evidence"]["title"] == "취업애로청년 근거 미확인" and any("채용일" in l for l in case["evidence"]["lines"])


def test_swapped_reading_is_corrected_and_corp_jamo_slip():
    """실측: 윤하람 건에서 보낸 분=윤하람·받는 분=김대표로 뒤바뀜, 회사명 '다운몬류' → 바로잡고 표시"""
    from claimdocs import check_month
    ps = {"name": "윤하람", "ym": "2026-04", "gross": "2300000", "net": "2030970"}
    ctx = {"worker": "윤하람", "company": "다온물류 (가상)"}
    r = check_month("2026-04", ps, {"recipient": "김대표", "sender": "윤하람", "amount": "2030970"}, ctx)
    lv = {i["item"]: i["level"] for i in r["items"]}
    assert lv["성명"] == "일치" and lv["이체자(보내는 분)"] == "확인 필요" and lv["판독 보정"] == "참고" and r["level"] == "확인 필요"
    ok = check_month("2026-04", ps, {"recipient": "윤하람", "sender": "다운몬류 (가상)", "amount": "2030970"}, ctx)
    assert ok["level"] == "일치"
    f = {"media_type": "image/jpeg", "data": base64.b64encode(b"x" * 10).decode()}
    out = certificate.claimdoc({"month": "2026-04", "files": [f], "ctx": ctx, "issued_payslip": {**ps, "pay_date": "2026-05-10", "deduction": "0"},
                                "sample_truth": {"transfer": {"recipient": "김대표", "sender": "윤하람", "amount": "2030970", "date": "2026-05-10"}}})
    assert out["transfer"]["sender"] == "김대표" and out["transfer"]["recipient"] == "윤하람"  # 화면 비교표도 바로잡힌 값
