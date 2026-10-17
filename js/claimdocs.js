/* ⑦ 참여사업 관리 — 월별 서류(급여명세서·이체확인증) 사전 점검 (이음24 기업 화면)
 *
 * 흐름: 기업이 매월 서류를 올림 → /api/certificate (kind=claimdoc) 에서 AI가 성명·귀속월·금액을 판독
 *       → 규칙엔진이 그 달 기준으로 점검(최저임금, 명세서·이체액 일치, 누적 평균 상한, 1회차 누적) → 결과 표시
 *       → 신청 시기가 되면 결과가 담당자 확인 대시보드의 신청 건에 붙는다(다시 걷지 않음).
 * 시연용 합성 서류는 브라우저에서 그림으로 만든다. AI 키가 없는 환경에서는 그림을 만들 때 기록한 값(sample_truth)으로 점검한다.
 */
(function () {
"use strict";
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const won = (n) => Number(n || 0).toLocaleString("ko-KR");
const pad = (n) => String(n).padStart(2, "0");
const badge = (l) => `<span class="badge ${esc(String(l).replace(/\s/g, ""))}">${esc(l)}</span>`;
const S = { ctx: null, rows: {}, onSend: null };

function ymAdd(ym, k) { const [y, m] = ym.split("-").map(Number); const t = y * 12 + m - 1 + k; return `${Math.floor(t / 12)}-${pad(t % 12 + 1)}`; }
function thisYm() { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; }

/** 합성 급여 값: 4대보험(2026 근로자 요율 근사) + 간이 소득세. 시연용 */
function synthPay(gross, ym) {
  const f10 = (n) => Math.floor(n / 10) * 10;
  const np = f10(Math.min(gross, 6_370_000) * 0.0475), hi = f10(gross * 0.03595), ltc = f10(hi * 0.9448 / 7.19), ei = f10(gross * 0.009);
  const tax = f10(gross * 0.018), local = f10(tax * 0.1);
  const ded = [["국민연금", np], ["건강보험", hi], ["장기요양", ltc], ["고용보험", ei], ["소득세", tax], ["지방소득세", local]];
  const dedTotal = ded.reduce((a, [, v]) => a + v, 0);
  return { gross, ded, dedTotal, net: gross - dedTotal, ym };
}

/** 합성 급여명세서·이체확인증 그림 (JPEG base64) */
const K = 2;  // 합성 서류 2배 해상도 (AI 판독 선명도)
function drawPayslip(c) {
  const cv = document.createElement("canvas"); cv.width = 620 * K; cv.height = 760 * K; const g = cv.getContext("2d"); g.scale(K, K);
  g.fillStyle = "#fff"; g.fillRect(0, 0, cv.width, cv.height);
  g.fillStyle = "#111"; g.textBaseline = "top";
  const F = (sz, b) => (g.font = `${b ? "700 " : ""}${sz}px "Noto Sans KR","Malgun Gothic",sans-serif`);
  F(28, 1); g.textAlign = "center"; g.fillText("임 금 명 세 서", 310, 30); g.textAlign = "left";
  F(16); g.fillText(`회사명: ${c.company}`, 40, 90); g.fillText(`성명: ${c.name}`, 40, 116);
  g.fillText(`귀속월: ${c.ym.replace("-", "년 ")}월`, 330, 90); g.fillText(`지급일: ${c.payDate}`, 330, 116);
  g.strokeStyle = "#333"; g.lineWidth = 1.5; g.strokeRect(40, 150, 540, 470);
  g.beginPath(); g.moveTo(310, 150); g.lineTo(310, 620); g.moveTo(40, 186); g.lineTo(580, 186); g.stroke();
  F(16, 1); g.fillText("지급 항목", 60, 160); g.fillText("공제 항목", 330, 160);
  F(15);
  const pays = [["기본급", c.gross]];
  pays.forEach(([k, v], i) => { g.fillText(k, 60, 200 + i * 30); g.textAlign = "right"; g.fillText(won(v), 295, 200 + i * 30); g.textAlign = "left"; });
  c.ded.forEach(([k, v], i) => { g.fillText(k, 330, 200 + i * 30); g.textAlign = "right"; g.fillText(won(v), 565, 200 + i * 30); g.textAlign = "left"; });
  g.beginPath(); g.moveTo(40, 560); g.lineTo(580, 560); g.stroke();
  F(16, 1); g.fillText("지급총액", 60, 575); g.textAlign = "right"; g.fillText(won(c.gross), 295, 575);
  g.textAlign = "left"; g.fillText("공제총액", 330, 575); g.textAlign = "right"; g.fillText(won(c.dedTotal), 565, 575); g.textAlign = "left";
  F(20, 1); g.fillText("실지급액", 60, 645); g.textAlign = "right"; g.fillText(`${won(c.net)}원`, 580, 645); g.textAlign = "left";
  F(12); g.fillStyle = "#888"; g.fillText("합성 데이터 · 시연용 (실제 인물·기업 아님)", 40, 720);
  return cv.toDataURL("image/jpeg", 0.85);
}
function drawTransfer(c) {
  const cv = document.createElement("canvas"); cv.width = 620 * K; cv.height = 400 * K; const g = cv.getContext("2d"); g.scale(K, K);
  g.fillStyle = "#fff"; g.fillRect(0, 0, cv.width, cv.height); g.fillStyle = "#0b3d91"; g.fillRect(0, 0, 620, 64);
  g.textBaseline = "top"; const F = (sz, b) => (g.font = `${b ? "700 " : ""}${sz}px "Noto Sans KR","Malgun Gothic",sans-serif`);
  g.fillStyle = "#fff"; F(24, 1); g.fillText("이체확인증", 30, 18);
  g.fillStyle = "#111"; F(16);
  const rows = [["이체일시", `${c.date} 09:12`], ["보내는 분", c.sender], ["받는 분", c.name], ["입금 은행", "가상은행 ***-****-1234"], ["이체금액", `${won(c.amount)}원`], ["메모", `${c.ym.slice(5)}월 급여`]];
  rows.forEach(([k, v], i) => { g.fillStyle = "#666"; g.fillText(k, 40, 90 + i * 40); g.fillStyle = "#111"; F(k === "이체금액" ? 20 : 16, k === "이체금액"); g.fillText(v, 180, 88 + i * 40); F(16); });
  F(12); g.fillStyle = "#888"; g.fillText("합성 데이터 · 시연용 (실제 거래 아님)", 40, 360);
  return cv.toDataURL("image/jpeg", 0.85);
}
const b64 = (dataUrl) => dataUrl.split(",")[1];
const fileToB64 = (f) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok({ media_type: f.type, data: b64(r.result) }); r.onerror = no; r.readAsDataURL(f); });

function months() { return Array.from({ length: 6 }, (_, i) => ymAdd(S.ctx.hireYm, i)); }

/** 시연 설정: 입사를 6개월 전 1일로 가정해 지난 6개월분 서류를 올려 볼 수 있게 한다 */
function open(cs, contract, worker) {
  const now = thisYm(), hireYm = ymAdd(now, -6);
  S.ctx = { cs, company: cs.company, worker, hireYm, hire_date: `${hireYm}-01`, weekly_hours: Number(contract.weekly_hours) || 40,
            gross: Number(String(contract.base_wage || "").replace(/[^\d]/g, "")) + Number(String(contract.allowances || "").replace(/[^\d]/g, "")) || 2600000 };
  S.rows = {};
  $("#docsWho").innerHTML = `근로자 <b>${esc(worker)}</b> (가상) · ${esc(cs.company)}<br><small>시연: 입사일을 ${esc(S.ctx.hire_date)}로 가정 — 지난 6개월분을 올려 봅니다. 급여일 익월 10일</small>`;
  $("#docsMonths").innerHTML = months().map(rowHtml).join("");
  $("#docsSummary").innerHTML = "";
  bindRows();
  $("#docsPanel").hidden = false;
}
function payDateOf(ym) { return `${ymAdd(ym, 1)}-10`; }
function rowHtml(ym) {
  return `<div class="month-row" data-ym="${ym}">
    <div class="mth">${Number(ym.slice(5))}월분<small>${ym} · 지급 ${payDateOf(ym)}</small></div>
    <div><div class="thumbs" data-thumbs></div><button class="btn ghost sm redo" type="button" data-redo>다시 올리기</button>
      <div class="btns up-btns" style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap"><button class="btn ghost sm" type="button" data-sample>합성 서류 넣기</button>
      <label class="btn ghost sm">명세서<input type="file" accept="image/*,application/pdf" data-file="payslip" hidden></label>
      <label class="btn ghost sm">이체확인증<input type="file" accept="image/*,application/pdf" data-file="transfer" hidden></label></div></div>
    <div data-result><span class="muted">서류를 올리면 그 달 기준으로 바로 점검합니다.</span></div></div>`;
}
function bindRows() {
  $$("#docsMonths .month-row").forEach((row) => {
    const ym = row.dataset.ym;
    $("[data-sample]", row).onclick = () => runSample(ym);
    $("[data-redo]", row).onclick = () => row.classList.remove("done");
    $$("[data-file]", row).forEach((inp) => (inp.onchange = async () => {
      const r = (S.rows[ym] = S.rows[ym] || {}); r.files = r.files || {};
      r.files[inp.dataset.file] = await fileToB64(inp.files[0]); r.truth = null;
      thumbs(row, r);
      if (r.files.payslip && r.files.transfer) check(ym);
    }));
  });
}
function thumbs(row, r) {
  $("[data-thumbs]", row).innerHTML = ["payslip", "transfer"].filter((k) => r.files && r.files[k]).map((k) => {
    const f = r.files[k]; const src = `data:${f.media_type};base64,${f.data}`;
    return f.media_type.startsWith("image/") ? `<img src="${src}" alt="${k === "payslip" ? "급여명세서" : "이체확인증"}" data-zoom>` : `<span class="badge 안내">${k === "payslip" ? "명세서" : "이체확인증"} PDF</span>`;
  }).join("");
  $$("[data-zoom]", row).forEach((im) => (im.onclick = () => window.open().document.write(`<img src="${im.src}" style="max-width:100%">`)));
}
function sampleFor(ym, idx) {
  const p = synthPay(S.ctx.gross, ym);
  const amount = idx === 3 ? p.net - 30000 : p.net; // 시연: 4번째 달은 이체액이 3만원 적은 사례
  const pay = payDateOf(ym);
  const files = { payslip: { media_type: "image/jpeg", data: b64(drawPayslip({ ...p, company: S.ctx.company, name: S.ctx.worker, payDate: pay })) },
                  transfer: { media_type: "image/jpeg", data: b64(drawTransfer({ ym, date: pay, sender: S.ctx.company, name: S.ctx.worker, amount })) } };
  const truth = { payslip: { name: S.ctx.worker, ym, pay_date: pay, gross: String(p.gross), deduction: String(p.dedTotal), net: String(p.net) },
                  transfer: { recipient: S.ctx.worker, date: pay, amount: String(amount), sender: S.ctx.company } };
  return { files, truth };
}
async function runSample(ym) {
  const idx = months().indexOf(ym);
  S.rows[ym] = { ...sampleFor(ym, idx) };
  thumbs($(`.month-row[data-ym="${ym}"]`), S.rows[ym]);
  await check(ym);
}
async function check(ym) {
  const row = $(`.month-row[data-ym="${ym}"]`), r = S.rows[ym], out = $("[data-result]", row);
  out.innerHTML = '<span class="muted">AI가 서류를 읽고 그 달 기준으로 점검하는 중…</span>';
  const history = months().filter((m) => m < ym && S.rows[m] && S.rows[m].res).map((m) => ({ ym: m, gross: S.rows[m].res.payslip.gross }));
  try {
    const res = await window.ieumApi("/api/certificate", { method: "POST", timeoutMs: 45000, body: {
      kind: "claimdoc", consent: true, month: ym, files: [r.files.payslip, r.files.transfer], sample_truth: r.truth || undefined,
      ctx: { worker: S.ctx.worker, hire_date: S.ctx.hire_date, weekly_hours: S.ctx.weekly_hours, history } } });
    r.res = res; row.classList.add("done");
    const bad = res.check.items.filter((i) => i.level !== "일치"), ok = res.check.items.length - bad.length;
    out.innerHTML = `<div>${badge(res.check.level)} <b>${res.check.level === "일치" ? "이상 없음" : `확인할 항목 ${bad.length}건`}</b> <span class="muted">· 일치 ${ok}건</span></div>
      <div class="read-vals">판독(${res.source === "ai" ? `AI ${esc(res.model || "")}` : "합성 서류 기록값 — AI 미연결 환경"}): 명세서 ${esc(res.payslip.name)} · 귀속 ${esc(res.payslip.ym)} · 지급총액 ${won(res.payslip.gross)} · 실지급 ${won(res.payslip.net)} / 이체 ${esc(res.transfer.recipient)} ${won(res.transfer.amount)}원 (${esc(res.transfer.date)})</div>
      ${bad.map((i) => `<div class="check-item">${badge(i.level)}<div><b>${esc(i.item)}</b><br>${esc(i.detail)}<div class="basis">근거: ${esc(i.basis)}</div></div></div>`).join("")}`;
  } catch (err) {
    out.innerHTML = `<div class="msg error">${esc(err.message)}</div>`;
  }
  summary();
}
function summary() {
  const ms = months(), done = ms.filter((m) => S.rows[m] && S.rows[m].res);
  if (!done.length) { $("#docsSummary").innerHTML = ""; return; }
  const mis = done.filter((m) => S.rows[m].res.check.level === "불일치"), chk = done.filter((m) => S.rows[m].res.check.level === "확인 필요");
  const gross = done.map((m) => Number(String(S.rows[m].res.payslip.gross).replace(/[^\d]/g, "")) || 0);
  const avg = Math.floor(gross.reduce((a, b) => a + b, 0) / gross.length), total = gross.reduce((a, b) => a + b, 0);
  const missing = ms.filter((m) => !done.includes(m));
  const open1 = `${ymAdd(S.ctx.hireYm, 6)}-01`;
  S.ctx.docs = { program: "청년일자리도약장려금", assumed_hire: S.ctx.hire_date, expected: ms.length, uploaded: done.length, mismatch: mis.length, check: chk.length, avg, total,
    months: ms.map((m) => ({ month: m, level: S.rows[m] && S.rows[m].res ? S.rows[m].res.check.level : "미첨부",
      note: S.rows[m] && S.rows[m].res ? S.rows[m].res.check.items.filter((i) => i.level !== "일치").map((i) => `${i.item}: ${i.detail}`).join(" / ") : "" })) };
  $("#docsSummary").innerHTML = `<div class="docs-sum">
      <div><small>첨부</small><b>${done.length}/${ms.length}개월</b></div>
      <div><small>불일치 · 확인 필요</small><b>${mis.length} · ${chk.length}</b></div>
      <div><small>평균 월 지급총액</small><b>${won(avg)}원</b></div>
      <div><small>1회차 신청 가능</small><b>${open1}부터</b></div></div>
    ${mis.length ? `<p class="msg info">${mis.map((m) => `${Number(m.slice(5))}월분`).join(", ")} 서류에 서로 다른 값이 있습니다. 신청 전에 정정 서류(추가 이체 내역 등)를 함께 올려 두세요.</p>` : ""}
    ${missing.length ? `<p class="meta">아직 올리지 않은 달: ${missing.join(", ")}</p>` : ""}
    <button class="btn primary block" id="docsSend" type="button" ${done.length ? "" : "disabled"}>점검된 서류를 담당자 확인 대시보드 신청 건에 연결 (시연)</button>`;
  $("#docsSend").onclick = () => { if (S.onSend) S.onSend(S.ctx.docs); $("#docsSend").disabled = true; $("#docsSend").textContent = "연결 완료 ✓"; };
}
async function runAll() {
  const b = $("#docsAll"); b.disabled = true;
  for (const ym of months()) { await runSample(ym); }
  b.disabled = false;
}

window.IeumDocs = { drawTransfer, b64, fileToB64, ymAdd,
  open, setOnSend: (fn) => (S.onSend = fn),
  init() { const b = $("#docsAll"); if (b) b.onclick = runAll; }, // 기존 6개월 일괄 점검 패널(있을 때만)
  docsBlock(d) { // 담당자 확인 대시보드용
    if (!d) return "";
    const lv = (l) => (l === "미첨부" ? '<span class="badge 안내">미첨부</span>' : badge(l));
    return `<h4>월별 서류 사전 점검 (${esc(d.program)})</h4>
      <p>첨부 <b>${d.uploaded}/${d.expected}개월</b> · 불일치 ${d.mismatch} · 확인 필요 ${d.check} · 평균 월 지급총액 ${won(d.avg)}원</p>
      <div class="docs-box">${d.months.map((m) => `<div class="check-item">${lv(m.level)}<div><b>${esc(m.month)}</b>${m.note ? `<br><span class="muted">${esc(m.note)}</span>` : ""}</div></div>`).join("")}</div>
      <p class="meta">기업이 매월 올리고 점검한 서류입니다. 신청 시 다시 받지 않고 이 기록으로 확인합니다.${d.assumed_hire ? ` (시연: 입사일 ${esc(d.assumed_hire)} 가정)` : ""}</p>`;
  },
};
})();
