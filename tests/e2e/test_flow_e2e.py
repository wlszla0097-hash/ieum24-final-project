"""화면 전체 흐름 자동 테스트 (브라우저로 실제 클릭) — AI 호출 없음, 비용 0.

실행:  IEUM_E2E=1 python3 -m pytest -q tests/e2e
- Playwright(파이썬)와 Chromium이 있어야 합니다. 없으면 건너뜁니다.
- 테스트마다 개발 서버를 새로 띄워(메모리 저장) 서로 영향을 주지 않습니다.
- 기본 pytest 실행(tests/)에는 포함되지 않도록 IEUM_E2E=1 일 때만 돕니다.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

if os.environ.get("IEUM_E2E") != "1":
    pytest.skip("IEUM_E2E=1 일 때만 실행 (브라우저 테스트)", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
XSS = '<img src=x onerror="window.__xss=1">'


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


def _server(extra_env=None):
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC", "OPENAI", "GEMINI", "KV_", "UPSTASH"))}
    env.update({"PORT": str(port), "VERCEL": "", **(extra_env or {})})
    if not env["VERCEL"]:
        env.pop("VERCEL")
    proc = subprocess.Popen([sys.executable, str(ROOT / "dev_server.py")], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            return proc, base
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("개발 서버가 뜨지 않음")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _page(browser, base, **kw):
    ctx = browser.new_context(viewport=kw.pop("viewport", {"width": 1280, "height": 900}))
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "ERR_TUNNEL" not in m.text and "Failed to load resource" not in m.text and pg.errors.append(m.text))
    pg.base = base
    return pg


@pytest.fixture()
def app(browser):
    proc, base = _server()
    pg = _page(browser, base)
    yield pg
    pg.context.close()
    proc.kill()


# ---------- 공통 단계 ----------
def seeker_apply(pg, example="P-01", alias="정다온", job_id=None, detail=False):
    pg.goto(pg.base + "/#seeker")
    pg.wait_for_function("document.querySelectorAll('#seekExample option').length > 1")
    pg.select_option("#seekExample", example)
    pg.fill("#s_alias", alias)
    pg.check("#seekForm [name=agree_privacy]")
    if detail:
        pg.check("#seekForm [name=agree_detail]")
    pg.click("#seekBtn")
    pg.wait_for_selector("#seekResult .apply", timeout=30000)
    ids = pg.eval_on_selector_all("#seekResult .apply", "els => els.map(e => e.dataset.id)")
    jid = job_id(ids) if callable(job_id) else (job_id or ids[0])
    pg.click(f"#seekResult .apply[data-id='{jid}']")
    pg.wait_for_function(f"document.querySelector(\"#seekResult .apply[data-id='{jid}']\").textContent.includes('지원 완료')")
    return jid


def company_key_for(pg, jid):
    cos = json.loads(urllib.request.urlopen(pg.base + "/api/employer").read())["companies"]
    return next(c["key"] for c in cos if any(x["id"] == jid for x in c["postings"]))


def goto_companies(pg):
    """기업 메뉴는 마지막으로 고른 회사 화면을 기억한다(로그인 상태처럼) → 목록으로 나가기"""
    pg.goto(pg.base + "/#employer")
    pg.wait_for_function("document.querySelector('#empCompanies .co-card') && (!document.querySelector('#empCompanies').hidden || document.querySelector('#coChange'))")
    if not pg.evaluate("document.querySelector('#empWork').hidden"):
        pg.click("#coChange")
    pg.wait_for_selector("#empCompanies:not([hidden]) .co-card")


def open_company(pg, key):
    goto_companies(pg)
    pg.click(f".co-card[data-key='{key}']")
    pg.wait_for_selector("#empWork:not([hidden])")


def hire_stored(pg):
    pg.click("[data-etab=list]")
    pg.wait_for_selector("#postDetail .applicant.me [data-hire]", timeout=20000)
    pg.click("#postDetail .applicant.me [data-hire]")
    pg.wait_for_selector("#ctDoc .lc-doc")


def draw_sign(pg):
    pg.click("#ctDoc [data-sign]")
    pg.wait_for_selector("dialog.sign-dlg .sign-pad")
    box = pg.locator(".sign-pad").bounding_box()
    pg.mouse.move(box["x"] + 40, box["y"] + 90); pg.mouse.down()
    for i in range(10):
        pg.mouse.move(box["x"] + 60 + i * 30, box["y"] + 60 + (i % 3) * 25)
    pg.mouse.up()
    pg.click("dialog.sign-dlg [data-ok]")
    pg.wait_for_selector("#ctDoc img.lc-sign")


def save_contract(pg):
    pg.click("#ctSave")
    pg.wait_for_selector("#ctResult #goPay", timeout=20000)


def register_company(pg, name="바른정밀", busino="000-12-34567", ind="소프트웨어 개발 및 공급업"):
    pg.goto(pg.base + "/#employer")
    pg.wait_for_selector(".co-card")
    pg.click("#coNewBtn")
    pg.fill("#cn_name", name); pg.fill("#cn_busino", busino); pg.fill("#cn_ceo", "김바른")
    pg.fill("#cn_ind", ind); pg.select_option("#cn_sido", "서울"); pg.fill("#cn_sgg", "성동구"); pg.fill("#cn_ins", "15")
    pg.select_option("#cn_pri", "예")
    pg.click("#cnSave")


def post_job(pg, title="프론트엔드 개발자 신입 (React)", wage="2900000"):
    pg.click("[data-etab=post]")
    pg.fill("#p_title", title); pg.fill("#p_job", "웹 개발"); pg.fill("#p_wage", wage)
    pg.fill("#p_desc", "웹 서비스 화면 개발. JavaScript, React, HTML, CSS 사용. 신입 가능.")
    pg.click("#postBtn"); pg.wait_for_selector("#pubBtn", timeout=30000)
    pg.click("#pubBtn"); pg.wait_for_selector("#myPosts .post-item.active")


def stored(pg, col):
    return pg.evaluate(f"IeumStore.list('{col}')")


# ---------- 시나리오 ----------
def test_full_flow_existing_company(app):
    pg = app
    jid = seeker_apply(pg, detail=True)
    open_company(pg, company_key_for(pg, jid))
    hire_stored(pg)
    pg.click("#ct6m")  # 기존 근로자 등록 — 6개월분 급여 지급일이 지난 시점 (D9: 미리 발급 없음)
    draw_sign(pg)
    save_contract(pg)
    assert "체결 완료" in pg.inner_text("#ctResult h3")
    pg.click("#goPay"); pg.wait_for_selector("#payAll")
    pg.click("#payAll")
    pg.wait_for_function("document.querySelectorAll('#payRows table.cmp').length >= 6", timeout=60000)
    assert "6/6개월" in pg.inner_text("#paySum")
    pg.goto(pg.base + "/#officer"); pg.wait_for_selector(".case.fresh")
    card = pg.locator(".case.fresh").first
    assert "6/6개월" in card.inner_text()
    card.locator(".decide[data-v='검토 완료']").click()
    pg.wait_for_function("document.querySelector('.case.fresh .decision').textContent.includes('저장됨')")
    pg.reload(); pg.wait_for_selector(".case.fresh")
    assert "검토 완료" in pg.inner_text(".case.fresh .decision")  # 새로고침 후에도 처리 결과 유지
    # 근로자 서류함: 계약서 1·명세서 6
    pg.goto(pg.base + "/#seeker"); pg.wait_for_selector("#myDocs:not([hidden]) .md-row")
    t = pg.inner_text("#myDocs")
    assert "근로계약서 1건" in t and "급여명세서 6건" in t and "채용 확정" in t
    assert not pg.errors, pg.errors


def test_new_company_posting_reaches_seeker_and_stats(app):
    pg = app
    register_company(pg)
    pg.wait_for_selector("#empWork:not([hidden]) #postForm")
    assert pg.input_value("#p_busino") == "000-12-34567" and pg.input_value("#p_company") == "바른정밀(가상)"
    post_job(pg)
    jid = seeker_apply(pg, job_id=lambda ids: next(i for i in ids if i.startswith("U-")))
    goto_companies(pg); pg.wait_for_selector("#coGridUser .co-card")
    pg.wait_for_function("document.querySelector('#storeStats').textContent.includes('지원 1건')")
    assert "직접 등록 기업 1곳" in pg.inner_text("#storeStats")
    pg.click("#coGridUser .co-card"); hire_stored(pg)
    assert "대표이사 김바른" in pg.inner_text("#ctDoc")
    assert jid.startswith("U-") and not pg.errors, pg.errors


def test_worker_signs_from_inbox(app):
    pg = app
    jid = seeker_apply(pg, example="P-S01")
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    save_contract(pg)
    assert "근로자 서명 대기" in pg.inner_text("#ctResult h3")
    pg.goto(pg.base + "/#officer"); pg.wait_for_selector(".case.fresh")
    assert "근로계약서 서명" in pg.inner_text(".case.fresh") and "검토 대기" not in pg.inner_text(".case.fresh header .badge")
    pg.goto(pg.base + "/#seeker"); pg.wait_for_selector("#myDocs [data-sign-ct]")
    pg.click("#myDocs [data-sign-ct]"); pg.click("dialog.doc-dlg [data-sign]")
    pg.click("dialog.sign-dlg [data-tab=seal]"); pg.click("dialog.sign-dlg [data-fake]"); pg.click("dialog.sign-dlg [data-ok]")
    pg.wait_for_function("!document.querySelector('#myDocs [data-sign-ct]')")
    ct = stored(pg, "contracts")[0]
    assert ct["status"] == "체결 완료" and ct["sign_kind"] == "인장"
    case = stored(pg, "cases")[0]
    assert case["contract_status"] == "체결 완료"  # 담당자 신청 건에도 반영
    open_company(pg, company_key_for(pg, jid)); pg.click("[data-etab=list]")  # 기업 화면: 서명 후라 발급 가능(D6)
    pg.wait_for_selector("#postDetail [data-pay-ct]", timeout=20000); pg.click("#postDetail [data-pay-ct]")
    pg.wait_for_selector("#payAll"); assert not pg.is_disabled("#payAll") and "서명 전" not in pg.inner_text("#payPanel")


@pytest.mark.parametrize("kind,item,level", [("ok", "실지급액·이체액", "일치"), ("short", "실지급액·이체액", "불일치"),
                                             ("sender", "이체자(보내는 분)", "확인 필요"), ("recipient", "성명", "불일치")])
def test_transfer_example_cases(app, kind, item, level):
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    pg.click("#ct6m"); draw_sign(pg); save_contract(pg)
    pg.click("#goPay"); pg.wait_for_selector("#payRows [data-ex]")
    ym = pg.get_attribute("#payRows .month-row[data-state=open] >> nth=0", "data-ym")
    pg.select_option(f"#payRows [data-ex='{ym}']", kind)
    pg.click(f"#payRows [data-run='{ym}']")
    pg.wait_for_selector(f"#payRows .month-row[data-ym='{ym}'] table.cmp", timeout=30000)
    p = next(x for x in stored(pg, "payslips") if x["ym"] == ym)
    assert {i["item"]: i["level"] for i in p["check"]["items"]}[item] == level


def test_validation_messages(app):
    pg = app
    register_company(pg, busino="123-45-67890")  # 000으로 시작하지 않음
    assert "000으로 시작" in pg.inner_text("#cnMsg")
    pg.fill("#cn_busino", "000-81-00012")  # 이미 있는 합성 기업
    pg.click("#cnSave"); assert "이미 등록된" in pg.inner_text("#cnMsg")
    pg.fill("#cn_name", ""); pg.click("#cnSave"); assert "회사명" in pg.inner_text("#cnMsg")
    # 공고 필수값
    pg.click("#cnCancel"); pg.click(".co-card >> nth=0")
    pg.click("[data-etab=post]"); pg.click("#postBtn")
    assert "필수값" in pg.inner_text("#postMsg")


def test_contract_rules_and_signature_reset(app):
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    draw_sign(pg)
    wage = pg.input_value('[data-f="base_wage"]')
    pg.fill('[data-f="base_wage"]', "1500000")  # 바꾸면 서명 다시 받아야 함
    pg.wait_for_selector("#ctDoc [data-sign]")
    pg.fill('[data-f="b_end"]', "12:30")
    pg.click("#ctSave")  # 최저임금 미달 → 저장 거부, 근거 표시
    pg.wait_for_selector("#ctMsg:not([hidden]) >> text=최저임금 미달", timeout=20000)
    m = pg.inner_text("#ctMsg")
    assert "저장할 수 없어요" in m and "최저임금법 제6조" in m and "제28조" in m and "월 환산 최소" in m
    assert "invalid" in pg.get_attribute('[data-f="base_wage"]', "class") and stored(pg, "contracts") == []
    pg.fill('[data-f="base_wage"]', wage)  # 고치면 저장됨 (휴게 위반은 점검 결과로 표시)
    save_contract(pg)
    res = pg.inner_text("#ctResult")
    assert "휴게시간" in res and "위반 의심" in res and "근로자 서명 대기" in res and pg.is_hidden("#ctMsg")
    pg.select_option('[data-f="kind"]', "기간")
    assert pg.input_value('[data-f="end_date"]')  # 기간제 종료일 자동
    assert "기간의 정함이 있는" in pg.inner_text("#ctDoc")


def test_no_script_injection(app):
    pg = app
    jid = seeker_apply(pg, alias=XSS[:10])  # 입력 칸 최대 10자
    pg.evaluate("""async () => { const me = IeumStore.me(); const s = await IeumStore.get('seekers', me);
      await IeumStore.put('seekers', me, { ...s, alias: %s, headline: %s, portfolio: %s }); }""" % (json.dumps(XSS), json.dumps(XSS), json.dumps(XSS)))
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg); save_contract(pg)
    pg.goto(pg.base + "/#officer"); pg.wait_for_selector(".case.fresh")
    pg.goto(pg.base + "/#seeker"); pg.wait_for_selector("#myDocs .md-row")
    assert pg.evaluate("window.__xss") is None


def test_apply_twice_keeps_one_application(app):
    pg = app
    jid = seeker_apply(pg)
    pg.evaluate("j => IeumFlow.apply(state.jobs.find(x => x.id === j))", jid)
    assert len([a for a in stored(pg, "applications") if a["posting_id"] == jid]) == 1


def test_excluded_industry_company_is_flagged(app):
    pg = app
    register_company(pg, name="새벽라운지", busino="000-55-12345", ind="일반 유흥 주점업")
    pg.wait_for_selector("#empWork:not([hidden]) #postForm")
    pg.fill("#p_title", "매장 관리 직원"); pg.fill("#p_job", "매장 관리"); pg.fill("#p_wage", "2500000")
    pg.click("#postBtn"); pg.wait_for_selector("#postCheck .verdict")
    assert "연계 어려움" in pg.inner_text("#postCheck .verdict") and "업종" in pg.inner_text("#postCheck")


def test_reset_clears_everything(app):
    pg = app
    seeker_apply(pg)
    goto_companies(pg)
    pg.click("#storeReset"); pg.click("#storeReset")
    pg.wait_for_function("document.querySelector('#storeStats').textContent.includes('지원 0건')")
    assert stored(pg, "applications") == [] and stored(pg, "seekers") == []


def test_browser_storage_mode_persists(browser):
    proc, base = _server({"VERCEL": "1"})  # 배포 환경 + 저장소 미연결 → 브라우저 저장
    try:
        pg = _page(browser, base)
        jid = seeker_apply(pg)
        assert pg.evaluate("IeumStore.mode()") == "local"
        pg.reload(); goto_companies(pg)
        assert "지원 1건" in pg.inner_text("#storeStats") or pg.wait_for_function("document.querySelector('#storeStats').textContent.includes('지원 1건')")
        open_company(pg, company_key_for(pg, jid)); hire_stored(pg); save_contract(pg)
        assert len(stored(pg, "contracts")) == 1
        pg.context.close()
    finally:
        proc.kill()


def test_mobile_layout_has_no_horizontal_scroll(browser):
    proc, base = _server()
    try:
        pg = _page(browser, base, viewport={"width": 390, "height": 844})
        over = lambda: pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")  # noqa: E731
        for h in ("home", "seeker", "officer", "about"):
            pg.goto(f"{base}/#{h}"); pg.wait_for_timeout(300)
            assert over() <= 0, h
        pg.goto(base + "/#employer"); pg.wait_for_selector(".co-card"); assert over() <= 0
        pg.click("#coNewBtn"); assert over() <= 0
        pg.click(".co-card >> nth=0"); pg.wait_for_selector("#postDetail .applicant [data-hire]"); assert over() <= 0
        pg.click("#postDetail .applicant [data-hire] >> nth=0"); pg.wait_for_selector("#ctDoc .lc-doc"); assert over() <= 0
        pg.click("#ctSave"); pg.wait_for_selector("#goPay"); pg.click("#goPay"); pg.wait_for_selector("#payRows .month-row"); assert over() <= 0
        pg.context.close()
    finally:
        proc.kill()


def test_fixed_term_payroll_stops_at_contract_end(app):
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    pg.select_option('[data-f="kind"]', "기간")
    start = pg.input_value('[data-f="start_date"]')
    y, m = int(start[:4]), int(start[5:7]) + 2
    y, m = (y + 1, m - 12) if m > 12 else (y, m)
    pg.fill('[data-f="end_date"]', f"{y:04d}-{m:02d}-28")  # 3개월 계약
    save_contract(pg)
    pg.click("#goPay"); pg.wait_for_selector("#payRows .month-row")
    assert pg.locator("#payRows .month-row").count() == 3
    assert "서명 전" in pg.inner_text("#payPanel")


# ---------- 2026-10-16 결정 반영 (D3·D4·D6·D9) ----------
def _ym_shift(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) + k
    while m > 12: y, m = y + 1, m - 12
    while m < 1: y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


def test_unsigned_contract_cannot_issue_payslip(app):
    """D6: 근로자 서명 전에는 명세서 발급·예시 첨부·일괄 발급 모두 막힘"""
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    pg.click("#ct6m"); save_contract(pg)
    pg.click("#goPay"); pg.wait_for_selector("#payRows .month-row")
    assert "서명 전" in pg.inner_text("#payPanel") and pg.is_disabled("#payAll")
    assert pg.locator("#payRows [data-issue]").count() >= 1 and pg.locator("#payRows [data-issue]:not([disabled])").count() == 0
    assert pg.locator("#payRows [data-ex]").count() == 0
    assert stored(pg, "payslips") == []


def test_monthly_issue_only_after_pay_date(app):
    """D9: 오늘 입사면 아직 지급일이 지난 달이 없어 전부 '발급 예정', 미리 발급 불가"""
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    draw_sign(pg); save_contract(pg)
    pg.click("#goPay"); pg.wait_for_selector("#payRows .month-row")
    assert pg.locator("#payRows .month-row[data-state=open]").count() == 0
    assert pg.locator("#payRows .month-row[data-state=future]").count() == 6
    assert "발급 예정" in pg.inner_text("#payRows") and "미리 발급" not in pg.inner_text("#payRows")
    pg.click("#payAll"); pg.wait_for_function("document.querySelector('#toast').textContent.includes('기존 근로자 등록')")
    assert stored(pg, "payslips") == []


def test_new_company_months_before_signup_not_issued(app):
    """D9: 직접 등록한 기업은 이음24 등록월 전 달을 발급하지 않음 (기존 명세서로 확인)"""
    pg = app
    register_company(pg); pg.wait_for_selector("#empWork:not([hidden]) #postForm")
    post_job(pg)
    seeker_apply(pg, job_id=lambda ids: next(i for i in ids if i.startswith("U-")))
    goto_companies(pg); pg.click("#coGridUser .co-card"); hire_stored(pg)
    pg.click("#ct6m"); draw_sign(pg); save_contract(pg)
    pg.click("#goPay"); pg.wait_for_selector("#payRows .month-row")
    assert pg.locator("#payRows .month-row[data-state=pre]").count() >= 5
    assert "이음24 등록 전" in pg.inner_text("#payRows")


def test_mid_month_hire_first_payslip_is_prorated(app):
    """D3: 15일 입사면 첫 달은 일할 계산 (역일 기준), 둘째 달은 전액"""
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    pg.click("#ct6m")
    start = pg.input_value('[data-f="start_date"]')
    first = _ym_shift(start[:7], -1)  # 한 달 더 앞당겨 15일 입사 → 6개월 모두 지급일 지남
    pg.fill('[data-f="start_date"]', f"{first}-15")
    wage = int(pg.input_value('[data-f="base_wage"]'))
    draw_sign(pg); save_contract(pg)
    pg.click("#goPay"); pg.wait_for_selector(f"#payRows [data-issue='{first}']")
    assert "일할 " in pg.inner_text(f"#payRows .month-row[data-ym='{first}']") and "일할" not in pg.inner_text(f"#payRows .month-row[data-ym='{_ym_shift(first, 1)}'] .mth")
    pg.click(f"#payRows [data-issue='{first}']"); pg.wait_for_selector(f"#payRows [data-view='{first}']")
    second = _ym_shift(first, 1)
    pg.click(f"#payRows [data-issue='{second}']"); pg.wait_for_selector(f"#payRows [data-view='{second}']")
    ps = {p["ym"]: p for p in stored(pg, "payslips")}
    pr = ps[first]["prorate"]
    assert ps[first]["base"] == wage * pr["days"] // pr["dim"] // 10 * 10 < wage and ps[second]["base"] == wage and ps[second]["prorate"] is None
    pg.click(f"#payRows [data-view='{first}']")
    assert "일할 계산" in pg.inner_text("dialog.doc-dlg")


def test_contract_change_voids_issued_payslips_keeps_history(app):
    """D4: 계약 시작일을 바꾸면 이미 발급한 명세서는 지우지 않고 '정정(취소)'로 남김"""
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    pg.click("#ct6m"); draw_sign(pg); save_contract(pg)
    pg.click("#goPay"); pg.wait_for_selector("#payRows [data-issue]")
    first = pg.get_attribute("#payRows .month-row[data-state=open] >> nth=0", "data-ym")
    pg.click(f"#payRows [data-issue='{first}']"); pg.wait_for_selector(f"#payRows [data-view='{first}']")
    pg.fill('[data-f="start_date"]', f"{_ym_shift(first, 1)}-01")  # 입사를 한 달 늦춤 → 첫 달은 대상 아님
    draw_sign(pg); pg.click("#ctSave")
    pg.wait_for_function("document.querySelector('#toast').textContent.includes('정정(취소)')", timeout=20000)
    ps = stored(pg, "payslips")
    assert len(ps) == 1 and ps[0]["voided"] and "계약 기간" in ps[0]["voided"]["reason"] and "정정" in ps[0]["id"]
    pg.click("#goPay"); pg.wait_for_selector("#payRows details.voided")
    assert "정정(취소)된 명세서 1건" in pg.inner_text("#payRows")
    pg.goto(pg.base + "/#seeker")
    pg.wait_for_function("document.querySelector('#myDocs').textContent.includes('근로계약서 1건')")  # 화면 갱신 뒤에 확인
    t = pg.inner_text("#myDocs")
    assert "급여명세서 0건" in t and "정정(취소)된 명세서 1건" in t
    assert not pg.errors, pg.errors


# ---------- 2026-10-17: 팀원 테스트 결과 전달 ----------
def test_seeker_export_includes_ai_test_log(app, tmp_path):
    """구직자 화면 [테스트 결과 내보내기]: AI 호출 기록(ailog)·구직자·지원이 한 파일로, 키 값은 없음"""
    pg = app
    seeker_apply(pg, example="P-01")
    log = stored(pg, "ailog")
    assert len(log) == 1 and log[0]["kind"] == "이력 정리·공고 추천" and log[0]["example_id"] == "P-01"
    assert log[0]["ms"] >= 0 and log[0]["result"]["jobs"] and log[0]["ai_used"] is False  # 테스트 서버는 키 없음
    pg.wait_for_function("document.querySelector('#myDocs').textContent.includes('지원 현황 1건')")  # 새로고침 없이 반영
    assert "서버를 끄면 테스트 결과가 사라져요" in pg.inner_text("#myDocs")
    with pg.expect_download() as dl:
        pg.click("#myDocs #mdExport")
    path = tmp_path / "out.json"; dl.value.save_as(path)
    assert dl.value.suggested_filename.startswith("ieum24-test-no-ai-")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["seekers"]) == 1 and len(data["applications"]) == 1 and len(data["ailog"]) == 1
    assert data["ai"]["provider"] == "not_configured" and "API_KEY" not in path.read_text(encoding="utf-8")
    goto_companies(pg)  # 기업 화면 내보내기도 같은 내용
    pg.wait_for_function("document.querySelector('#storeStats').textContent.includes('AI 테스트 기록 1건')")
    with pg.expect_download() as dl2:
        pg.click("#storeExport")
    assert dl2.value.suggested_filename.startswith("ieum24-test-")
    assert not pg.errors, pg.errors


def test_team_results_merge_on_leader_browser(browser, tmp_path):
    """팀원 2명이 각자 컴퓨터(서버)에서 테스트 → 내보내기 → 팀장 브라우저에서 두 파일 불러오기 → 기업 화면에서 이어서 채용"""
    files, jids = [], []
    for who, ex in (("A", "P-01"), ("B", "P-S01")):
        proc, base = _server()  # 팀원마다 다른 개발 서버(메모리 저장) = 다른 컴퓨터
        try:
            pg = _page(browser, base)
            jids.append(seeker_apply(pg, example=ex, alias=f"팀원{who}구직"))
            pg.wait_for_selector("#myDocs #mdExport")
            with pg.expect_download() as dl:
                pg.click("#myDocs #mdExport")
            path = tmp_path / f"export_{who}.json"; dl.value.save_as(path); files.append(str(path))
            pg.context.close()
        finally:
            proc.kill()
    proc, base = _server({"VERCEL": "1"})  # 팀장: 배포 환경과 같은 브라우저 저장
    try:
        pg = _page(browser, base)
        goto_companies(pg)
        bad = tmp_path / "broken.json"; bad.write_text("{ 깨진", encoding="utf-8")
        with pg.expect_file_chooser() as fc:
            pg.click("#storeImport")
        fc.value.set_files(files + [str(bad)])
        pg.wait_for_function("document.querySelector('#toast').textContent.includes('export_B.json')")
        toast = pg.inner_text("#toast")
        assert "export_A.json: 구직자 1 · 지원 1 · AI 기록 1" in toast and "broken.json: 불러오지 못함" in toast
        pg.wait_for_function("document.querySelector('#storeStats').textContent.includes('지원 2건')")
        assert "AI 테스트 기록 2건" in pg.inner_text("#storeStats")
        seekers = stored(pg, "seekers")
        assert sorted(s["alias"] for s in seekers) == ["팀원A구직", "팀원B구직"]
        assert {s["imported_from"] for s in seekers} == {"export_A.json", "export_B.json"}  # 누구 결과인지 구분
        # 같은 파일을 다시 불러와도 늘어나지 않음(덮어쓰기)
        with pg.expect_file_chooser() as fc:
            pg.click("#storeImport")
        fc.value.set_files(files[:1])
        pg.wait_for_timeout(500)
        assert len(stored(pg, "seekers")) == 2 and len(stored(pg, "applications")) == 2
        # 팀원 A가 지원한 회사에서 팀원 구직자가 지원자로 보이고, 채용 확정까지 이어짐
        open_company(pg, company_key_for(pg, jids[0])); hire_stored(pg)
        assert "팀원A구직" in pg.inner_text("#ctDoc")
        assert not pg.errors, pg.errors
        pg.context.close()
    finally:
        proc.kill()



# ---------- 2026-10-17: 서명 변경 ----------
def test_change_worker_and_employer_signature_after_save(app):
    """저장한 계약서에서 근로자 서명·사업주 서명(날인)을 각각 바꾸고, 이력이 남고, 법인 인장으로 되돌릴 수 있음"""
    pg = app
    jid = seeker_apply(pg)
    open_company(pg, company_key_for(pg, jid)); hire_stored(pg)
    assert pg.locator("#ctSignBtns [data-resign=worker]").count() == 0  # 서명 전에는 '변경' 없음
    draw_sign(pg); save_contract(pg)
    first = stored(pg, "contracts")[0]["worker_sign"]
    # 근로자 서명 변경 → 인장으로 (계약 내용 그대로면 바로 저장)
    pg.click("#ctSignBtns [data-resign=worker]")
    pg.click("dialog.sign-dlg [data-tab=seal]"); pg.click("dialog.sign-dlg [data-fake]"); pg.click("dialog.sign-dlg [data-ok]")
    pg.wait_for_function("document.querySelector('#toast').textContent.includes('근로자 서명을(를) 바꿔 저장')")
    ct = stored(pg, "contracts")[0]
    assert ct["worker_sign"] != first and ct["sign_kind"] == "인장" and ct["status"] == "체결 완료"
    # 사업주 서명 변경 (서명 창 제목이 사업주)
    pg.click("#ctSignBtns [data-resign=employer]")
    assert "사업주 서명" in pg.inner_text("dialog.sign-dlg h3")
    box = pg.locator(".sign-pad").bounding_box()
    pg.mouse.move(box["x"] + 30, box["y"] + 60); pg.mouse.down(); pg.mouse.move(box["x"] + 200, box["y"] + 120); pg.mouse.up()
    pg.click("dialog.sign-dlg [data-ok]")
    pg.wait_for_function("document.querySelector('#toast').textContent.includes('사업주 서명·날인을(를) 바꿔 저장')")
    ct = stored(pg, "contracts")[0]
    assert ct["employer_sign"] and ct["seal"] == ct["employer_sign"] and ct["employer_kind"] == "서명"
    assert [l["who"] for l in ct["sign_log"]] == ["근로자", "근로자", "사업주"]
    # 법인 인장으로 되돌리기
    pg.click("#ctSignBtns [data-resign=seal]")
    pg.wait_for_function("document.querySelector('#toast').textContent.includes('사업주 날인')")
    ct = stored(pg, "contracts")[0]
    assert not ct["employer_sign"] and ct["seal"] and ct["seal"] != first and len(ct["sign_log"]) == 4
    # 계약 내용도 고친 상태면 바로 저장하지 않고 다시 저장 안내
    pg.fill('[data-f="job"]', "웹 개발 — 화면 개발")
    pg.wait_for_selector("#ctDoc [data-sign]")  # 내용이 바뀌어 근로자 서명 초기화
    pg.click("#ctSignBtns [data-resign=employer]")
    pg.click("dialog.sign-dlg [data-tab=seal]"); pg.click("dialog.sign-dlg [data-fake]"); pg.click("dialog.sign-dlg [data-ok]")
    pg.wait_for_function("document.querySelector('#toast').textContent.includes('계약서 다시 저장')")
    assert not stored(pg, "contracts")[0]["employer_sign"]  # 아직 저장 안 됨
    # 담당자 화면 계약서 보기에 서명 이력
    pg.evaluate("async () => IeumFlow.viewContract((await IeumStore.list('contracts'))[0].id)")
    pg.wait_for_selector("dialog.doc-dlg >> text=서명 이력")
    assert "사업주 서명·날인 변경" in pg.inner_text("dialog.doc-dlg") and "법인 인장으로 되돌림" in pg.inner_text("dialog.doc-dlg")
    assert not pg.errors, pg.errors
