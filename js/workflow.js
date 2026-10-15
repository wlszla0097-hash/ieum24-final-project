/* 이음24 시연 흐름 (로그인 없이 저장) — window.IeumFlow
 *
 * 구직자: 이력·포트폴리오 저장 → 추천 공고 [지원] → 그 회사 지원자 목록에 추가 → [내 서류함]에서 계약서 서명·명세서 확인
 * 기업:   회사 선택(추후 기업 로그인) → [공고 올리기] 점검·게시 / [공고 확인] 구직자에게 보이는 모습·지원자·채용 확정
 *         채용 확정 → 저장된 구직자 정보 + 공고 조건으로 표준근로계약서 → 법인 인장(가상) 날인 · 근로자 서명 → 저장·규칙 점검
 *         → 계약 조건대로 급여명세서 발급(근로자에게 전송) → 이체확인증 대조
 * 담당자: 저장된 신청 건에서 계약서·명세서·점검 기록을 바로 확인 (서류를 다시 요구하지 않음)
 * app.js의 공용 도구($, esc, api, toast, state, badge, checkList …)를 그대로 쓴다.
 */
(function () {
"use strict";
const S = window.IeumStore, C = window.IeumContract;
const E = { companies: null, co: null, sel: null, view: null, ct: null, seal: "", pay: null };
const pad = (n) => String(n).padStart(2, "0");
const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const rid = () => Math.random().toString(36).slice(2, 8);
const ymAdd = (ym, k) => { const [y, m] = ym.split("-").map(Number); const t = y * 12 + m - 1 + k; return `${Math.floor(t / 12)}-${pad(t % 12 + 1)}`; };
const num = (v) => Number(String(v ?? "").replace(/[^\d.]/g, "")) || 0;
const monthlyHours = (w) => Math.round((w + (w / 40) * 8) * 4.345); // 주휴 포함 월 환산 (주 40h → 209h)

/* ================= 구직자 ================= */
async function saveSeeker() {
  if (!state.profile) return null;
  const prof = readSeekForm();
  return S.put("seekers", S.me(), { alias: prof.alias || "구직자", profile: prof, headline: state.headline, points: state.points, portfolio: state.portfolio });
}
async function extraPostings() {
  try { return (await S.list("postings")).slice(0, 30).map((p) => ({ id: p.id, form: p.form, skills: p.skills || [] })); } catch (e) { return []; }
}
/** 지원 저장. opts.portfolio: 이 공고에 맞춘 포트폴리오(맞춤 포트폴리오 기능이 넘겨 줌) — 있으면 기업 화면에 이것이 보인다 */
async function apply(job, opts = {}) {
  if (!job) throw new Error("공고를 찾지 못했습니다. 다시 추천을 받아 주세요.");
  const me = S.me(), sk = await saveSeeker();
  if (!sk) throw new Error("먼저 [AI로 이력 정리 · 공고 추천]으로 이력을 저장하세요.");
  const id = `${job.id}~${me}`, old = await S.get("applications", id);
  return S.put("applications", id, { ...(old || {}), posting_id: job.id, busino: job.busino || "", company: job.company, title: job.title,
    seeker_id: me, alias: sk.alias, applied: (old && old.applied) || today(), status: (old && old.status) || "지원",
    portfolio: opts.portfolio || (old && old.portfolio) || "" });
}
async function markApplied() {
  const mine = (await S.list("applications").catch(() => [])).filter((a) => a.seeker_id === S.me());
  $$("#seekResult .apply").forEach((b) => { if (mine.some((a) => a.posting_id === b.dataset.id)) { b.disabled = true; b.textContent = "지원 완료 ✓"; } });
  seekerInbox();
}

/** 내 서류함: 지원 현황 · 근로계약서(서명) · 급여명세서 */
async function seekerInbox() {
  const box = $("#myDocs"); if (!box) return;
  try {
    await S.init();
    const me = S.me();
    const [sk, apps, cts, pays] = await Promise.all([S.get("seekers", me), S.list("applications"), S.list("contracts"), S.list("payslips")]);
    const myApps = apps.filter((a) => a.seeker_id === me), myCts = cts.filter((c) => c.seeker_id === me), myPays = pays.filter((p) => p.seeker_id === me);
    const all = await S.list("seekers");
    if (!sk && !myApps.length && !all.length) { box.hidden = true; return; }
    box.hidden = false;
    const empty = !$("#seekForm [name=experience]").value.trim();
    const switcher = `<div class="btn-row"><span class="muted">저장된 구직자 ${all.length}명</span>
      ${all.length ? `<select id="mdSwitch" aria-label="저장된 구직자로 바꾸기"><option value="">저장된 구직자로 바꾸기…</option>${all.map((x) => `<option value="${esc(x.id)}" ${x.id === me ? "selected" : ""}>${esc(x.alias || "구직자")} · ${esc(String(x.updated || "").slice(0, 10))}</option>`).join("")}</select>` : ""}
      <button class="btn ghost sm" type="button" id="mdNew">+ 새 구직자로 작성 (시연)</button></div>`;
    if (!sk && !myApps.length) {
      box.innerHTML = `<h2 class="panel-title">📥 내 서류함 <small class="muted">${esc(S.label())}</small></h2>${switcher}<p class="muted">지금은 새 구직자입니다. 아래에 이력을 입력해 저장하세요.</p>`;
      bindSwitch(box); return;
    }
    box.innerHTML = `<h2 class="panel-title">📥 내 서류함 — ${esc((sk && sk.alias) || "구직자")} <small class="muted">${esc(S.label())}</small></h2>${switcher}
      ${sk && empty ? `<p class="muted">저장된 내 이력이 있어요. <button class="btn ghost sm" type="button" id="mdLoad">저장된 이력 불러오기</button></p>` : ""}
      <div class="md-grid">
        <div><h4>지원 현황 ${myApps.length}건</h4>${myApps.map((a) => `<div class="md-row"><b>${esc(a.company)}</b><span class="muted">${esc(a.title)} · 지원 ${esc(a.applied)}</span>${badge(a.status === "채용 확정" ? "채용 확정" : "지원")}</div>`).join("") || '<p class="muted">아직 지원한 공고가 없어요.</p>'}</div>
        <div><h4>근로계약서 ${myCts.length}건</h4>${myCts.map((c) => `<div class="md-row"><b>${esc(c.company)}</b><span class="muted">${esc(c.fields.start_date)} 입사 · ${esc(c.status)}</span>
            <span><button class="btn ghost sm" type="button" data-ct="${esc(c.id)}">보기</button>${c.worker_sign ? "" : ` <button class="btn primary sm" type="button" data-sign-ct="${esc(c.id)}">✍ 서명하기</button>`}</span></div>`).join("") || '<p class="muted">채용이 확정되면 여기서 계약서를 확인하고 서명합니다.</p>'}</div>
        <div><h4>급여명세서 ${myPays.length}건</h4>${myPays.sort((x, y) => x.ym.localeCompare(y.ym)).map((p) => `<div class="md-row"><b>${esc(p.ym)}</b><span class="muted">${esc(p.company)} · 실지급 ${won(p.net)}</span>
            <span>${p.check ? badge(p.check.level) : '<span class="badge 안내">이체 확인 전</span>'} <button class="btn ghost sm" type="button" data-ps="${esc(p.id)}">보기</button></span></div>`).join("") || '<p class="muted">입사 후 회사가 발급한 명세서가 여기로 옵니다.</p>'}</div>
      </div>`;
    bindSwitch(box);
    const load = $("#mdLoad", box);
    if (load) load.onclick = () => { fillForm($("#seekForm"), sk.profile, SEEK_FIELDS.filter((k) => k in sk.profile)); syncProgramBoxes();
      Object.assign(state, { points: sk.points || [], portfolio: sk.portfolio || "", headline: sk.headline || "" }); toast("저장된 이력을 불러왔어요. [AI로 이력 정리 · 공고 추천]을 누르면 추천이 다시 나와요."); load.closest("p").remove(); };
    $$("[data-ct]", box).forEach((b) => (b.onclick = () => viewContract(b.dataset.ct)));
    $$("[data-ps]", box).forEach((b) => (b.onclick = () => { const p = myPays.find((x) => x.id === b.dataset.ps); C.view(`${p.ym} 임금명세서`, C.payslipHtml(p)); }));
    $$("[data-sign-ct]", box).forEach((b) => (b.onclick = async () => {
      const c = myCts.find((x) => x.id === b.dataset.signCt);
      const dlg = C.view("근로계약서 확인 후 서명", C.docHtml(c.fields, { seal: c.seal, signable: true }));
      $("[data-sign]", dlg).onclick = async () => {
        const r = await C.openSign(c.fields.worker); if (!r) return;
        await signContract(c, r); dlg.close(); dlg.remove(); toast("서명했어요. 회사와 담당자 화면에도 바로 반영됩니다."); seekerInbox();
      };
    }));
  } catch (err) { box.hidden = false; box.innerHTML = `<p class="msg error">${esc(err.message)}</p>`; }
}
/** 저장된 구직자 바꾸기 / 새 구직자로 시작: 여러 구직자 데이터가 쌓이는 것을 한 브라우저에서 시연 */
function bindSwitch(box) {
  const clear = () => {
    $("#seekForm").reset(); syncProgramBoxes();
    Object.assign(state, { profile: null, points: [], portfolio: "", headline: "", jobs: [], cert: null });
    $("#seekResult").innerHTML = '<div class="empty"><span>🧭</span><p>왼쪽에 내 경험을 적고<br>[AI로 이력 정리 · 공고 추천]을 누르세요.</p></div>';
  };
  const nw = $("#mdNew", box);
  if (nw) nw.onclick = () => { S.newMe(); clear(); seekerInbox(); toast("새 구직자로 시작해요. 앞서 저장한 구직자 데이터는 그대로 남아 있어요."); };
  const sw = $("#mdSwitch", box);
  if (sw) sw.onchange = () => { if (!sw.value || sw.value === S.me()) return; S.newMe(sw.value); clear(); seekerInbox(); };
}
async function signContract(c, r) {
  Object.assign(c, { worker_sign: r.data, sign_kind: r.kind, signed_at: new Date().toISOString(), status: "체결 완료" });
  await S.put("contracts", c.id, c);
  if (c.case_id) { const cs = await S.get("cases", c.case_id); if (cs) await S.put("cases", cs.id, { ...cs, contract_status: c.status, sign_kind: r.kind }); }
}

/* ================= 기업: 회사 선택 · 신규 등록 ================= */
async function enterEmployer() {
  await S.init();
  $("#storeMode").textContent = `저장 방식: ${S.label()}`;
  try {
    if (!E.companies) { const r = await api("/api/employer", { timeoutMs: 15000 }); E.companies = r.companies; state.postExamples = r.examples; }
  } catch (err) { $("#coGrid").innerHTML = errorHtml(err); return; }
  E.userCos = await S.list("companies").catch(() => []);
  if (E.co) return showWork(false);
  renderCompanies();
}
/** 직접 등록한 기업(저장소) + 공공데이터(합성) 연결 기업 + 기본 예시 기업 */
function allCos() {
  const user = (E.userCos || []).map((c) => ({ ...c, key: c.id, user: true, registered: true, postings: [] }));
  return [...user.sort((a, b) => String(b.created).localeCompare(String(a.created))), ...(E.companies || [])];
}
async function renderCompanies() {
  $("#empCompanies").hidden = false; $("#empWork").hidden = true;
  E.userCos = await S.list("companies").catch(() => []);
  const [apps, posts] = await Promise.all([S.list("applications").catch(() => []), S.list("postings").catch(() => [])]);
  const ids = (co) => new Set([...co.postings.map((p) => p.id), ...posts.filter((p) => p.co_key === co.key).map((p) => p.id)]);
  const card = (co) => { const set = ids(co), n = apps.filter((a) => set.has(a.posting_id)).length;
    return `<button class="co-card ${co.user ? "user" : ""}" type="button" data-key="${esc(co.key)}"><b>${esc(co.company)}</b>
      <span class="muted">${esc(co.industry || "업종 미등록")} · ${esc(co.region)}</span>
      <span class="muted">${co.busino ? `사업자 ${esc(C.fmtBiz(co.busino))}` : "사업자번호 없음"} · 공고 ${set.size}건${n ? ` · <b class="hl">지원자 ${n}명</b>` : ""}</span>
      ${co.user ? `<small class="co-note ok">직접 등록 · ${esc(co.created || "")}</small>` : co.note ? `<small class="co-note">시연 사례: ${esc(co.note)}</small>` : ""}</button>`; };
  const cos = allCos();
  $("#coGridUser").innerHTML = cos.filter((c) => c.user).map(card).join("");
  $("#coUserHead").hidden = !cos.some((c) => c.user);
  $("#coGrid").innerHTML = cos.filter((c) => c.registered && !c.user).map(card).join("") || '<p class="muted">등록된 합성 기업이 없습니다.</p>';
  $("#coGridEtc").innerHTML = cos.filter((c) => !c.registered).map(card).join("");
  $$(".co-card").forEach((b) => (b.onclick = () => selectCompany(b.dataset.key)));
  stats();
}
/** 저장 현황: 화면에서 입력한 데이터가 쌓이고 있는지 한눈에 */
async function stats() {
  const el = $("#storeStats"); if (!el) return;
  try {
    const d = await S.dump();
    el.innerHTML = `저장 현황 — 구직자 <b>${d.seekers.length}</b>명 · 직접 등록 기업 <b>${d.companies.length}</b>곳 · 게시 공고 <b>${d.postings.length}</b>건 · 지원 <b>${d.applications.length}</b>건 · 근로계약서 <b>${d.contracts.length}</b>건 · 급여명세서 <b>${d.payslips.length}</b>건 · 신청 건 <b>${d.cases.length}</b>건`;
  } catch (err) { el.textContent = err.message; }
}
async function selectCompany(key) {
  E.co = allCos().find((c) => c.key === key); E.sel = null; E.ct = null;
  E.seal = C.safeImg(E.co.seal) || await C.sealFor(E.co.busino, E.co.company);
  showWork(true);
}

/* 신규 기업 등록 (실제 서비스의 기업 회원가입 자리) */
$("#coNewBtn").onclick = () => { const f = $("#coNew"); f.hidden = !f.hidden; if (!f.hidden) $("#cn_name").focus(); };
$("#cnCancel").onclick = () => ($("#coNew").hidden = true);
$("#cn_ins").addEventListener("input", (e) => (e.target.value = e.target.value.replace(/[^\d]/g, "")));
$("#coNew").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#cnMsg"), v = (id) => $("#" + id).value.trim();
  const busino = v("cn_busino").replace(/\D/g, "");
  const miss = [["cn_name", "회사명"], ["cn_busino", "사업자등록번호"], ["cn_ind", "업종"], ["cn_sido", "소재지 시·도"], ["cn_ins", "피보험자 수"]].filter(([id]) => !v(id));
  if (miss.length) return showMsg(msg, `필수값을 입력하세요: ${miss.map(([, l]) => l).join(", ")}`);
  if (busino.length !== 10 || !busino.startsWith("000")) return showMsg(msg, "시연용 사업자등록번호는 000으로 시작하는 숫자 10자리만 쓸 수 있어요. (실제 번호 입력 금지)");
  if (allCos().some((c) => c.busino === busino)) return showMsg(msg, "이미 등록된 사업자등록번호예요. 목록에서 그 회사를 고르세요.");
  showMsg(msg, "");
  const name = v("cn_name").replace(/\(가상\)/g, "").trim();
  const btn = $("#cnSave"); btn.disabled = true; btn.textContent = "등록 중…";
  try {
    const seal = C.drawSeal("대표이사", { ring: `주식회사 ${name} · 시연용 가상 인장 · `, size: 160 });
    const co = await S.put("companies", `C-${busino}`, { busino, company: `${name}(가상)`, ceo: v("cn_ceo"), industry: v("cn_ind"),
      region: [v("cn_sido"), v("cn_sgg")].filter(Boolean).join(" "), insured: Number(v("cn_ins")), priority: { 예: true, 아니오: false }[v("cn_pri")] ?? null,
      seal, created: today() });
    $("#coNew").reset(); $("#coNew").hidden = true;
    toast(`${esc(co.company)}을(를) 등록했어요. 법인 인장(가상)도 만들어 저장했어요.`);
    E.userCos = await S.list("companies");
    selectCompany(co.id);
  } catch (err) { showMsg(msg, err.message); }
  finally { btn.disabled = false; btn.textContent = "등록하고 시작하기"; }
});
/* 저장 데이터 내보내기: 쌓인 시연 데이터를 JSON 파일로 받아 저장소(data/)에 올릴 수 있게 */
$("#storeExport").onclick = async () => {
  try {
    const d = await S.dump();
    const blob = new Blob([JSON.stringify({ exported: new Date().toISOString(), note: "이음24 시연 데이터(합성)", ...d }, null, 1)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `ieum24-demo-data-${today()}.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (err) { toast(esc(err.message)); }
};

function showWork(fresh) {
  $("#empCompanies").hidden = true; $("#empWork").hidden = false;
  const co = E.co;
  $("#coBar").innerHTML = `<div class="co-bar-in"><img class="co-seal" src="${esc(C.safeImg(E.seal))}" alt="법인 인장(가상)">
    <div><h2>${esc(co.company)} ${co.user ? '<span class="badge 안내">직접 등록</span>' : ""}</h2><p class="muted">${esc(co.industry || "업종 미등록")} · ${esc(co.region)} · 사업자등록번호 ${esc(C.fmtBiz(co.busino))} · 피보험자 ${esc(co.insured ?? "-")}명 · 우선지원대상 ${co.priority === true ? "예" : co.priority === false ? "아니오" : "모름"}${co.ceo ? ` · 대표 ${esc(co.ceo)}` : ""}</p>
      <small class="muted">법인 인장 등록됨 (시연용 가상 인장) — 근로계약서 사업주 날인에 자동으로 쓰입니다.${co.user ? " 직접 등록한 기업은 공공데이터(합성) 조회 결과가 없어 업종은 입력값으로, 임금체불은 '연동 후 확인'으로 점검합니다." : ""}</small></div>
    <button class="btn ghost sm" type="button" id="coChange">다른 회사 선택</button></div>`;
  $("#coChange").onclick = () => { E.co = null; ["contractPanel", "payPanel", "hiredocPanel", "empArea"].forEach((id) => ($("#" + id).hidden = true)); renderCompanies(); window.scrollTo({ top: 0 }); };
  if (fresh) {
    prepPostForm();
    ["contractPanel", "payPanel", "hiredocPanel", "empArea"].forEach((id) => ($("#" + id).hidden = true));
    tab(co.postings.length ? "list" : "post");
  }
}
function tab(name) {
  $$("[data-etab]").forEach((b) => b.classList.toggle("active", b.dataset.etab === name));
  $$("[data-epane]").forEach((p) => (p.hidden = p.dataset.epane !== name));
  if (name === "list") renderList();
}
$$("[data-etab]").forEach((b) => (b.onclick = () => tab(b.dataset.etab)));

/* ================= 공고 올리기 ================= */
function prepPostForm() {
  const co = E.co, [sido, ...rest] = String(co.region || "").split(" ");
  $("#postForm").reset();
  fillPost({ company: co.company, busino: co.busino ? C.fmtBiz(co.busino) : "", industry: co.user ? co.industry : "", sido, sigungu: rest.join(" "), insured: co.insured ?? "",
    priority: co.priority === true ? "예" : co.priority === false ? "아니오" : "모름", weekly_hours: 40 });
  $("#postExample").innerHTML = '<option value="">불러오기…</option>' + co.postings.map((p) => `<option value="${esc(p.id)}">${esc(p.title)}</option>`).join("");
  renderPreview();
}
$("#postExample").addEventListener("change", (e) => {
  const p = E.co && E.co.postings.find((x) => x.id === e.target.value);
  if (p) { fillPost({ ...p.form, close: "" }); renderPreview(); }
});
$("#postForm").addEventListener("input", () => renderPreview());
$("#postForm").addEventListener("change", () => renderPreview());

function jobCard(p, extra = {}) {
  const tags = (extra.skills || []).map((s) => `<span>${esc(s)}</span>`).join("");
  return `<article class="job preview">
    <div class="job-head"><h3>${esc(p.title || "공고 제목")}</h3></div>
    <div class="agency">${esc(p.company)} · ${esc([p.sido, p.sigungu].filter(Boolean).join(" ") || p.region || "근무지")} · ${esc(p.emp_type || "고용형태")} · 월 ${won(num(p.wage))} · 마감 ${esc(p.close || "-")}</div>
    ${tags ? `<div class="tags">${tags}</div>` : ""}
    <p>${esc(extra.summary || String(p.description || "").slice(0, 140) || "공고 본문 요약이 여기에 보입니다.")}</p>
    <div class="job-actions"><button class="btn primary" type="button" disabled>이 공고에 지원</button></div></article>`;
}
function renderPreview() {
  if (!E.co) return;
  const f = readPostForm();
  $("#postPreview").innerHTML = jobCard({ ...f, wage: f.wage });
}
function publishBox(data) {
  const { check, analysis } = data;
  // 요구 역량: AI가 본문에서 찾은 단어. AI 키가 없으면 기존 공고들의 기술 단어 중 본문에 실제로 있는 것만 (추천 매칭용)
  const body = `${state.postInput.title} ${state.postInput.job} ${state.postInput.description}`.toLowerCase();
  const vocab = [...new Set((E.companies || []).flatMap((c) => c.postings.flatMap((p) => p.skills || [])))];
  const skills = (analysis && analysis.requirements && analysis.requirements.length) ? analysis.requirements
    : vocab.filter((w) => w && body.includes(String(w).toLowerCase())).slice(0, 8);
  $("#postPublish").innerHTML = `<h2 class="panel-title">게시 전 확인 — 구직자에게 이렇게 보여요</h2>
    ${jobCard(state.postInput, { skills, summary: analysis && analysis.summary })}
    ${check.verdict === "연계 어려움" ? '<p class="msg info">지원제도 연계는 어렵다고 점검됐어요. 공고 게시는 할 수 있지만, 왼쪽 점검 항목을 먼저 확인하세요.</p>' : ""}
    <button class="btn primary block" type="button" id="pubBtn">이 공고 게시하기</button>
    <p class="meta">게시하면 구직자 추천 후보에 들어가고, [공고 확인]에서 지원자를 볼 수 있어요. (요구 역량은 AI가 공고 본문에서 찾은 단어만)</p>`;
  $("#pubBtn").onclick = async () => {
    const b = $("#pubBtn"); b.disabled = true; b.textContent = "게시 중…";
    try {
      const id = `U-${rid()}`, f = state.postInput;
      await S.put("postings", id, { co_key: E.co.key, busino: E.co.busino, company: E.co.company, title: f.title, close: f.close || "", form: f,
        skills, summary: (analysis && analysis.summary) || "", verdict: check.verdict, created: today() });
      toast("공고를 게시했어요. 구직자 추천 후보에 들어갑니다.");
      E.sel = id; $("#empArea").hidden = true; tab("list");
    } catch (err) { b.disabled = false; b.textContent = "이 공고 게시하기"; toast(esc(err.message)); }
  };
}

/* ================= 공고 확인 · 지원자 ================= */
async function companyPosts() {
  const stored = (await S.list("postings").catch(() => [])).filter((p) => p.co_key === E.co.key)
    .map((p) => ({ id: p.id, title: p.title, form: p.form, skills: p.skills || [], summary: p.summary, close: p.close, src: "이음24에서 게시", created: p.created }));
  const files = E.co.postings.map((p) => ({ id: p.id, title: p.title, form: { ...p.form, close: p.close }, skills: p.skills, close: p.close,
    src: p.source === "synthetic" ? "기본 예시 공고" : "고용24 등록 공고(합성)" }));
  return [...stored.sort((a, b) => String(b.created).localeCompare(String(a.created))), ...files];
}
async function renderList() {
  const box = $("#myPosts");
  box.innerHTML = loadingHtml("공고를 불러오는 중");
  const [posts, apps] = await Promise.all([companyPosts(), S.list("applications").catch(() => [])]);
  E.posts = posts;
  box.innerHTML = `<h3>우리 회사 공고 ${posts.length}건</h3>` + posts.map((p) => {
    const n = apps.filter((a) => a.posting_id === p.id).length;
    return `<button class="post-item ${E.sel === p.id ? "active" : ""}" type="button" data-pid="${esc(p.id)}"><b>${esc(p.title)}</b>
      <span class="muted">${esc(p.src)} · 마감 ${esc(p.close || "-")}</span><span class="muted">지원자 ${n + 3}명 (구직자 화면 지원 ${n} · 가상 3)</span></button>`;
  }).join("") + '<button class="btn ghost block" type="button" id="goPost">+ 새 공고 올리기</button>';
  $$(".post-item", box).forEach((b) => (b.onclick = () => { E.sel = b.dataset.pid; $$(".post-item", box).forEach((x) => x.classList.toggle("active", x === b)); loadDetail(); }));
  $("#goPost").onclick = () => tab("post");
  if (!E.sel && posts.length) E.sel = posts[0].id;
  if (E.sel) { $$(".post-item", box).forEach((x) => x.classList.toggle("active", x.dataset.pid === E.sel)); loadDetail(); }
}
async function loadDetail() {
  const p = E.posts.find((x) => x.id === E.sel); if (!p) return;
  const out = $("#postDetail");
  out.innerHTML = loadingHtml("공고 점검 결과와 지원자를 불러오는 중 (AI 호출 없음)");
  try {
    const [apps, seekers, cts] = await Promise.all([S.list("applications"), S.list("seekers"), S.list("contracts")]);
    const skMap = Object.fromEntries(seekers.map((x) => [x.id, x]));
    const extra = apps.filter((a) => a.posting_id === p.id && skMap[a.seeker_id]).map((a) => { const sk = skMap[a.seeker_id];
      return { seeker_id: a.seeker_id, alias: sk.alias || a.alias, applied: a.applied, headline: sk.headline,
        profile: { ...sk.profile, points: sk.points || [], portfolio: a.portfolio || sk.portfolio || "" } }; });  // 공고별 맞춤 포트폴리오 우선
    const data = await api("/api/employer", { method: "POST", timeoutMs: 20000,
      body: { posting: p.form, posting_id: p.id, analyze: false, skills: p.skills || [], applicants_extra: extra } });
    E.view = { p, data, extra };
    const flags = data.check.items.filter((i) => i.level !== "충족" && i.level !== "안내");
    out.innerHTML = `
      <h3>👀 구직자 추천 목록에 보이는 모습</h3>${jobCard(p.form, { skills: p.skills, summary: p.summary })}
      <h3>지원제도 연계 점검 <span class="badge ${VERDICT_TONE[data.check.verdict]}">${esc(data.check.verdict)}</span></h3>
      ${flags.length ? checkList(flags) : '<p class="muted">미충족·확인 필요 항목 없음</p>'}
      <details><summary>점검 항목 전체 보기</summary>${checkList(data.check.items)}</details>
      <h3>지원자 현황 ${data.applicants.length}명 <small class="muted">지원일 순</small></h3>
      <p class="note">${esc(data.note)}</p>
      ${data.applicants.map((a) => {
        const ct = cts.find((c) => c.posting_id === p.id && c.applicant_id === a.id);
        return `<div class="applicant ${a.stored ? "me" : ""}">
          <div><b>${esc(a.alias)}</b> ${a.badge ? EUM : ""} <span class="badge 안내">${a.stored ? "구직자 화면에서 지원" : "시연용 가상 지원자"}</span><br><span class="muted">${esc(a.headline)}</span>
            ${a.points.length ? `<ul class="points">${a.points.slice(0, 4).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
            ${a.portfolio ? `<details class="pf"><summary>포트폴리오 전체 보기</summary><pre>${esc(a.portfolio)}</pre></details>` : ""}
            <small class="muted">지원일 ${esc(a.applied)}</small></div>
          <div class="ap-actions">${ct ? `<span class="badge ${ct.worker_sign ? "적정" : "확인필요"}">${esc(ct.status)}</span>
              <button class="btn ghost sm" type="button" data-open-ct="${esc(a.id)}">계약서 열기</button><button class="btn ghost sm" type="button" data-pay-ct="${esc(ct.id)}">급여명세서</button>`
            : `<button class="btn primary hire" type="button" data-hire="${esc(a.id)}">채용 확정</button>`}</div></div>`; }).join("")}
      <p class="meta">정렬·필터 기능은 일부러 두지 않았습니다. ‘지원제도 활용 가능’ 사유와 나이는 채용 전 기업에 보이지 않습니다.</p>`;
    $$("[data-hire],[data-open-ct]", out).forEach((b) => (b.onclick = () => hire(data.applicants.find((a) => a.id === (b.dataset.hire || b.dataset.openCt)))));
    $$("[data-pay-ct]", out).forEach((b) => (b.onclick = async () => { E.ct = await S.get("contracts", b.dataset.payCt); openPay(); }));
  } catch (err) { out.innerHTML = errorHtml(err); }
}

/* ================= 채용 확정 → 근로계약서 ================= */
async function hire(a) {
  const { p, data, extra } = E.view;
  const id = `CT~${p.id}~${a.id.split("-").pop()}`;
  const old = await S.get("contracts", id);
  if (old) E.ct = old;
  else {
    const sk = a.stored ? extra.find((x) => x.seeker_id === a.seeker_id) : null;
    E.ct = { id, posting_id: p.id, posting_title: p.title, applicant_id: a.id, seeker_id: a.seeker_id || "", worker: a.hire_name,
      company: E.co.company, busino: E.co.busino, posting_form: p.form, applicant: sk ? { alias: sk.alias, profile: sk.profile } : null,
      fields: C.defaults({ ...data.posting, busino: E.co.busino, job: p.form.job, region: data.posting.region, ceo: E.co.ceo || "" }, { id: a.seeker_id || `SYN-${a.id}`, name: a.hire_name }, today()),
      status: "작성 중" };
  }
  renderContract();
  $("#contractPanel").scrollIntoView({ behavior: "smooth", block: "start" });
}
const CT_FIELDS = [
  ["start_date", "근로개시일", "date"], ["kind", "계약 기간", "select", [["무기", "기간의 정함 없음"], ["기간", "기간의 정함 있음"]]], ["end_date", "계약 종료일 (기간 있음)", "date"],
  ["place", "근무 장소", "text"], ["job", "업무의 내용", "text"],
  ["t_start", "시업", "time"], ["t_end", "종업", "time"], ["b_start", "휴게 시작", "time"], ["b_end", "휴게 끝", "time"],
  ["days", "주 근무일", "number"], ["holiday", "주휴일", "select", ["일", "토", "월"].map((d) => [d, `매주 ${d}요일`])],
  ["base_wage", "월급(원)", "number"], ["bonus", "상여금(원, 없으면 0)", "number"], ["allow_name", "기타급여 이름", "text"], ["allow_amount", "기타급여(원)", "number"],
  ["payday", "임금지급일(매월 ○일)", "number"], ["pay_method", "지급방법", "select", [["통장", "근로자 명의 예금통장 입금"], ["직접", "근로자에게 직접지급"]]], ["sign_date", "작성일", "date"],
];
function renderContract() {
  const ct = E.ct, f = ct.fields, panel = $("#contractPanel");
  panel.hidden = false;
  const input = ([k, label, type, opts]) => `<div class="field"><label>${esc(label)}</label>${type === "select"
    ? `<select data-f="${k}">${opts.map(([v, l]) => `<option value="${esc(v)}" ${String(f[k]) === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`
    : `<input type="${type}" data-f="${k}" value="${esc(f[k])}" ${type === "number" ? 'min="0"' : ""}>`}</div>`;
  panel.innerHTML = `<h2 class="panel-title">⑥ 채용 확정 — 근로계약서 <small class="muted">${esc(ct.company)} → ${esc(f.worker)}</small></h2>
    <p class="muted">저장된 구직자 정보(이름)와 공고 조건(임금·근무지·직무·근로시간)으로 <b>고용노동부 표준근로계약서</b>를 채웠습니다. 고칠 곳을 고치고, 근로자 서명을 받아 저장하세요.
      사업주 날인은 등록된 법인 인장(가상)이 자동으로 들어갑니다.</p>
    <div class="grid-contract">
      <form class="ct-form" id="ctForm" novalidate>
        <div class="btn-row"><button class="btn ghost sm" type="button" id="ct6m">시연: 6개월 전 입사로 가정</button><span class="muted">고용유지 6개월·월별 급여까지 한 번에 보려면</span></div>
        <div class="ct-grid">${CT_FIELDS.map(input).join("")}</div>
        <fieldset class="field"><legend>사회보험 적용</legend><div class="chips">
          ${[["emp", "고용보험"], ["acc", "산재보험"], ["pen", "국민연금"], ["hea", "건강보험"]].map(([k, l]) => `<label><input type="checkbox" data-ins="${k}" ${f.ins[k] ? "checked" : ""}> ${l}</label>`).join("")}</div></fieldset>
      </form>
      <div><div id="ctDoc"></div>
        <p class="meta">근로자 서명: 시연에서는 이 화면의 서명란 버튼으로 바로 받을 수 있고, 저장 후 근로자가 구직자 화면 [내 서류함]에서 서명할 수도 있습니다.</p></div>
    </div>
    <p class="msg" id="ctMsg" role="alert" hidden></p>
    <button class="btn primary block" type="button" id="ctSave">${ct.case_id ? "계약서 다시 저장 · 근로계약 점검" : "계약서 저장 · 근로계약 점검 · 담당자 신청 건 만들기"}</button>
    <div id="ctResult"></div>`;
  drawDoc();
  $$("[data-f]", panel).forEach((el) => el.addEventListener("input", () => {
    const k = el.dataset.f; f[k] = el.type === "number" ? num(el.value) : el.value;
    if (k === "kind" && f.kind === "기간" && !f.end_date) { const d = new Date(f.start_date); d.setFullYear(d.getFullYear() + 1); d.setDate(d.getDate() - 1); f.end_date = d.toISOString().slice(0, 10); $('[data-f="end_date"]', panel).value = f.end_date; }
    changed();
  }));
  $$("[data-ins]", panel).forEach((el) => el.addEventListener("change", () => { f.ins[el.dataset.ins] = el.checked; changed(); }));
  $("#ct6m").onclick = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 6);
    f.start_date = f.sign_date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`;
    ["start_date", "sign_date"].forEach((k) => ($(`[data-f="${k}"]`, panel).value = f[k])); changed(); };
  $("#ctSave").onclick = saveContract;
  if (ct.case_id) showCtResult();
}
function changed() {
  if (E.ct.worker_sign) { Object.assign(E.ct, { worker_sign: "", sign_kind: "", signed_at: "" }); toast("계약 내용이 바뀌어 근로자 서명을 다시 받아야 해요."); }
  drawDoc();
}
function drawDoc() {
  const ct = E.ct;
  $("#ctDoc").innerHTML = C.docHtml(ct.fields, { seal: E.seal, sign: ct.worker_sign, signable: true });
  const b = $("#ctDoc [data-sign]");
  if (b) b.onclick = async () => { const r = await C.openSign(ct.fields.worker); if (!r) return;
    Object.assign(ct, { worker_sign: r.data, sign_kind: r.kind, signed_at: new Date().toISOString() }); drawDoc(); };
}
async function saveContract() {
  const ct = E.ct, f = ct.fields, msg = $("#ctMsg"), h = C.hours(f);
  const bad = [];
  if (!f.start_date) bad.push("근로개시일");
  if (!(num(f.base_wage) > 0)) bad.push("월급");
  if (!(f.days >= 1 && f.days <= 7)) bad.push("주 근무일(1~7)");
  if (!(h.daily > 0)) bad.push("시업·종업·휴게 시간");
  if (f.kind === "기간" && !(f.end_date && f.end_date >= f.start_date)) bad.push("계약 종료일");
  if (!(f.payday >= 1 && f.payday <= 31)) bad.push("임금지급일");
  if (bad.length) return showMsg(msg, `확인할 값: ${bad.join(", ")}`);
  showMsg(msg, "");
  const btn = $("#ctSave"); btn.disabled = true; btn.textContent = "저장·점검 중…";
  try {
    const r = await api("/api/cases", { method: "POST", timeoutMs: 20000, body: { posting: ct.posting_form, posting_id: ct.posting_id, applicant_id: ct.applicant_id,
      hire_date: f.start_date, contract: C.toCheck(f), applicant: ct.applicant || undefined } });
    const cs = r.case;
    if (ct.case_id && ct.case_id !== cs.case_id) await S.del("cases", ct.case_id).catch(() => {});
    const prev = (await S.get("cases", cs.case_id)) || {};
    Object.assign(ct, { case_id: cs.case_id, check: cs.contract, seal: E.seal, status: ct.worker_sign ? "체결 완료" : "근로자 서명 대기", saved_at: new Date().toISOString() });
    await S.put("contracts", ct.id, ct);
    await S.put("cases", cs.case_id, { ...cs, worker: f.worker, contract_id: ct.id, posting_id: ct.posting_id, seeker_id: ct.seeker_id,
      contract_status: ct.status, sign_kind: ct.sign_kind || "", base_checklist: cs.checklist, status_base: cs.status,
      docs: prev.docs, hiredocs: prev.hiredocs, decision: prev.decision });
    if (prev.docs) await syncCase(false);
    if (ct.seeker_id) {
      const aid = `${ct.posting_id}~${ct.seeker_id}`, app = await S.get("applications", aid);
      if (app) await S.put("applications", aid, { ...app, status: "채용 확정", contract_id: ct.id });
    }
    toast(`계약서를 저장했어요 (${esc(ct.status)}). <a href="#officer">담당자 확인 대시보드</a>에 신청 건이 생겼어요.`);
    showCtResult();
    loadDetail();
  } catch (err) { showMsg(msg, err.message); }
  finally { btn.disabled = false; btn.textContent = "계약서 다시 저장 · 근로계약 점검"; }
}
async function showCtResult() {
  const ct = E.ct, res = ct.check || [];
  const order = { "위반 의심": 0, "확인 필요": 1, "적정": 2 };
  const v = res.filter((x) => x.level === "위반 의심").length, c = res.filter((x) => x.level === "확인 필요").length;
  $("#ctResult").innerHTML = `<h3>근로계약 점검 (규칙엔진) — 위반 의심 ${v}건 · 확인 필요 ${c}건 <small class="muted">${esc(ct.status)}</small></h3>
    ${[...res].sort((a, b) => order[a.level] - order[b.level]).map((r) => `<div class="check-item">${badge(r.level)}<div><b>${esc(r.item)}</b><br>${esc(r.detail)}<div class="basis">근거: ${esc(r.basis)}</div></div></div>`).join("")}
    <p class="meta">※ 입력값 기준 규칙 점검이며 법적 판단이 아닙니다. 최종 판단은 이용자와 노무 전문가·관할 기관의 몫입니다.</p>
    <div class="btn-row"><button class="btn primary" type="button" id="goPay">💰 급여명세서 발급으로</button>
      <button class="btn ghost" type="button" id="goHd">(선택) 사업자등록증·다른 양식 서류 판독</button>
      <a class="btn ghost" href="#officer">담당자 확인 대시보드 보기</a></div>`;
  $("#goPay").onclick = openPay;
  $("#goHd").onclick = () => {
    const f = ct.fields, pf = ct.posting_form || {};
    window.IeumHireDocs.open({ worker: f.worker, posting: { company: ct.company, title: ct.posting_title, region: [pf.sido, pf.sigungu].filter(Boolean).join(" "),
      wage: num(pf.wage), emp_type: pf.emp_type, weekly_hours: num(pf.weekly_hours) || 40, busino: ct.busino, industry: "", hire_date: f.start_date } });
    window.IeumHireDocs.setOnDone(async (hd) => {
      const cs = await S.get("cases", ct.case_id); if (!cs) return;
      await S.put("cases", cs.id, { ...cs, hiredocs: hd });
      toast(`서류 판독 결과를 신청 건에 저장했어요. <a href="#officer">담당자 확인 대시보드</a>`);
    });
    $("#hiredocPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  };
}

/* ================= 급여명세서 발급 · 이체 확인 ================= */
/** 급여 달: 입사월부터 6개월. 기간제는 계약 종료월까지만 (종료 뒤 명세서 발급 방지) */
function payMonths() {
  const f = E.ct.fields, s = String(f.start_date).slice(0, 7);
  const end = f.kind === "기간" && f.end_date ? String(f.end_date).slice(0, 7) : "";
  return Array.from({ length: 6 }, (_, i) => ymAdd(s, i)).filter((m) => !end || m <= end);
}
const psId = (ym) => `PS~${E.ct.id.slice(3)}~${ym}`;
/* 이체확인증 예시: 가상 은행 양식으로 그려 '첨부'한 것처럼 쓰고, AI(또는 키가 없으면 그릴 때 기록한 값)로 판독해 대조 */
const TR_CASES = {
  ok: "정상 — 금액·보내는 분·받는 분 모두 일치",
  short: "금액 다름 — 3만 원 적게 이체",
  sender: "이체자 다름 — 대표자 개인 명의 계좌에서 이체",
  recipient: "받는 분 다름 — 근로자가 아닌 다른 사람 계좌",
};
const BATCH = ["ok", "ok", "ok", "short", "ok", "sender"];
function makeExample(p, kind, i = 0) {
  const ceo = String(E.ct.fields.ceo || "").replace(/대표이사|\(가상\)/g, "").trim() || "김대표";
  const t = { bank: C.BANKS[i % C.BANKS.length], date: p.pay_date, sender: kind === "sender" ? ceo : p.company,
    recipient: kind === "recipient" ? "박서연" : p.worker, amount: p.net - (kind === "short" ? 30000 : 0), memo: `${Number(p.ym.slice(5))}월 급여` };
  const url = C.drawBankTransfer(t);
  return { src: url, label: `예시: ${TR_CASES[kind]}`, kind, file: { media_type: "image/jpeg", data: url.split(",")[1] },
    truth: { transfer: { recipient: t.recipient, date: t.date, amount: String(t.amount), sender: t.sender } } };
}
/** 기준값(명세서·계약) ↔ 이체확인증 판독값 비교표 */
function compareHtml(p) {
  const r = (p.transfer && p.transfer.read) || {}, items = (p.check && p.check.items) || [];
  const lv = (name) => { const it = items.find((x) => x.item === name); return it ? badge(it.level) : '<span class="badge 안내">참고</span>'; };
  const rows = [["받는 분(예금주)", `근로자 ${p.worker}`, r.recipient, "성명"], ["보내는 분(이체자)", `회사 ${p.company}`, r.sender, "이체자(보내는 분)"],
    ["이체금액", `명세서 실지급 ${won(p.net)}`, r.amount ? won(num(r.amount)) : "", "실지급액·이체액"], ["이체일", `지급일 ${p.pay_date}`, r.date, "이체일"]];
  const rest = items.filter((x) => !["성명", "이체자(보내는 분)", "실지급액·이체액", "이체일"].includes(x.item));
  return `<table class="cmp"><thead><tr><th>항목</th><th>기준</th><th>이체확인증 판독</th><th></th></tr></thead><tbody>
    ${rows.map(([k, base, read, item]) => `<tr><td>${esc(k)}</td><td>${esc(base)}</td><td><b>${esc(read || "읽지 못함")}</b></td><td>${lv(item)}</td></tr>`).join("")}</tbody></table>
    ${items.filter((x) => x.level !== "일치").map((x) => `<div class="muted">· ${esc(x.item)}: ${esc(x.detail)}</div>`).join("")}
    ${rest.length ? `<details><summary>그 밖의 규칙 점검 ${rest.length}항목</summary>${checkList(rest)}</details>` : ""}
    <small class="muted">${esc(p.transfer.kind || "")} · 판독: ${esc(p.transfer.read_source === "ai" ? `AI ${p.transfer.model || ""}` : "예시 이체확인증을 그릴 때 기록한 값 — AI 키 미설정 환경")}</small>`;
}
async function openPay() {
  const ct = E.ct; if (!ct || !ct.case_id) return toast("먼저 근로계약서를 저장하세요.");
  const panel = $("#payPanel"), f = ct.fields;
  panel.hidden = false; E.pending = {};
  const gross = num(f.base_wage) + num(f.allow_amount);
  panel.innerHTML = `<h2 class="panel-title">⑦ 급여명세서 발급 · 이체확인증 대조 <small class="muted">${esc(f.worker)} · ${esc(ct.company)}</small></h2>
    <p class="muted">근로계약서 조건(월급 ${won(num(f.base_wage))}${num(f.allow_amount) ? ` + ${esc(f.allow_name || "고정수당")} ${won(num(f.allow_amount))}` : ""} · 매월 ${esc(f.payday)}일 지급)으로 임금명세서를 발급하면 근로자 [내 서류함]으로 바로 전송됩니다.
      이체확인증은 은행이 발급하는 서류라 기업이 <b>첨부</b>하면, AI가 <b>이체금액·보내는 분(이체자)·받는 분(예금주)·이체일</b>을 읽어 명세서·계약과 대조합니다. 파일은 저장하지 않고 판독값만 기록합니다.</p>
    ${ct.worker_sign ? "" : '<p class="msg info">근로자 서명 전입니다. 실제 운영에서는 서명(계약 체결) 뒤에 급여명세서를 발급합니다. 담당자 신청 건에도 \'근로자 서명 대기\'로 표시됩니다.</p>'}
    <p class="meta">시연: [예시 선택]에서 사례를 고르면 가상 은행 양식의 이체확인증 이미지가 만들어져 첨부됩니다. 직접 만든 이미지·PDF도 [내 파일 첨부]로 올릴 수 있어요(AI 키가 있어야 판독).</p>
    <div class="btn-row"><button class="btn primary" type="button" id="payAll">6개월분 발급 + 예시 이체확인증 대조 (시연)</button>
      <span class="muted">지급총액 ${won(gross)} · 4번째 달 금액 다름, 6번째 달 이체자 다름 사례가 섞여 있어요.</span></div>
    <div id="payRows"></div><div id="paySum"></div>`;
  await drawPayRows();
  $("#payAll").onclick = async () => {
    const b = $("#payAll"); b.disabled = true;
    try {
      for (const [i, ym] of payMonths().entries()) {
        let p = await S.get("payslips", psId(ym)); if (!p) p = await issue(ym);
        E.pending[ym] = makeExample(p, BATCH[i], i);
        await transfer(ym, true);
      }
      await syncCase(true);
      toast(`6개월분 명세서를 근로자에게 보내고 이체확인증 대조를 마쳤어요. <a href="#officer">담당자 확인 대시보드</a>에 반영됐어요.`);
    } catch (err) { toast(esc(err.message)); }
    finally { b.disabled = false; drawPayRows(); }
  };
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}
async function drawPayRows() {
  const pays = Object.fromEntries((await S.list("payslips")).filter((p) => p.contract_id === E.ct.id).map((p) => [p.ym, p]));
  const now = today();
  $("#payRows").innerHTML = payMonths().map((ym) => { const p = pays[ym], pend = E.pending[ym];
    return `<div class="month-row pay" data-ym="${ym}"><div class="mth">${Number(ym.slice(5))}월분<small>${ym}${p ? ` · 지급 ${esc(p.pay_date)}${p.pay_date > now ? " (미리 발급·시연)" : ""}` : ""}</small></div>
      <div>${p ? `<b>실지급 ${won(p.net)}</b> <button class="btn ghost sm" type="button" data-view="${ym}">명세서 보기</button> <span class="badge 적정">근로자에게 전송됨</span>`
        : `<button class="btn ghost sm" type="button" data-issue="${ym}">명세서 발급·전송</button>`}
        <div class="tr-attach"><b>이체확인증 첨부</b>
          <div class="btn-row sm-gap"><select data-ex="${ym}" aria-label="예시 이체확인증 선택"><option value="">예시 선택…</option>${Object.entries(TR_CASES).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select>
            <label class="btn ghost sm">내 파일 첨부<input type="file" accept="image/png,image/jpeg,image/webp,application/pdf" data-trfile="${ym}" hidden></label></div>
          ${pend ? `<div class="tr-pend">${pend.src ? `<img src="${esc(pend.src)}" alt="첨부한 이체확인증" data-zoom>` : '<span class="badge 안내">PDF</span>'}<div><small>${esc(pend.label)}</small><br>
            <button class="btn primary sm" type="button" data-run="${ym}">AI 판독 · 대조</button></div></div>` : ""}</div></div>
      <div data-res>${p && p.check ? `${badge(p.check.level)} ${compareHtml(p)}` : '<span class="muted">이체확인증을 첨부하고 [AI 판독 · 대조]를 누르세요.</span>'}</div></div>`; }).join("");
  $$("#payRows [data-issue]").forEach((b) => (b.onclick = async () => { b.disabled = true; await issue(b.dataset.issue); await syncCase(false); drawPayRows(); }));
  $$("#payRows [data-view]").forEach((b) => (b.onclick = () => { const p = pays[b.dataset.view]; C.view(`${p.ym} 임금명세서`, C.payslipHtml(p)); }));
  $$("#payRows [data-ex]").forEach((sel) => (sel.onchange = async () => { if (!sel.value) return; const ym = sel.dataset.ex;
    let p = pays[ym] || await S.get("payslips", psId(ym)); if (!p) p = await issue(ym);
    E.pending[ym] = makeExample(p, sel.value, payMonths().indexOf(ym)); drawPayRows(); }));
  $$("#payRows [data-trfile]").forEach((inp) => (inp.onchange = async () => { const fl = inp.files[0]; if (!fl) return;
    if (fl.size > 3 * 1024 * 1024) return toast("3MB 이하 파일만 올릴 수 있어요.");
    const file = await window.IeumDocs.fileToB64(fl);
    E.pending[inp.dataset.trfile] = { file, src: file.media_type.startsWith("image/") ? `data:${file.media_type};base64,${file.data}` : "", label: `내 파일: ${fl.name}`, kind: "file" };
    drawPayRows(); }));
  $$("#payRows [data-run]").forEach((b) => (b.onclick = async () => { b.disabled = true; await transfer(b.dataset.run); }));
  $$("#payRows [data-zoom]").forEach((im) => (im.onclick = () => C.view("첨부한 이체확인증", `<img src="${esc(im.src)}" alt="이체확인증" style="max-width:100%">`)));
  summary(Object.values(pays));
}
async function issue(ym) {
  const ct = E.ct, f = ct.fields, base = num(f.base_wage), allow = num(f.allow_amount), p = C.synthPay(base + allow, ym);
  const payday = Math.min(28, Math.max(1, num(f.payday) || 10));
  const rec = { contract_id: ct.id, case_id: ct.case_id, seeker_id: ct.seeker_id, worker: f.worker, company: ct.company, ym,
    pay_date: `${ymAdd(ym, 1)}-${pad(payday)}`, base, allow, allow_name: f.allow_name, gross: p.gross, ded: p.ded, dedTotal: p.dedTotal, net: p.net,
    monthly_hours: monthlyHours(C.hours(f).weekly || 40), emp_no: `E-${ct.id.slice(-6)}`, issued_at: new Date().toISOString(), sent_to_worker: true };
  return S.put("payslips", psId(ym), rec);
}
/** 첨부한 이체확인증(E.pending[ym]) 판독 → 발급한 명세서·계약과 대조 → 저장 */
async function transfer(ym, batch) {
  const row = $(`#payRows .month-row[data-ym="${ym}"] [data-res]`), pend = E.pending[ym];
  if (!pend) return;
  if (row) row.innerHTML = '<span class="muted">AI가 이체확인증을 읽고 명세서와 대조하는 중…</span>';
  try {
    let p = await S.get("payslips", psId(ym));
    if (!p) p = await issue(ym);
    const prev = (await S.list("payslips")).filter((x) => x.contract_id === p.contract_id && x.ym < ym).map((x) => ({ ym: x.ym, gross: x.gross }));
    const res = await api("/api/certificate", { method: "POST", timeoutMs: 45000, body: { kind: "claimdoc", consent: true, month: ym, files: [pend.file],
      issued_payslip: { name: p.worker, ym, pay_date: p.pay_date, gross: String(p.gross), deduction: String(p.dedTotal), net: String(p.net) },
      sample_truth: pend.truth, ctx: { worker: p.worker, company: p.company, hire_date: E.ct.fields.start_date, weekly_hours: C.hours(E.ct.fields).weekly || 40, history: prev } } });
    p.transfer = { kind: pend.kind === "file" ? "첨부 파일" : pend.label, read: res.transfer, read_source: res.source, model: res.model || "" };
    p.check = { level: res.check.level, items: res.check.items };
    await S.put("payslips", p.id, p);
    delete E.pending[ym];
    if (!batch) { await syncCase(false); drawPayRows(); }
  } catch (err) { if (row) row.innerHTML = `<div class="msg error">${esc(err.message)}</div>`; if (batch) throw err; }
}
function docsOf(pays) {
  const by = Object.fromEntries(pays.map((p) => [p.ym, p])), ms = payMonths();
  const done = ms.filter((m) => by[m] && by[m].check), gross = done.map((m) => by[m].gross);
  return { program: "청년일자리도약장려금", expected: ms.length, uploaded: done.length,
    mismatch: done.filter((m) => by[m].check.level === "불일치").length, check: done.filter((m) => by[m].check.level === "확인 필요").length,
    avg: gross.length ? Math.floor(gross.reduce((a, b) => a + b, 0) / gross.length) : 0, total: gross.reduce((a, b) => a + b, 0),
    months: ms.map((m) => ({ month: m, level: by[m] && by[m].check ? by[m].check.level : "미첨부",
      note: by[m] && by[m].check ? by[m].check.items.filter((i) => i.level !== "일치").map((i) => `${i.item}: ${i.detail}`).join(" / ")
        : by[m] ? "명세서 발급 · 이체확인증 대기" : "" })) };
}
function summary(pays) {
  const d = docsOf(pays);
  $("#paySum").innerHTML = d.uploaded ? `<div class="docs-sum"><div><small>대조 완료</small><b>${d.uploaded}/${d.expected}개월</b></div>
    <div><small>불일치 · 확인 필요</small><b>${d.mismatch} · ${d.check}</b></div><div><small>평균 월 지급총액</small><b>${won(d.avg)}</b></div>
    <div><small>담당자 신청 건</small><b>자동 반영</b></div></div>
    ${d.mismatch ? '<p class="msg info">금액이 다른 달이 있어요. 신청 전에 추가 이체 내역 등 정정 서류를 올려 두세요.</p>' : ""}` : "";
}
/** 신청 건에 월별 기록 반영. 6개월 모두 대조되면 고용유지 6개월 시점 기준으로 다시 정리(시연 기준일) */
async function syncCase(rebuild) {
  const ct = E.ct, cs = await S.get("cases", ct.case_id); if (!cs) return;
  const docs = docsOf((await S.list("payslips")).filter((p) => p.contract_id === ct.id));
  let core = { checklist: cs.base_checklist || cs.checklist, status: cs.status_base || cs.status, schedule: cs.schedule, evidence: cs.evidence, as_of: cs.as_of, contract: cs.contract };
  if (rebuild && docs.uploaded === docs.expected) {
    const six = cs.schedule.six_month_date, asOf = six > today() ? six : "";
    try {
      const r = await api("/api/cases", { method: "POST", timeoutMs: 20000, body: { posting: ct.posting_form, posting_id: ct.posting_id, applicant_id: ct.applicant_id,
        hire_date: ct.fields.start_date, contract: C.toCheck(ct.fields), applicant: ct.applicant || undefined, as_of: asOf || undefined } });
      core = { checklist: r.case.checklist, status: r.case.status, schedule: r.case.schedule, evidence: r.case.evidence, as_of: r.case.as_of, contract: r.case.contract };
    } catch (e) { /* 다시 정리하지 못하면 기존 건 유지 */ }
  }
  const checklist = [...core.checklist];
  let status = core.status;
  if (docs.mismatch || docs.check || docs.uploaded < docs.expected) {
    checklist.push({ level: "확인 필요", item: "월별 서류 사전 점검", basis: "이음24 발급 명세서 · 기업 첨부 이체확인증 (월별 점검 기록)",
      detail: `대조 ${docs.uploaded}/${docs.expected}개월 · 불일치 ${docs.mismatch}건 · 확인 필요 ${docs.check}건 — 아래 월별 기록 확인` });
    if (status === "검토 대기") status = "확인 필요";
  }
  await S.put("cases", cs.id, { ...cs, ...core, base_checklist: core.checklist, status_base: core.status, checklist, status, docs,
    contract_status: ct.status, sign_kind: ct.sign_kind || "" });
}

/* ================= 담당자 화면에서 서류 보기 ================= */
async function viewContract(id) {
  const c = await S.get("contracts", id);
  if (!c) return toast("계약서를 찾지 못했어요.");
  const chk = (c.check || []).filter((r) => r.level !== "적정");
  C.view(`근로계약서 — ${c.company} · ${c.fields.worker} (${c.status})`, C.docHtml(c.fields, { seal: c.seal, sign: c.worker_sign })
    + `<div class="lc-note"><b>저장 기록</b> 사업주 날인: 법인 인장(가상) · 근로자: ${esc(c.sign_kind || "서명 대기")}${c.signed_at ? ` (${esc(new Date(c.signed_at).toLocaleString("ko-KR"))})` : ""}<br>
      규칙 점검: ${chk.length ? chk.map((r) => `${esc(r.item)}(${esc(r.level)})`).join(", ") : "이상 없음"}</div>`);
}
async function viewPays(contractId) {
  const pays = (await S.list("payslips")).filter((p) => p.contract_id === contractId).sort((a, b) => a.ym.localeCompare(b.ym));
  if (!pays.length) return toast("아직 발급된 급여명세서가 없어요.");
  C.view(`급여명세서·이체확인증 대조 ${pays.length}건`, pays.map((p) => `<div class="ps-wrap">${C.payslipHtml(p)}
    <div class="lc-note"><b>이체확인증 대조</b> ${p.check ? `${badge(p.check.level)} ${compareHtml(p)}` : "이체확인증 대기"}</div></div>`).join(""));
}

/* 시연 데이터 초기화 (두 번 눌러야 실행) */
const rs = $("#storeReset");
if (rs) rs.onclick = async () => {
  if (!rs.dataset.armed) { rs.dataset.armed = "1"; rs.textContent = "한 번 더 누르면 모두 지워져요"; setTimeout(() => { delete rs.dataset.armed; rs.textContent = "시연 데이터 초기화"; }, 4000); return; }
  try { await S.reset(); toast("저장된 시연 데이터를 모두 지웠어요."); } catch (err) { toast(esc(err.message)); }
  delete rs.dataset.armed; rs.textContent = "시연 데이터 초기화"; renderCompanies();
};

window.IeumFlow = { saveSeeker, extraPostings, apply, markApplied, seekerInbox, enterEmployer, publishBox, viewContract, viewPays };
})();
