/* ⑥-2 채용 확정 서류 첨부 — 근로계약서·사업자등록증 (이음24 기업 화면)
 *
 * 흐름: 채용 확정 → 서류 첨부(또는 합성 예시 생성) → /api/certificate (kind=hiredoc) 에서 AI가 항목만 판독
 *       → 규칙엔진이 근로계약 점검 + 공고 입력값·공공데이터(업종·임금체불·체납) 대조 → 결과를 신청 건에 붙인다.
 * 서류는 채용 단계에서 한 번만 첨부한다. 담당자는 이 기록으로 확인하고 다시 걷지 않는다.
 * 합성 서류는 브라우저에서 그림으로 만든다(실제 양식의 항목 배치만 따르고 내용은 가상). AI 키가 없으면 그릴 때 기록한 값(sample_truth)으로 점검한다.
 */
(function () {
"use strict";
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const won = (n) => Number(n || 0).toLocaleString("ko-KR");
const badge = (l) => `<span class="badge ${esc(String(l).replace(/\s/g, ""))}">${esc(l)}</span>`;
const b64 = (u) => u.split(",")[1];
const S = { ctx: null, files: {}, truth: null, res: null, onDone: null };

const FONT = (g, sz, b) => (g.font = `${b ? "700 " : ""}${sz}px "Noto Sans KR","Malgun Gothic",sans-serif`);
const paper = (w, h) => { const k = (window.IeumContract && window.IeumContract.DOC_SCALE) || 2;  // 2배 해상도 (AI 판독 선명도)
  const cv = document.createElement("canvas"); cv.width = w * k; cv.height = h * k; const g = cv.getContext("2d"); g.scale(k, k); g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); g.fillStyle = "#111"; g.textBaseline = "top"; return [cv, g]; };

/** 표준근로계약서(기간의 정함이 없는 경우) 항목 배치를 따른 합성 그림 */
function drawContract(c) {
  const [cv, g] = paper(680, 920);
  FONT(g, 26, 1); g.textAlign = "center"; g.fillText("표 준 근 로 계 약 서", 340, 36); g.textAlign = "left";
  FONT(g, 14); g.fillText(`${c.company}(이하 "사업주")과(와) ${c.worker}(이하 "근로자")은`, 40, 88); g.fillText("다음과 같이 근로계약을 체결한다.", 40, 108);
  const lines = [
    ["1. 근로계약기간", c.end ? `${c.start}부터 ${c.end}까지` : `${c.start}부터 (기간의 정함이 없음)`],
    ["2. 근무장소", c.place || "(기재 없음)"],
    ["3. 업무의 내용", c.job || "(기재 없음)"],
    ["4. 소정근로시간", `${c.daily}시간 (09:00 ~ 18:00), 휴게시간 ${c.brk}분 · 주 ${c.weekly}시간`],
    ["5. 근무일/휴일", c.holiday ? "매주 5일 근무, 주휴일 매주 일요일" : "매주 5일 근무"],
    ["6. 임금", `월급 ${won(c.wage)}원${c.allow ? ` (수당 ${won(c.allow)}원 별도)` : ""}`],
    ["   - 지급일", c.payday ? "매월 10일 (근로자 명의 예금통장에 입금)" : "(기재 없음)"],
    ["7. 연차유급휴가", c.leave ? "근로기준법에서 정하는 바에 따라 부여" : "(기재 없음)"],
    ["8. 사회보험 적용", "고용보험 · 산재보험 · 국민연금 · 건강보험"],
  ];
  let y = 150;
  lines.forEach(([k, v]) => { FONT(g, 15, 1); g.fillText(k, 40, y); FONT(g, 15); g.fillText(v, 230, y); y += 44; });
  g.strokeStyle = "#333"; g.lineWidth = 1; g.beginPath(); g.moveTo(40, y + 10); g.lineTo(640, y + 10); g.stroke();
  FONT(g, 15); g.fillText(`${c.start.slice(0, 4)}년 ${Number(c.start.slice(5, 7))}월 ${Number(c.start.slice(8))}일`, 40, y + 30);
  g.fillText(`(사업주) 사업체명: ${c.company}   대표자: ○○○ (서명)`, 40, y + 66);
  g.fillText(`(근로자) 성명: ${c.worker} (서명)`, 40, y + 96);
  FONT(g, 12); g.fillStyle = "#888"; g.fillText("합성 데이터 · 시연용 (실제 인물·기업 아님, 주민번호·주소 미기재)", 40, 880);
  return cv.toDataURL("image/jpeg", 0.85);
}

/** 사업자등록증 항목 배치를 따른 합성 그림 */
function drawBizreg(c) {
  const [cv, g] = paper(620, 800);
  g.strokeStyle = "#8a6d3b"; g.lineWidth = 6; g.strokeRect(14, 14, 592, 772);
  FONT(g, 30, 1); g.textAlign = "center"; g.fillText("사 업 자 등 록 증", 310, 50);
  FONT(g, 15); g.fillText(`( ${c.kind} )`, 310, 96); g.textAlign = "left";
  const rows = [["등록번호", c.busino.replace(/(\d{3})(\d{2})(\d{5})/, "$1-$2-$3")], ["상호", c.company], ["대표자", "○○○"], ["개업연월일", c.opened],
    ["사업장 소재지", c.addr], ["업태", c.sector], ["종목", c.item]];
  rows.forEach(([k, v], i) => { FONT(g, 16, 1); g.fillText(`${k} :`, 60, 160 + i * 52); FONT(g, 16); g.fillText(v, 230, 160 + i * 52); });
  FONT(g, 14); g.fillText("발급사유 : 신규", 60, 560); g.fillText(`${c.opened.slice(0, 4)}년 ${Number(c.opened.slice(5, 7))}월 ${Number(c.opened.slice(8))}일`, 60, 620);
  FONT(g, 20, 1); g.textAlign = "center"; g.fillText("○ ○ 세 무 서 장 (인)", 310, 680); g.textAlign = "left";
  FONT(g, 12); g.fillStyle = "#888"; g.fillText("합성 데이터 · 시연용 (실제 사업자 아님, 000으로 시작하는 가짜 번호)", 40, 760);
  return cv.toDataURL("image/jpeg", 0.85);
}

/** 시연 사례: 정상 / 오류(계약서 항목 누락·휴게 부족·공고와 임금 불일치) / 공공데이터 걸림(임금체불 명단공개 기업) */
/** 기간제 공고면 예시 계약서에도 종료일(1년)을 넣는다 — 정상 사례가 '종료일 없음'으로 걸리지 않게 */
const endFor = (p) => { if (!/계약|기간/.test(String(p.emp_type || "")) || !p.hire_date) return "";
  const d = new Date(p.hire_date); d.setFullYear(d.getFullYear() + 1); d.setDate(d.getDate() - 1); return d.toISOString().slice(0, 10); };
const CASES = {
  ok: { label: "정상 사례", contract: (p, w) => ({ company: p.company, worker: w, start: p.hire_date, end: endFor(p), place: p.region, job: p.title, daily: 8, brk: 60, weekly: 40, holiday: true, payday: true, leave: true, wage: p.wage, allow: 0 }),
    biz: (p) => ({ busino: p.busino || "0008100012", company: p.company, kind: "법인사업자", opened: "2015-03-02", addr: `${p.region} 가상로 1`, sector: "서비스업", item: p.industry || "소프트웨어 개발 및 공급" }) },
  bad: { label: "오류 사례 (휴게 부족·지급일 누락·임금 불일치)", contract: (p, w) => ({ company: p.company, worker: w, start: p.hire_date, end: endFor(p), place: p.region, job: p.title, daily: 8, brk: 30, weekly: 40, holiday: true, payday: false, leave: true, wage: Math.max(p.wage - 100000, 2000000), allow: 0 }),
    biz: (p) => ({ busino: p.busino || "0008100012", company: p.company, kind: "법인사업자", opened: "2015-03-02", addr: `${p.region} 가상로 1`, sector: "서비스업", item: p.industry || "소프트웨어 개발 및 공급" }) },
  arrears: { label: "공공데이터 걸림 (임금체불 명단공개 기업)", contract: (p, w) => CASES.ok.contract(p, w),
    biz: (p) => ({ busino: "0008100112", company: "한결전자(가상)", kind: "법인사업자", opened: "2012-07-01", addr: "경상북도 구미시 가상로 11", sector: "제조업", item: "전자부품" }) },
};

function makeSample(key) {
  const p = S.ctx.posting, w = S.ctx.worker, cs = CASES[key];
  const c = cs.contract(p, w), b = cs.biz(p);
  S.files = { contract: { media_type: "image/jpeg", data: b64(drawContract(c)) }, bizreg: { media_type: "image/jpeg", data: b64(drawBizreg(b)) } };
  S.truth = { contract: { worker: c.worker, employment_type: c.end ? "기간제" : "정규직", start_date: c.start, end_date: c.end, base_wage: String(c.wage), wage_type: "월급",
    weekly_hours: String(c.weekly), daily_hours: String(c.daily), break_minutes: String(c.brk), has_holiday: c.holiday, has_leave: c.leave, has_place: !!c.place, has_job: !!c.job, has_payday: c.payday },
    bizreg: { busino: b.busino, company: b.company, ceo: "", industry: `${b.sector} ${b.item}`, opened: b.opened, doc_type: "사업자등록증" } };
  thumbs(`${cs.label} — 합성 서류 생성됨`);
}

const fileToB64 = (f) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok({ media_type: f.type, data: b64(r.result) }); r.onerror = no; r.readAsDataURL(f); });

function thumbs(note) {
  const box = $("#hdThumbs");
  box.innerHTML = ["contract", "bizreg"].map((k) => S.files[k]
    ? `<figure><img src="data:${S.files[k].media_type};base64,${S.files[k].data}" alt="${k === "contract" ? "근로계약서" : "사업자등록증"}"><figcaption>${k === "contract" ? "근로계약서" : "사업자등록증"}</figcaption></figure>`
    : `<figure class="empty-thumb"><figcaption>${k === "contract" ? "근로계약서" : "사업자등록증"} 없음</figcaption></figure>`).join("");
  $("#hdNote").textContent = note || "";
  $("#hdRun").disabled = !(S.files.contract || S.files.bizreg);
}

async function run() {
  const out = $("#hdResult"), btn = $("#hdRun");
  btn.disabled = true; out.innerHTML = '<span class="muted">AI가 서류 항목을 읽고, 규칙엔진이 점검·대조하는 중…</span>';
  try {
    const p = S.ctx.posting;
    const res = await window.ieumApi("/api/certificate", { method: "POST", timeoutMs: 60000, body: {
      kind: "hiredoc", consent: true, files: S.files, sample_truth: S.truth || undefined, worker: S.ctx.worker,
      posting: { wage: p.wage, emp_type: p.emp_type, region: p.region, busino: p.busino, weekly_hours: p.weekly_hours } } });
    S.res = res;
    const order = { "위반 의심": 0, "미충족": 0, "확인 필요": 1, "충족": 2, "적정": 2, "안내": 3 };
    const items = [...res.items].sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3));
    const flagged = items.filter((i) => (order[i.level] ?? 3) < 2);
    const con = res.contract || {}, biz = res.bizreg || {};
    out.innerHTML = `
      <div>${badge(res.level)} <b>${flagged.length ? `확인할 항목 ${flagged.length}건` : "이상 없음"}</b> <span class="muted">· 점검 ${items.length}항목</span></div>
      <div class="read-vals">판독(${res.source === "ai" ? `AI ${esc(res.model || "")}` : "합성 서류 기록값 — AI 미연결 환경"}):
        ${con.worker ? `계약서 ${esc(con.worker)} · ${esc(con.employment_type)} · ${esc(con.start_date)}~${esc(con.end_date || "")} · 기본급 ${won(con.base_wage)}원 · 주 ${esc(con.weekly_hours)}h · 휴게 ${esc(con.break_minutes)}분` : ""}
        ${biz.busino ? ` / 등록증 ${esc(biz.company)} · ${esc(biz.busino)} · ${esc(biz.industry)}` : ""}</div>
      ${items.map((i) => `<div class="check-item">${badge(i.level)}<div><b>${esc(i.item)}</b><br>${esc(i.detail)}<div class="basis">근거: ${esc(i.basis)}</div></div></div>`).join("")}
      <p class="meta">${esc(res.note)}</p>`;
    if (S.onDone) S.onDone({ level: res.level, source: res.source, items: res.items, contract: con, bizreg: biz,
      files: Object.keys(S.files).map((k) => (k === "contract" ? "근로계약서" : "사업자등록증")) });
  } catch (err) {
    out.innerHTML = `<div class="msg error">${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function open(ctx) {
  S.ctx = ctx; S.files = {}; S.truth = null; S.res = null;
  const panel = $("#hiredocPanel"); if (!panel) return;
  panel.hidden = false;
  $("#hdWho").textContent = `${ctx.posting.company} · ${ctx.worker} 채용 확정 — 근로계약서와 사업자등록증을 여기서 한 번만 첨부합니다. 담당자는 이 기록으로 확인하고 다시 요구하지 않습니다.`;
  $("#hdResult").innerHTML = '<div class="empty"><span>📎</span><p>서류를 올리거나 합성 예시를 만든 뒤<br>[서류 판독 · 점검]을 누르세요.</p></div>';
  thumbs("");
}

function init() {
  const panel = $("#hiredocPanel"); if (!panel) return;
  $$("[data-sample]", panel).forEach((b) => b.addEventListener("click", () => { S.truth = null; makeSample(b.dataset.sample); }));
  ["contract", "bizreg"].forEach((k) => {
    const inp = $(`#hd_${k}`); if (!inp) return;
    inp.addEventListener("change", async () => { const f = inp.files && inp.files[0]; if (!f) return; S.truth = null; S.files[k] = await fileToB64(f); thumbs("직접 올린 파일"); });
  });
  $("#hdRun").addEventListener("click", run);
}

window.IeumHireDocs = {
  open, init, setOnDone: (fn) => (S.onDone = fn),
  block(d) { // 담당자 확인 대시보드용
    if (!d) return "";
    const flagged = d.items.filter((i) => ["위반 의심", "미충족", "확인 필요"].includes(i.level));
    return `<h4>채용 확정 서류 (${esc(d.files.join("·"))})</h4>
      <p>${badge(d.level)} 확인할 항목 ${flagged.length}건 · 판독 ${d.source === "ai" ? "AI" : "합성 기록값"}</p>
      <div class="docs-box">${flagged.map((i) => `<div class="check-item">${badge(i.level)}<div><b>${esc(i.item)}</b><br><span class="muted">${esc(i.detail)}</span></div></div>`).join("") || '<p class="muted">이상 없음</p>'}</div>
      <p class="meta">채용 단계에서 기업이 한 번 첨부한 서류의 판독·점검 기록입니다. 신청 시 다시 받지 않습니다.</p>`;
  },
};
})();
