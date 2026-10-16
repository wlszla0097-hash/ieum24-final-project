/* 근로계약서·급여명세서 문서 + 서명/인장 — window.IeumContract
 *
 * - 근로계약서: 고용노동부 표준근로계약서(기간의 정함이 없는 경우 / 있는 경우)의 항목 순서와 문구를 따른다.
 *   값은 저장된 구직자 정보(JSON)와 공고 조건으로 채우고, 문서는 저장하지 않고 값(JSON)으로 다시 그린다.
 * - 사업주 날인: 회사별 시연용 가상 법인 인장(data/synthetic/seals/<사업자번호>.png, 없으면 화면에서 그림)
 * - 근로자 서명: 서명란 버튼 → 직접 그리기 또는 인장 이미지 올리기 (작게 줄인 PNG만 저장)
 * - 급여명세서: 근로기준법 제48조 임금명세서 기재사항(성명·지급일·임금총액·항목별 금액·계산방법·공제 내역)
 */
(function () {
"use strict";
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const won = (n) => Number(n || 0).toLocaleString("ko-KR");
const IMG_OK = /^(data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+|\/data\/synthetic\/seals\/\d{10}\.png)$/;
const safeImg = (u) => (IMG_OK.test(String(u || "")) ? u : "");
const pad = (n) => String(n).padStart(2, "0");
const ymd = (s) => { const [y, m, d] = String(s || "").split("-"); return y ? `${y}년 ${Number(m)}월 ${Number(d)}일` : "    년   월   일"; };
const mins = (t) => { const [h, m] = String(t || "0:0").split(":").map(Number); return h * 60 + (m || 0); };
const hm = (t) => { const [h, m] = String(t || "").split(":"); return h ? `${Number(h)}시 ${pad(m || 0)}분` : "  시  분"; };

/** 공고 + 구직자(근로자) → 계약서 값 */
function defaults(post, worker, start) {
  const fixedTerm = post.emp_type === "계약직";
  const end = fixedTerm ? (() => { const d = new Date(start); d.setFullYear(d.getFullYear() + 1); d.setDate(d.getDate() - 1); return d.toISOString().slice(0, 10); })() : "";
  return {
    kind: fixedTerm ? "기간" : "무기", company: post.company, busino: post.busino || "", ceo: post.ceo ? `대표이사 ${post.ceo}` : "대표이사 (가상)",
    company_addr: `${post.region || ""} (가상 주소)`, worker: worker.name, worker_id: worker.id,
    start_date: start, end_date: end, place: `${post.company} ${post.region || ""} 사업장`, job: `${post.job || ""} — ${post.title || ""}`.replace(/^ — /, ""),
    t_start: "09:00", t_end: "18:00", b_start: "12:00", b_end: "13:00", days: 5, holiday: "일",
    wage_type: "월급", base_wage: Number(post.wage) || 0, bonus: 0, allow_name: "", allow_amount: 0,
    payday: 10, pay_method: "통장", ins: { emp: true, acc: true, pen: true, hea: true }, sign_date: start,
  };
}
function hours(c) {
  const daily = Math.max(0, (mins(c.t_end) - mins(c.t_start) - (mins(c.b_end) - mins(c.b_start))) / 60);
  return { daily, weekly: Math.round(daily * (Number(c.days) || 0) * 10) / 10, breakMin: Math.max(0, mins(c.b_end) - mins(c.b_start)) };
}
/** 규칙엔진(/api/cases → labor.py)에 넘길 근로조건 */
function toCheck(c) {
  const h = hours(c);
  return { employment_type: c.kind === "기간" ? "기간제" : "정규직", wage_type: "월급", start_date: c.start_date, end_date: c.kind === "기간" ? c.end_date : "",
    base_wage: Number(c.base_wage) || 0, allowances: Number(c.allow_amount) || 0, weekly_hours: h.weekly, daily_hours: h.daily, break_minutes: h.breakMin,
    has_holiday: !!c.holiday, has_leave: true, has_place: !!c.place, has_job: !!c.job, has_payday: !!c.payday };
}

/** 표준근로계약서 HTML. opts: {seal, sign, signable} */
function docHtml(c, opts = {}) {
  const h = hours(c), chk = (v) => (v ? "■" : "□"), seal = safeImg(opts.seal), sign = safeImg(opts.sign);
  const term = c.kind === "기간"
    ? `<li><b>근로계약기간</b> : ${ymd(c.start_date)}부터 ${ymd(c.end_date)}까지</li>`
    : `<li><b>근로개시일</b> : ${ymd(c.start_date)}부터</li>`;
  const signSlot = sign ? `<img class="lc-sign" src="${esc(sign)}" alt="근로자 서명">`
    : opts.signable ? `<button class="btn primary sm lc-sign-btn" type="button" data-sign>✍ 서명 또는 인장</button>` : `<span class="lc-wait">(서명 대기)</span>`;
  return `<article class="lc-doc">
    <h3 class="lc-title">표준근로계약서<small>(기간의 정함이 ${c.kind === "기간" ? "있는" : "없는"} 경우)</small></h3>
    <p><u>${esc(c.company)}</u>(이하 "사업주"라 함)과(와) <u>${esc(c.worker)}</u>(이하 "근로자"라 함)은 다음과 같이 근로계약을 체결한다.</p>
    <ol class="lc-items">
      ${term}
      <li><b>근 무 장 소</b> : ${esc(c.place)}</li>
      <li><b>업무의 내용</b> : ${esc(c.job)}</li>
      <li><b>소정근로시간</b> : ${hm(c.t_start)}부터 ${hm(c.t_end)}까지 (휴게시간 : ${hm(c.b_start)} ~ ${hm(c.b_end)})<small class="lc-calc">1일 ${h.daily}시간 · 주 ${h.weekly}시간</small></li>
      <li><b>근무일/휴일</b> : 매주 ${esc(c.days)}일 근무, 주휴일 매주 ${esc(c.holiday)}요일</li>
      <li><b>임 금</b>
        <div>- 월(일, 시간)급 : ${won(c.base_wage)}원</div>
        <div>- 상여금 : 있음 (${c.bonus > 0 ? "○" : " "}) ${c.bonus > 0 ? `${won(c.bonus)}원` : "______원"}, 없음 (${c.bonus > 0 ? " " : "○"})</div>
        <div>- 기타급여(제수당 등) : 있음 (${c.allow_amount > 0 ? "○" : " "}), 없음 (${c.allow_amount > 0 ? " " : "○"})${c.allow_amount > 0 ? `<br>&nbsp;&nbsp;· ${esc(c.allow_name || "고정수당")} ${won(c.allow_amount)}원` : ""}</div>
        <div>- 임금지급일 : 매월 ${esc(c.payday)}일 (휴일의 경우는 전일 지급)</div>
        <div>- 지급방법 : 근로자에게 직접지급 (${c.pay_method === "직접" ? "○" : " "}), 근로자 명의 예금통장에 입금 (${c.pay_method === "직접" ? " " : "○"})</div></li>
      <li><b>연차유급휴가</b><div>- 연차유급휴가는 근로기준법에서 정하는 바에 따라 부여함</div></li>
      <li><b>사회보험 적용여부</b>(해당란에 체크)<div>${chk(c.ins.emp)} 고용보험 ${chk(c.ins.acc)} 산재보험 ${chk(c.ins.pen)} 국민연금 ${chk(c.ins.hea)} 건강보험</div></li>
      <li><b>근로계약서 교부</b><div>- 사업주는 근로계약을 체결함과 동시에 본 계약서를 사본하여 근로자의 교부요구와 관계없이 근로자에게 교부함(근로기준법 제17조 이행)</div></li>
      <li><b>근로계약, 취업규칙 등의 성실한 이행의무</b><div>- 사업주와 근로자는 각자가 근로계약, 취업규칙, 단체협약을 지키고 성실하게 이행하여야 함</div></li>
      <li><b>기 타</b><div>- 이 계약에 정함이 없는 사항은 근로기준법령에 의함</div></li>
    </ol>
    <p class="lc-date">${ymd(c.sign_date)}</p>
    <div class="lc-parties">
      <div><b>(사업주)</b> 사업체명 : ${esc(c.company)} <span class="muted">(사업자등록번호 ${esc(fmtBiz(c.busino))})</span><br>
        주 소 : ${esc(c.company_addr)}<br>
        대 표 자 : ${esc(c.ceo)} <span class="lc-slot">(서명)${seal ? `<img class="lc-seal" src="${esc(seal)}" alt="법인 인장(가상)">` : ""}</span></div>
      <div><b>(근로자)</b> 주 소 : <span class="muted">(시연 생략 — 실제 서비스는 고용24 회원정보)</span><br>
        연 락 처 : <span class="muted">(시연 생략)</span><br>
        성 명 : ${esc(c.worker)} <span class="lc-slot">(서명)${signSlot}</span></div>
    </div>
    <p class="lc-foot">고용노동부 표준근로계약서 양식 · 합성 데이터 시연용 (실제 인물·기업·계약 아님)</p>
  </article>`;
}
const fmtBiz = (b) => (String(b || "").length === 10 ? `${b.slice(0, 3)}-${b.slice(3, 5)}-${b.slice(5)}` : "미등록");

/* ---------- 인장 ---------- */
function drawSeal(text, { ring = "", size = 240, square = false } = {}) {
  const cv = document.createElement("canvas"); cv.width = cv.height = size; const g = cv.getContext("2d");
  const red = "rgba(200,30,30,.92)", c = size / 2, r = size / 2 - 8;
  g.strokeStyle = g.fillStyle = red; g.textAlign = "center"; g.textBaseline = "middle";
  const F = (px) => (g.font = `700 ${px}px "Noto Serif KR","Nanum Myeongjo","Batang",serif`);
  if (square) {
    g.lineWidth = size * 0.05; g.strokeRect(size * 0.08, size * 0.08, size * 0.84, size * 0.84);
    const chars = [...text.replace(/\s/g, "")].slice(0, 4);
    if (chars.length === 2) { F(size * 0.36); g.fillText(chars[0], c, c - size * 0.18); g.fillText(chars[1], c, c + size * 0.18); }
    else { F(size * (chars.length <= 1 ? 0.5 : 0.28)); const grid = chars.length === 3 ? [[c, c - size * 0.22], [c - size * 0.18, c + size * 0.17], [c + size * 0.18, c + size * 0.17]] : [[c + size * 0.18, c - size * 0.18], [c + size * 0.18, c + size * 0.18], [c - size * 0.18, c - size * 0.18], [c - size * 0.18, c + size * 0.18]]; chars.forEach((ch, i) => g.fillText(ch, ...(grid[i] || [c, c]))); }
    return cv.toDataURL("image/png");
  }
  g.lineWidth = size * 0.035; g.beginPath(); g.arc(c, c, r, 0, Math.PI * 2); g.stroke();
  g.lineWidth = size * 0.015; g.beginPath(); g.arc(c, c, r * 0.62, 0, Math.PI * 2); g.stroke();
  if (ring) {
    F(size * 0.095); const chars = [...ring], step = (Math.PI * 2) / chars.length;
    chars.forEach((ch, i) => { g.save(); g.translate(c, c); g.rotate(i * step); g.fillText(ch, 0, -r * 0.81); g.restore(); });
  }
  F(size * 0.15); g.fillText(text.slice(0, 2), c, c - size * 0.09); g.fillText(text.slice(2, 4), c, c + size * 0.09);
  return cv.toDataURL("image/png");
}
/** 회사 법인 인장(가상): 미리 만들어 둔 파일이 있으면 그것, 없으면 화면에서 그림 */
function sealFor(busino, company) {
  const name = String(company || "").replace("(가상)", "").trim();
  if (/^\d{10}$/.test(String(busino || ""))) {
    const url = `/data/synthetic/seals/${busino}.png`;
    return new Promise((ok) => { const im = new Image(); im.onload = () => ok(url); im.onerror = () => ok(drawSeal("대표이사", { ring: `주식회사 ${name} · 시연용 가상 인장 · ` })); im.src = url; });
  }
  return Promise.resolve(drawSeal("대표이사", { ring: `주식회사 ${name} · 시연용 가상 인장 · ` }));
}
/** 이미지 → 최대 240px PNG (저장 용량 줄이기) */
function shrink(src, max = 240) {
  return new Promise((ok, no) => {
    const im = new Image();
    im.onload = () => { const k = Math.min(1, max / Math.max(im.width, im.height)); const cv = document.createElement("canvas");
      cv.width = Math.round(im.width * k); cv.height = Math.round(im.height * k); cv.getContext("2d").drawImage(im, 0, 0, cv.width, cv.height); ok(cv.toDataURL("image/png")); };
    im.onerror = () => no(new Error("이미지를 읽지 못했습니다."));
    im.src = src;
  });
}

/* ---------- 근로자 서명 창: 직접 그리기 / 인장 이미지 올리기 ---------- */
function openSign(name) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog"); dlg.className = "sign-dlg";
    dlg.innerHTML = `<form method="dialog" class="sign-box">
      <h3>근로자 서명 — ${esc(name)}</h3>
      <div class="tabs" role="tablist"><button type="button" class="tab active" data-tab="draw">✍ 직접 서명</button><button type="button" class="tab" data-tab="seal">🔴 인장 이미지</button></div>
      <div data-pane="draw"><canvas class="sign-pad" width="460" height="180" aria-label="서명 그리는 곳"></canvas>
        <div class="btn-row"><button type="button" class="btn ghost sm" data-clear>지우기</button><span class="muted">마우스나 손가락으로 서명하세요.</span></div></div>
      <div data-pane="seal" hidden>
        <div class="field"><label>인장 이미지 첨부 (PNG·JPG)</label><input type="file" accept="image/png,image/jpeg,image/webp" data-file></div>
        <div class="btn-row"><button type="button" class="btn ghost sm" data-fake>시연용 가상 인장 만들기</button><span class="muted">실제 인감 이미지는 올리지 마세요.</span></div>
        <div class="seal-prev" data-prev></div></div>
      <p class="msg error" data-msg hidden></p>
      <div class="btn-row end"><button type="button" class="btn ghost" data-cancel>취소</button><button type="button" class="btn primary" data-ok>서명 넣기</button></div>
    </form>`;
    document.body.appendChild(dlg);
    let tab = "draw", sealData = "", drawn = false;
    const pad = $(".sign-pad", dlg), g = pad.getContext("2d");
    g.lineWidth = 3.2; g.lineCap = g.lineJoin = "round"; g.strokeStyle = "#111";
    let down = false;
    const pos = (e) => { const r = pad.getBoundingClientRect(); return [(e.clientX - r.left) * (pad.width / r.width), (e.clientY - r.top) * (pad.height / r.height)]; };
    pad.addEventListener("pointerdown", (e) => { down = true; pad.setPointerCapture(e.pointerId); g.beginPath(); g.moveTo(...pos(e)); });
    pad.addEventListener("pointermove", (e) => { if (!down) return; g.lineTo(...pos(e)); g.stroke(); drawn = true; });
    ["pointerup", "pointercancel"].forEach((t) => pad.addEventListener(t, () => (down = false)));
    $("[data-clear]", dlg).onclick = () => { g.clearRect(0, 0, pad.width, pad.height); drawn = false; };
    $$(".tab", dlg).forEach((b) => (b.onclick = () => { tab = b.dataset.tab; $$(".tab", dlg).forEach((x) => x.classList.toggle("active", x === b)); $$("[data-pane]", dlg).forEach((p) => (p.hidden = p.dataset.pane !== tab)); }));
    const showSeal = (u) => { sealData = u; $("[data-prev]", dlg).innerHTML = `<img src="${esc(safeImg(u))}" alt="인장 미리보기">`; };
    $("[data-file]", dlg).onchange = (e) => { const f = e.target.files[0]; if (!f) return;
      if (f.size > 3 * 1024 * 1024) return showErr("3MB 이하 이미지만 올릴 수 있어요.");
      const r = new FileReader(); r.onload = async () => { try { showSeal(await shrink(r.result)); } catch (err) { showErr(err.message); } }; r.readAsDataURL(f); };
    $("[data-fake]", dlg).onclick = () => showSeal(drawSeal(String(name).replace(/\(가상\)/, "").trim().slice(0, 3) + "인", { square: true, size: 160 }));
    const showErr = (t) => { const m = $("[data-msg]", dlg); m.textContent = t; m.hidden = !t; };
    const close = (v) => { dlg.close(); dlg.remove(); resolve(v); };
    $("[data-cancel]", dlg).onclick = () => close(null);
    dlg.addEventListener("cancel", () => close(null));
    $("[data-ok]", dlg).onclick = async () => {
      if (tab === "draw") {
        if (!drawn) return showErr("서명을 그려 주세요.");
        close({ kind: "서명", data: await shrink(pad.toDataURL("image/png"), 300) });
      } else {
        if (!sealData) return showErr("인장 이미지를 올리거나 가상 인장을 만들어 주세요.");
        close({ kind: "인장", data: sealData });
      }
    };
    dlg.showModal();
  });
}

/* ---------- 급여명세서 (근로기준법 제48조 임금명세서 기재사항) ---------- */
function synthPay(gross, ym) {
  const f10 = (n) => Math.floor(n / 10) * 10; // 2026 근로자 부담 요율 근사 + 간이 소득세 — 시연용
  const np = f10(Math.min(gross, 6_370_000) * 0.0475), hi = f10(gross * 0.03595), ltc = f10(hi * 0.9448 / 7.19), ei = f10(gross * 0.009);
  const tax = f10(gross * 0.018), local = f10(tax * 0.1);
  const ded = [["국민연금", np], ["건강보험", hi], ["장기요양보험", ltc], ["고용보험", ei], ["소득세", tax], ["지방소득세", local]];
  const dedTotal = ded.reduce((a, [, v]) => a + v, 0);
  return { ym, gross, ded, dedTotal, net: gross - dedTotal };
}
function payslipHtml(p) {
  const pr = p.prorate, part = (full) => (pr ? ` — 일할 계산: ${won(full)} × ${pr.days}/${pr.dim}일 (월 중간 입사·종료)` : "");
  const rows = [["기본급", p.base, `월 소정근로 ${p.monthly_hours}시간 기준 월급 (근로계약서 6항)${part(p.base_full)}`]];
  if (p.allow) rows.push([p.allow_name || "고정수당", p.allow, `근로계약서 6항 기타급여${part(p.allow_full)}`]);
  return `<article class="lc-doc ps-doc">
    ${p.voided ? `<p class="msg error">정정(취소)된 명세서 — ${esc(p.voided.reason)}</p>` : ""}
    <h3 class="lc-title">임금명세서<small>${esc(p.ym.replace("-", "년 "))}월분</small></h3>
    <table class="ps-head"><tr><th>회사명</th><td>${esc(p.company)}</td><th>지급일</th><td>${esc(p.pay_date)}</td></tr>
      <tr><th>성명</th><td>${esc(p.worker)}</td><th>사원번호</th><td>${esc(p.emp_no)}</td></tr></table>
    <table class="ps-tbl"><thead><tr><th>지급 항목</th><th>금액(원)</th><th>계산 방법</th></tr></thead><tbody>
      ${rows.map(([k, v, how]) => `<tr><td>${esc(k)}</td><td class="num">${won(v)}</td><td>${esc(how)}</td></tr>`).join("")}
      <tr class="sum"><td>임금총액</td><td class="num">${won(p.gross)}</td><td></td></tr></tbody></table>
    <table class="ps-tbl"><thead><tr><th>공제 항목</th><th>금액(원)</th><th></th></tr></thead><tbody>
      ${p.ded.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${won(v)}</td><td></td></tr>`).join("")}
      <tr class="sum"><td>공제총액</td><td class="num">${won(p.dedTotal)}</td><td></td></tr></tbody></table>
    <p class="ps-net">실지급액 <b>${won(p.net)}원</b></p>
    <p class="lc-foot">근로기준법 제48조 임금명세서 · 공제액은 시연용 근사치 · 합성 데이터 (실제 인물·기업 아님)</p>
  </article>`;
}

/* ---------- 시연용 은행 이체확인증 (가상 은행 — 실제 은행 양식·상호 아님) ---------- */
const BANKS = ["가람은행", "누리은행", "솔빛은행"];
/** c: {bank, date, sender, recipient, amount, memo} → JPEG dataURL */
function drawBankTransfer(c) {
  const cv = document.createElement("canvas"); cv.width = 640; cv.height = 560; const g = cv.getContext("2d");
  const F = (sz, b) => (g.font = `${b ? "700 " : ""}${sz}px "Noto Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif`);
  const bank = `${c.bank || BANKS[0]}(가상)`;
  g.fillStyle = "#fff"; g.fillRect(0, 0, 640, 560);
  g.fillStyle = "#14532d"; g.fillRect(0, 0, 640, 70);
  g.fillStyle = "#fff"; g.textBaseline = "middle"; F(24, 1); g.fillText(bank, 28, 36);
  F(13); g.textAlign = "right"; g.fillText("인터넷뱅킹 · 시연용 가상 은행", 612, 36); g.textAlign = "left";
  g.fillStyle = "#111"; F(28, 1); g.textAlign = "center"; g.fillText("이 체 확 인 증", 320, 112); g.textAlign = "left";
  const acct = (n) => `${n}-***-***${String(n * 7919).slice(-3)}`;
  const rows = [["거래일시", `${c.date} 09:12:30`], ["출금계좌", acct(110)], ["보내는 분(예금주)", c.sender], ["입금은행", bank],
    ["입금계좌", acct(352)], ["받는 분(예금주)", c.recipient], ["이체금액", `${won(c.amount)}원`], ["수수료", "0원"], ["받는 분 통장 표시", c.memo || "급여"], ["처리결과", "정상 처리"]];
  g.strokeStyle = "#c9ced8"; g.lineWidth = 1;
  rows.forEach(([k, v], i) => {
    const y = 140 + i * 34;
    g.fillStyle = i % 2 ? "#fff" : "#f4f7f4"; g.fillRect(28, y, 584, 34); g.strokeRect(28, y, 584, 34);
    g.beginPath(); g.moveTo(190, y); g.lineTo(190, y + 34); g.stroke();
    g.fillStyle = "#555"; F(14); g.fillText(k, 40, y + 17);
    g.fillStyle = "#111"; F(k === "이체금액" ? 18 : 15, k === "이체금액" || k.startsWith("받는 분(") || k.startsWith("보내는")); g.fillText(v, 204, y + 17);
  });
  F(14); g.fillStyle = "#111"; g.textAlign = "center"; g.fillText("위와 같이 이체되었음을 확인합니다.", 320, 498);
  F(12); g.fillStyle = "#888"; g.fillText(`${bank} · 합성 데이터 시연용 (실제 은행·거래 아님) · 계좌번호는 가림 처리`, 320, 532); g.textAlign = "left";
  g.strokeStyle = "rgba(200,30,30,.85)"; g.lineWidth = 3; g.beginPath(); g.arc(560, 488, 30, 0, Math.PI * 2); g.stroke();
  g.fillStyle = "rgba(200,30,30,.85)"; F(11, 1); g.textAlign = "center"; g.fillText(c.bank || BANKS[0], 560, 482); g.fillText("(가상)", 560, 497); g.textAlign = "left";
  return cv.toDataURL("image/jpeg", 0.9);
}

/** 문서 보기 창 (담당자·근로자 화면 공용) */
function view(title, html) {
  const dlg = document.createElement("dialog"); dlg.className = "doc-dlg";
  dlg.innerHTML = `<div class="doc-dlg-head"><b>${esc(title)}</b><button class="btn ghost sm" type="button" data-x>닫기</button></div><div class="doc-dlg-body">${html}</div>`;
  document.body.appendChild(dlg);
  const close = () => { dlg.close(); dlg.remove(); };
  $("[data-x]", dlg).onclick = close; dlg.addEventListener("cancel", close);
  dlg.showModal();
  return dlg;
}

window.IeumContract = { drawBankTransfer, BANKS, defaults, hours, toCheck, docHtml, sealFor, drawSeal, openSign, synthPay, payslipHtml, view, safeImg, fmtBiz };
})();
