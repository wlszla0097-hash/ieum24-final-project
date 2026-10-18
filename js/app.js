// 이음24 — 화면 이동, 입력 검증, API 호출(fetch), 결과 표시
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const badge = (label) => `<span class="badge ${esc(String(label).replace(/\s/g, ""))}">${esc(label)}</span>`;
const safeUrl = (u) => (/^https?:\/\//.test(u || "") ? u : "");
const won = (n) => (n || n === 0 ? `${Number(n).toLocaleString("ko-KR")}원` : "-");
const EUM = '<span class="eum">✓ 지원제도 활용 가능</span>';

// 화면 사이에서 이어지는 상태. 시연용 저장(이력·지원·계약서·명세서)은 store.js / workflow.js
const state = { seekExamples: [], profile: null, headline: "", postExamples: [], post: null, postInput: null, jobs: [], consentLog: [], points: [], portfolio: "", cert: null };

/* ---------- 1. 화면 이동 (해시 라우팅) ---------- */
const ROUTES = ["home", "seeker", "employer", "officer", "about"];
function route() {
  const h = location.hash.slice(1);
  const name = ROUTES.includes(h) ? h : "home";
  $$(".page").forEach((p) => (p.hidden = p.dataset.page !== name));
  $$(".nav a").forEach((a) => { a.classList.toggle("active", a.dataset.route === name); a.toggleAttribute("aria-current", a.dataset.route === name); });
  $("#nav").classList.remove("open");
  setTimeout(() => ($("#toast").hidden = true), 1500); // 화면 이동 후 안내 닫기
  $("#menuBtn").setAttribute("aria-expanded", "false");
  window.scrollTo({ top: 0 });
  if (name === "seeker") { loadSeekExamples(); if (window.IeumFlow) window.IeumFlow.seekerInbox(); }
  if (name === "employer" && window.IeumFlow) window.IeumFlow.enterEmployer();
  if (name === "officer") loadCases();
  if (name === "about") loadStatus();
}
window.addEventListener("hashchange", route);
$("#menuBtn").addEventListener("click", () => {
  const open = $("#nav").classList.toggle("open");
  $("#menuBtn").setAttribute("aria-expanded", String(open));
});

/* ---------- 다크 모드 ---------- */
const syncThemeIcon = () => ($("#themeBtn").textContent = document.documentElement.dataset.theme === "dark" ? "☀️" : "🌙");
syncThemeIcon();
$("#themeBtn").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  syncThemeIcon();
  try { localStorage.setItem("theme", next); } catch (e) { /* 저장 불가 환경은 무시 */ }
});

/* ---------- 2. 공통 API 호출: 시간 초과·지연 안내·오류 메시지 ---------- */
async function api(path, { method = "GET", body, timeoutMs = 45000, onSlow, headers = {} } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const slow = onSlow ? setTimeout(onSlow, 8000) : null; // 8초 넘으면 '지연 중' 안내
  try {
    const res = await fetch(path, {
      method, headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
      body: body ? JSON.stringify(body) : undefined, signal: ctrl.signal,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* JSON 아닌 응답 */ }
    if (!res.ok || !data || data.ok === false) {
      const fallback = res.status >= 500 ? "서버에 일시적인 문제가 있습니다. 잠시 후 다시 시도하세요." : "요청을 처리하지 못했습니다. 입력값을 확인하세요.";
      const e = new Error(`${(data && data.message) || fallback} (오류 코드 ${res.status})`);
      if (data) Object.assign(e, { code: data.error, detail: data.detail });
      throw e;
    }
    return data;
  } catch (err) {
    if (err.name === "AbortError") throw new Error("응답 시간이 초과되었습니다. 네트워크 상태를 확인하고 잠시 후 다시 시도하세요.");
    if (err instanceof TypeError) throw new Error("서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요.");
    throw err;
  } finally {
    clearTimeout(timer);
    if (slow) clearTimeout(slow);
  }
}
window.ieumApi = api; // claimdocs.js(⑦ 월별 서류 점검)에서 같은 호출 규칙을 쓴다
function showMsg(el, text, type = "error") { el.textContent = text; el.className = `msg ${type}`; el.hidden = !text; }
const revealOnMobile = (el) => { if (window.matchMedia("(max-width: 900px)").matches) el.scrollIntoView({ behavior: "smooth", block: "start" }); };
const loadingHtml = (text) => `<div class="loading"><div><div class="spinner"></div><p>${esc(text)}</p></div></div>`;
const errorHtml = (err) => `<div class="empty"><span>⚠️</span><p>${esc(err.message)}</p></div>`;
function toast(html) {
  const t = $("#toast"); t.innerHTML = html; t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), 6000);
}
$$("textarea[maxlength]").forEach((ta) => ta.addEventListener("input", () => {
  const c = $(`.counter[data-for="${ta.id}"]`); if (c) c.textContent = `${ta.value.length}/${ta.maxLength}`;
}));

const fmt = (n) => (n || n === 0 ? Number(n).toLocaleString("ko-KR") : "");
/* ---------- 3. 구직자: 직접 쓴 경험 → AI 정리·역량 문장·공고 추천 ---------- */
const SEEK_FIELDS = ["alias", "kuchwi", "kuchwi_qualified", "kuchwi_iap", "kuchwi_job_after", "dojeon", "dojeon_completed", "youth", "mil", "mil_age", "mil_months", "experience", "job", "region",
  "consent", "agree_privacy", "agree_ai", "agree_detail", "agree_cert"];
const CONSENT_VERSION = "2026-10-10-v1";
const seekEl = (k) => $(`#seekForm [name="${k}"]`);
function readSeekForm() {
  const f = {};
  SEEK_FIELDS.forEach((k) => { const el = seekEl(k); f[k] = el.type === "checkbox" ? el.checked : el.value.trim(); });
  f.cert = f.agree_cert ? state.cert : null;            // 본인이 확인한 판독값 (판단은 폼 값으로)
  f.points = state.points || [];                         // 정리된 활동 = 기업 화면 핵심 포인트
  f.portfolio = state.portfolio || "";
  return f;
}

/* 동의 기록·철회 (이 탭 안에만 기록) */
function logConsent(item, agreed) {
  state.consentLog.unshift({ item, action: agreed ? "동의" : "철회", at: new Date().toLocaleString("ko-KR"), version: CONSENT_VERSION });
  $("#consentLog").innerHTML = state.consentLog.map((c) => `<li><b>${esc(c.action)}</b> ${esc(c.item)} · ${esc(c.at)} · 문구 ${esc(c.version)}</li>`).join("");
}
$$("#seekForm [data-consent]").forEach((el) => el.addEventListener("change", () => {
  logConsent(el.dataset.consent, el.checked);
  if (el.name === "agree_privacy" && !el.checked) {            // 필수 동의 철회 → 입력·결과 삭제
    ["experience", "kuchwi_qualified", "dojeon_completed", "job"].forEach((k) => (seekEl(k).value = ""));
    Object.assign(state, { profile: null, points: [], portfolio: "", cert: null, headline: "" });
    $("#certResult").innerHTML = "";
    $("#seekResult").innerHTML = '<div class="empty"><span>🗑</span><p>개인정보 수집·이용 동의를 철회해<br>입력 내용과 결과를 삭제했습니다.</p></div>';
  }
  if (el.name === "agree_cert" && !el.checked) { state.cert = null; $("#certResult").innerHTML = ""; }
}));

/* 증빙 서류 판독: AI는 읽기만 하고, 값은 본인이 확인한 뒤 폼에 남는다 */
const toBase64 = (file) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = rej; r.readAsDataURL(file); });
/* 시연용 예시 증빙 서류: 가상 양식 이미지를 만들어 '첨부한 것처럼' 쓴다 (내 파일을 고르면 그쪽이 우선) */
/* 예시 서류는 지금 입력된 사람의 이름·날짜로 만든다 — 다른 사람 예시 날짜가 입력 칸을 덮어써 시연 판정이 바뀌는 일 방지 */
function personalCert(c) {
  if (!c) return c;
  const ymd = (s) => { const [y, m, d] = s.split("-").map(Number); return `${y}. ${m}. ${d}.`; };
  const plus = (s, n) => { const t = new Date(`${s}T00:00:00`); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
  const alias = (seekEl("alias") && seekEl("alias").value.trim()) || "";
  const name = alias ? `${alias}(가상)` : c.name;
  const q = seekEl("kuchwi_qualified") && seekEl("kuchwi_qualified").value, done = seekEl("dojeon_completed") && seekEl("dojeon_completed").value;
  if (c.kind === "kuchwi" && /^\d{4}-\d{2}-\d{2}$/.test(q || "")) {
    return { ...c, name, rows: c.rows.map(([k, v]) => [k, k === "수급자격 인정일" ? ymd(q) : k === "취업활동계획 수립일" ? ymd(plus(q, 14)) : v]), truth: { ...c.truth, date: q } };
  }
  if (c.kind === "dojeon" && /^\d{4}-\d{2}-\d{2}$/.test(done || "")) {
    return { ...c, name, date: done, rows: c.rows.map(([k, v]) => [k, k === "수료일" ? ymd(done) : k === "참여기간" ? `${ymd(plus(done, -88))} ~ ${ymd(done)}` : v]), truth: { ...c.truth, date: done } };
  }
  return { ...c, name };
}
$("#certSample").addEventListener("change", (e) => {
  const c = personalCert(window.IeumContract.CERT_SAMPLES[e.target.value]);
  state.certSample = c ? { media_type: "image/png", data: window.IeumContract.drawCertificate(c).split(",")[1], label: e.target.selectedOptions[0].text,
    truth: { doc_type: c.kind === "kuchwi" ? "참여확인서" : "수료증", program_text: c.rows.find(([k]) => k === "사업명")?.[1] || "", course: c.rows.find(([k]) => k === "과정명")?.[1] || "",
      issuer: c.issuer.replace(/ (센터장|소장|원장)$/, ""), date: c.truth.date, date_label: c.kind === "kuchwi" ? "수급자격 인정일" : "수료일", readable: true } } : null;
  $("#certSampleName").textContent = c ? "예시 서류를 첨부했어요 → [AI로 읽기]" : "";
  if (c) $("#certFile").value = "";
});
$("#certFile").addEventListener("change", () => { if ($("#certFile").files[0]) { state.certSample = null; $("#certSample").value = ""; $("#certSampleName").textContent = ""; } });
$("#certBtn").addEventListener("click", async () => {
  const out = $("#certResult"), file = $("#certFile").files[0], sample = !file && state.certSample;
  if (!seekEl("agree_cert").checked) return (out.innerHTML = '<p class="msg error">[선택] 증빙 서류 AI 판독에 동의해야 읽을 수 있어요. 동의하지 않으면 날짜를 직접 입력하세요.</p>');
  if (!file && !sample) return (out.innerHTML = '<p class="msg error">필수값을 입력하세요: 증빙 파일 (또는 예시 서류 선택)</p>');
  if (file && file.size > 3 * 1024 * 1024) return (out.innerHTML = '<p class="msg error">파일이 너무 큽니다. 3MB 이하로 올려 주세요.</p>');
  const btn = $("#certBtn"); btn.disabled = true; btn.textContent = "읽는 중…";
  out.innerHTML = '<p class="muted">AI가 서류를 읽고 있어요 (10초 안팎)…</p>';
  try {
    const r = await api("/api/certificate", { method: "POST", timeoutMs: 45000,
      body: sample ? { media_type: sample.media_type, data: sample.data, consent: true, sample_truth: sample.truth } : { media_type: file.type, data: await toBase64(file), consent: true } });
    state.cert = { program: r.program, date: r.date, issuer: r.issuer, course: r.course };
    if (r.program === "청년도전지원사업") { seekEl("dojeon").checked = true; if (r.date) seekEl("dojeon_completed").value = r.date; }
    if (r.program === "국민취업지원제도") { seekEl("kuchwi").checked = true; if (r.date) seekEl("kuchwi_qualified").value = r.date; }
    syncProgramBoxes();
    out.innerHTML = `<div class="cert-read ${r.readable ? "" : "warn"}"><b>AI 판독 결과</b> (${esc(r.doc_type || "서류")})
      <ul><li>사업: <b>${esc(r.program)}</b> ${r.program_text ? `(서류 표기: ${esc(r.program_text)})` : ""}</li>
      ${r.course ? `<li>과정: ${esc(r.course)}</li>` : ""}${r.issuer ? `<li>발급기관: ${esc(r.issuer)}</li>` : ""}
      <li>${esc(r.date_label || "날짜")}: <b>${esc(r.date || "읽지 못함")}</b></li></ul>
      <small>${r.program === "기타" ? "국민취업지원제도·청년도전지원사업 서류로 확인되지 않았어요. 위 체크는 바꾸지 않았습니다." : "위 칸에 채웠어요."} ${esc(r.note)}</small></div>`;
  } catch (err) {
    out.innerHTML = `<p class="msg error">${esc(err.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = "AI로 읽기"; }
});
function fillForm(root, values, names) {
  names.forEach((k) => {
    const el = $(`[name="${k}"]`, root); if (!el || !(k in values)) return;
    if (el.type === "checkbox") el.checked = !!values[k]; else el.value = values[k] ?? "";
    el.dispatchEvent(new Event("input"));
  });
}
function syncProgramBoxes() {
  $("#milWrap").hidden = $("#youth").checked;  // 만 15~34세가 아닐 때만 군필 연령 연동 확인
  if ($("#milWrap").hidden) $("#mil").checked = false;  // 청년(15~34)에 체크하면 군필 연동 입력은 쓰지 않음
  $$(".sub[data-for]").forEach((s) => (s.hidden = !$("#" + s.dataset.for).checked));
}
["kuchwi", "dojeon", "youth", "mil"].forEach((id) => $("#" + id).addEventListener("change", syncProgramBoxes));

async function loadSeekExamples() {
  if (state.seekExamples.length) return;
  try {
    state.seekExamples = (await api("/api/seeker", { timeoutMs: 15000 })).examples;
    $("#seekExample").insertAdjacentHTML("beforeend", state.seekExamples.map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join(""));
  } catch (e) { /* 예시는 없어도 직접 입력 가능 */ }
}
$("#seekExample").addEventListener("change", (e) => {
  const x = state.seekExamples.find((v) => v.id === e.target.value);
  if (!x) return;
  state.exampleId = x.id;  // AI 테스트 기록에 어떤 합성 구직자로 돌렸는지 남김
  ["kuchwi", "kuchwi_iap", "kuchwi_job_after", "dojeon"].forEach((k) => (seekEl(k).checked = false));
  ["kuchwi_qualified", "dojeon_completed"].forEach((k) => (seekEl(k).value = ""));
  fillForm($("#seekForm"), x.form, SEEK_FIELDS.filter((k) => k !== "consent"));
  syncProgramBoxes();
});

$("#seekForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#seekMsg"), body = readSeekForm();
  $$(".invalid", $("#seekForm")).forEach((el) => el.classList.remove("invalid"));
  if (!body.agree_privacy) return showMsg(msg, "[필수] 개인정보 수집·이용에 동의해 주세요. (아래 4번 항목)");
  const need = [["experience", "내 경험"], ["job", "희망 직무"]];
  if (body.kuchwi) need.push(["kuchwi_qualified", "국민취업지원제도 수급자격 인정일"]);
  if (body.dojeon) need.push(["dojeon_completed", "청년도전지원사업 수료일"]);
  if (!body.youth && body.mil) need.push(["mil_age", "만 나이"], ["mil_months", "의무복무 기간(개월)"]);
  const missing = need.filter(([k]) => !body[k]);
  missing.forEach(([k]) => seekEl(k).classList.add("invalid"));
  if (missing.length) return showMsg(msg, `필수값을 입력하세요: ${missing.map(([, l]) => l).join(", ")}`);
  if (body.experience.length < 10) { seekEl("experience").classList.add("invalid"); return showMsg(msg, "내 경험을 조금 더 자세히(10자 이상) 적어 주세요."); }
  showMsg(msg, "");
  const btn = $("#seekBtn"), out = $("#seekResult");
  btn.disabled = true; btn.textContent = "정리 중…";
  out.innerHTML = loadingHtml("AI가 내 경험을 정리하고 맞는 공고를 고르고 있어요");
  revealOnMobile(out);
  try {
    const extra = window.IeumFlow ? await window.IeumFlow.extraPostings() : [];  // 기업 화면에서 게시한 공고도 추천 후보에
    const t0 = performance.now();
    const data = await api("/api/seeker", { method: "POST", body: { ...body, extra_postings: extra },
      onSlow: () => (out.innerHTML = loadingHtml("AI 응답이 평소보다 늦어지고 있어요. 조금만 기다려 주세요 (최대 45초)")) });
    logAI("이력 정리·공고 추천", body, t0, { model: data.meta.ai_used ? data.meta.model : "", ai_used: !!data.meta.ai_used, guard_blocked: data.meta.guard_blocked ?? null,
      error: data.meta.ai_used ? "" : data.meta.ai_error || "",
      result: { competencies: data.competencies.map((c) => c.text), resume_intro: data.resume_intro || "",
        jobs: data.jobs.map((j) => ({ id: j.id, company: j.company, title: j.title, eligible: !!(j.badge && j.badge.eligible), badge_shown: !!(j.badge && j.badge.show) })) } });
    state.points = data.activities.map((a) => a.name);
    state.profile = { ...body, points: state.points };
    state.headline = data.competencies[0]?.text || "";
    state.jobs = data.jobs;
    renderSeeker(data);
    if (window.IeumFlow) window.IeumFlow.saveSeeker().then(() => window.IeumFlow.markApplied()).catch((err) => toast(esc(err.message)));
  } catch (err) {
    out.innerHTML = errorHtml(err);
  } finally {
    btn.disabled = false; btn.textContent = "AI로 이력 정리 · 공고 추천";
  }
});

/** AI 호출 1회 기록 → 시연 데이터 ailog 에 저장 (모델 비교용, [테스트 결과 내보내기]에 포함). 실패해도 화면 흐름은 계속 */
function logAI(kind, body, t0, rec) {
  if (!window.IeumStore) return;
  const at = new Date().toISOString(), id = `${at.replace(/[^\d]/g, "").slice(0, 17)}-${Math.random().toString(36).slice(2, 6)}`;
  window.IeumStore.put("ailog", id, { at, kind, ms: Math.round(performance.now() - t0), example_id: state.exampleId || "", alias: body.alias || "",
    seeker_id: window.IeumStore.me(), job: body.job || "", ...rec }).catch(() => {});
}

function renderSeeker({ activities, competencies, resume_intro, jobs, programs, meta }) {
  const aiNote = meta.ai_used
    ? `<p class="meta">🤖 AI ${esc(meta.model)} 정리 · 원문에 없는 숫자·내용 등으로 서버가 차단한 문장 ${meta.guard_blocked}건</p>`
    : `<div class="msg info">${esc(meta.ai_error || "AI 결과 없이 규칙 기반 기본 정리로 표시합니다.")}</div>`;
  const acts = activities.length ? `<table class="acts"><thead><tr><th>구분</th><th>활동</th><th>기간</th></tr></thead><tbody>${
    activities.map((a) => `<tr><td><span class="kind">${esc(a.kind)}</span></td><td>${esc(a.name)}</td><td>${esc(a.period || "-")}</td></tr>`).join("")}</tbody></table>` : "";
  const comps = competencies.map((c) => `<li>${esc(c.text)}${c.evidence ? `<small>근거: ${esc(c.evidence)}</small>` : ""}</li>`).join("");
  const cards = jobs.map((j) => `
    <article class="job">
      <div class="job-head"><h3>${esc(j.title)}</h3>${j.source === "employer" ? '<span class="badge 안내">기업이 이음24에 게시</span>' : ""}${j.badge.show ? EUM : ""}</div>
      <div class="agency">${esc(j.company)} · ${esc(j.region)} · ${esc(j.emp_type || "고용형태 미상")} · 월 ${won(j.wage)} · 마감 ${esc(j.close || "-")}</div>
      ${j.matched.length ? `<div class="tags">${j.matched.map((m) => `<span>${esc(m)}</span>`).join("")}</div>` : ""}
      <p>${esc(j.reason)}</p>
      ${j.prep ? `<p class="next">👉 ${esc(j.prep)}</p>` : ""}
      <div class="mine ${j.badge.eligible ? "yes" : ""}"><b>나에게만 보이는 안내</b> ${esc(j.badge.text)}<br><small>기준: ${esc(j.badge.basis)} · 본인 입력 기준 예상 안내이며 최종 확인은 고용센터</small></div>
      <div class="job-actions">
        ${safeUrl(j.url) ? `<a class="btn ghost" href="${esc(j.url)}" target="_blank" rel="noopener">공고 원문 ↗</a>` : ""}
        <button class="btn primary apply" type="button" data-id="${esc(j.id)}">이 공고에 지원</button>
      </div>
    </article>`).join("");
  const ex = meta.excluded;
  $("#seekResult").innerHTML = `
    <h3>🗂 AI가 정리한 내 이력</h3>
    ${programs.length ? `<p class="muted">참여 고용서비스: ${programs.map(esc).join(" · ")}</p>` : ""}
    ${acts}
    <h3>📌 직무 역량 문장</h3>
    <ul class="comps">${comps}</ul>
    ${resume_intro ? `<details open><summary>자기소개서 첫 문단 초안</summary><p>${esc(resume_intro)}</p></details>` : ""}
    ${aiNote}
    <h3>🎯 추천 공고 ${jobs.length}건</h3>
    ${meta.no_match ? `<div class="msg info">작성한 경험·희망 직무와 맞는 공고가 아직 없어요. 희망 직무를 바꾸거나 경험에 사용한 도구·기술을 더 적어 보세요.</div>` : ""}
    ${jobs.length && !meta.consent ? `<div class="msg info">‘지원제도 활용 가능’ 표시에 동의하지 않아 기업에는 아무 표시도 보이지 않아요.</div>` : ""}
    ${cards}
    <p class="meta">공고 출처: ${meta.postings_source === "live" ? "고용24 채용정보 실시간" : "합성 공고(고용24 OpenAPI 승인 전 시연)"} · 제외: 임금체불 명단공개 ${ex.arrears}건, 고액·상습 체납 ${ex.tax_arrears || 0}건, 최저임금 미달 ${ex.min_wage || 0}건, 마감 ${ex.closed}건</p>
    <h3>📄 내 포트폴리오</h3>
    <p class="muted">위에서 정리된 활동으로 AI가 초안을 한 번만 만들고, 직접 고쳐서 등록합니다. 기업은 <b>핵심 포인트</b>를 먼저 보고, 필요할 때만 전체를 펼칩니다. 참여 사업명은 기업 화면에서 자동으로 가려집니다.</p>
    <div class="pf-actions"><button class="btn ghost" id="pfAi" type="button">AI 초안 만들기</button><span class="muted" id="pfMsg"></span></div>
    <div class="pf-review" id="pfReview" hidden></div>
    <textarea id="pfText" rows="10" maxlength="4000" placeholder="직접 작성하거나 [AI 초안 만들기]를 누르세요.">${esc(state.portfolio || "")}</textarea>
    <label class="pf-check" id="pfCheckWrap" hidden><input type="checkbox" id="pfChecked"> <span>표시된 부분을 내 경험과 대조해 확인하고, 필요한 곳은 고쳤어요 <small class="muted">— 색 표시는 검토용이에요. [포트폴리오 저장]을 누르면 표시 없이 기본 글꼴로 저장돼요.</small></span></label>
    <button class="btn primary block" id="pfSave" type="button">포트폴리오 저장</button>`;
  /* AI 초안 검토 표시: 내 경험에 없는 말·과장 표현에 색을 입혀 그 부분부터 확인하게 한다 (최종 내용은 본인이 정함) */
  const pfSource = () => { const f = readSeekForm(); return [f.job, f.experience, ...(state.points || [])].join("\n"); };
  let pfFromAi = !!state.portfolioFromAi, pfTimer = null;
  const pfRender = () => {
    const box = $("#pfReview"), text = $("#pfText").value;
    if (!pfFromAi || !text.trim() || !window.IeumReview) { box.hidden = true; $("#pfCheckWrap").hidden = true; state.pfFlags = 0; return; }
    const r = window.IeumReview.mark(text, pfSource());
    state.pfFlags = r.total;
    box.hidden = false;
    box.innerHTML = `<div class="legend"><b>AI 초안 검토 도우미</b>`
      + (r.total ? `<span><span class="pf-add">노란 표시</span> 내 경험에 없는 말 ${r.added}문장</span><span><span class="pf-puff">빨간 물결</span> 과장·단정 표현 ${r.puff}문장</span>`
        : `<span class="ok">표시할 곳이 없어요. 그래도 한 번 읽어 보세요.</span>`)
      + `<span>아래 칸에서 고치면 바로 다시 표시돼요</span></div>${r.html}`;
    $("#pfCheckWrap").hidden = !r.total;
  };
  $("#pfText").addEventListener("input", () => { clearTimeout(pfTimer); pfTimer = setTimeout(pfRender, 300); });
  pfRender();
  $("#pfAi").addEventListener("click", async () => {
    const b = $("#pfAi"), m = $("#pfMsg"), body = readSeekForm();
    if (!body.agree_ai) return (m.textContent = "AI 처리 동의(4번 두 번째 항목)가 필요해요. 직접 작성해도 됩니다.");
    b.disabled = true; m.textContent = "AI가 초안을 쓰고 있어요…";
    const t0 = performance.now();
    try {
      const r = await api("/api/seeker", { method: "POST", body: { ...body, action: "portfolio" } });
      logAI("포트폴리오 초안", body, t0, { model: r.meta.model, ai_used: true, guard_blocked: r.meta.guard_blocked, result: { portfolio: r.portfolio } });
      $("#pfText").value = r.portfolio;
      pfFromAi = state.portfolioFromAi = true; $("#pfChecked").checked = false; pfRender();
      const rm = r.meta.removed || {};
      m.textContent = `초안 완료 · ${r.meta.chars ?? r.portfolio.length}자 · 원문에 없는 내용 차단 ${r.meta.guard_blocked}건 · 중복 ${rm.duplicate ?? 0}·과장 표현 ${rm.puffery ?? 0}·원문에 없는 기술명 ${rm.unknown_term ?? 0}문장 제외 · 색으로 표시된 부분부터 확인하고 고친 뒤 저장하세요.`;
    } catch (err) { logAI("포트폴리오 초안", body, t0, { ai_used: false, error: err.message }); m.textContent = err.message; } finally { b.disabled = false; }
  });
  $("#pfSave").addEventListener("click", async () => {
    if (pfFromAi) pfRender();
    if (pfFromAi && state.pfFlags && !$("#pfChecked").checked) {
      $("#pfMsg").textContent = `표시된 ${state.pfFlags}곳을 내 경험과 대조해 확인한 뒤, 아래 확인 칸을 체크하고 저장하세요.`;
      $("#pfCheckWrap").scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    state.portfolio = $("#pfText").value.trim();
    if (state.profile) state.profile.portfolio = state.portfolio;
    try { if (window.IeumFlow) await window.IeumFlow.saveSeeker(); } catch (err) { return toast(esc(err.message)); }
    // 저장되는 것은 입력 칸의 글(색·표시 없는 기본 글꼴)뿐 → 검토 표시는 닫는다
    pfFromAi = state.portfolioFromAi = false; pfRender();
    toast(state.portfolio ? "포트폴리오를 저장했어요(색 표시 없이 기본 글꼴). 지원한 기업 화면에서 핵심 포인트와 함께 보입니다." : "포트폴리오를 비웠어요.");
  });
  $$(".apply", $("#seekResult")).forEach((b) => b.addEventListener("click", async () => {
    const job = state.jobs.find((j) => j.id === b.dataset.id);
    b.disabled = true; b.textContent = "지원 중…";
    try {
      await window.IeumFlow.apply(job);
      b.textContent = "지원 완료 ✓";
      window.IeumFlow.seekerInbox();  // 내 서류함 '지원 현황'에 바로 반영
      toast(`${esc(job.company)}에 지원했어요. <a href="#employer">기업 화면</a>에서 이 회사를 고르면 지원자 목록에 내 지원서가 보여요.`);
    } catch (err) { b.disabled = false; b.textContent = "이 공고에 지원"; toast(esc(err.message)); }
  }));
}

/* ---------- 4. 기업: 공고 올리기 (점검·AI 정리 → 게시) ----------
 * 회사 선택·공고 확인·지원자·채용 확정(근로계약서)·급여명세서는 workflow.js */
const POST_FIELDS = ["busino", "industry", "company", "sido", "sigungu", "title", "job", "emp_type", "wage", "weekly_hours", "insured", "priority", "close", "description"];
const postEl = (k) => $(`#postForm [name="${k}"]`);
["p_wage", "p_insured"].forEach((id) => $("#" + id).addEventListener("input", (e) => {
  const n = e.target.value.replace(/[^\d]/g, ""); e.target.value = n ? Number(n).toLocaleString("ko-KR") : "";
}));
function fillPost(form) { fillForm($("#postForm"), { ...form, wage: fmt(form.wage), insured: fmt(form.insured) }, POST_FIELDS.filter((k) => k in form)); }
$("#postForm").addEventListener("submit", (e) => { e.preventDefault(); runPostCheck(); });

function readPostForm() {
  const f = {};
  POST_FIELDS.forEach((k) => (f[k] = postEl(k).value.trim()));
  ["wage", "insured", "weekly_hours"].forEach((k) => (f[k] = f[k] === "" ? null : Number(f[k].replace(/[^\d.]/g, ""))));
  return f;
}

async function runPostCheck() {
  const msg = $("#postMsg"), body = readPostForm();
  $$(".invalid", $("#postForm")).forEach((el) => el.classList.remove("invalid"));
  const missing = [["sido", "근무지(시·도)"], ["title", "공고 제목"], ["job", "직무"], ["wage", "월 임금"]].filter(([k]) => !body[k]);
  missing.forEach(([k]) => postEl(k).classList.add("invalid"));
  if (missing.length) return showMsg(msg, `필수값을 입력하세요: ${missing.map(([, l]) => l).join(", ")}`);
  showMsg(msg, "");
  const btn = $("#postBtn");
  btn.disabled = true; btn.textContent = "점검 중…";
  $("#empArea").hidden = false;
  $("#postCheck").innerHTML = loadingHtml("규칙엔진이 공고를 점검하고 AI가 공고를 정리하고 있어요");
  $("#postPublish").innerHTML = "";
  $("#empArea").scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const data = await api("/api/employer", { method: "POST", body: { posting: body } });
    state.post = data.posting; state.postInput = body;
    renderPostCheck(data);
  } catch (err) {
    $("#postCheck").innerHTML = errorHtml(err);
  } finally {
    btn.disabled = false; btn.textContent = "공고 점검 · AI 정리 (게시 전 확인)";
  }
}

function checkList(items) {
  return items.map((r) => `<div class="check-item">${badge(r.level)}<div><b>${esc(r.item)}</b><br>${esc(r.detail)}<div class="basis">근거: ${esc(r.basis)}</div></div></div>`).join("");
}
const VERDICT_TONE = { "연계 가능성 높음": "적정", "확인 필요": "확인필요", "연계 어려움": "위반의심" };

function renderPostCheck(data) {
  const { posting, check, analysis, ai_error } = data;
  const ai = analysis ? `
    <h3>🤖 AI 공고 정리</h3>
    ${analysis.summary ? `<div class="summary">${esc(analysis.summary)}</div>` : ""}
    ${analysis.requirements.length ? `<p><b>요구 역량</b> <span class="tags">${analysis.requirements.map((r) => `<span>${esc(r)}</span>`).join("")}</span></p><p class="meta">요구 역량은 공고 본문에 실제로 적힌 단어만 남기고, 구직자 추천에 사용합니다.</p>` : ""}
    ${analysis.suggestions.length ? `<b>공고 보완 제안</b><ul>${analysis.suggestions.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}`
    : ai_error ? `<div class="msg info">AI 공고 정리: ${esc(ai_error)} — 규칙 점검 결과는 정상입니다.</div>` : "";
  $("#postCheck").innerHTML = `
    <h2 class="panel-title">④ 이 공고로 받을 수 있는 지원</h2>
    <p class="muted">${esc(posting.company)} · ${esc(posting.title)} · ${esc(posting.region)}</p>
    <div class="verdict ${VERDICT_TONE[check.verdict]}">청년일자리도약장려금 연계: <b>${esc(check.verdict)}</b></div>
    ${checkList(check.items)}
    ${ai}
    <p class="meta">※ 입력한 공고 정보 기준 사전 점검입니다. 최종 요건 확인은 고용센터에서 합니다.</p>`;
  if (window.IeumFlow) window.IeumFlow.publishBox(data);
}

/* ---------- 5. 담당자 확인 대시보드: 근거가 정리된 신청 건 (채용 확정으로 저장된 건 + 시연용 과거 건) ---------- */
async function loadCases() {
  const box = $("#cases");
  try {
    const [demo, saved] = await Promise.all([
      api("/api/cases", { timeoutMs: 15000 }).then((r) => r.cases),
      window.IeumStore ? window.IeumStore.list("cases").catch(() => []) : [],
    ]);
    saved.sort((x, y) => String(y.updated || "").localeCompare(String(x.updated || "")));
    const all = [...saved.map((c) => ({ ...c, fresh: true })), ...demo];
    $("#caseSrc").textContent = `신청 건 ${all.length}건 (이음24에서 채용 확정·저장된 건 ${saved.length}건 포함) · 합성 데이터 · ${window.IeumStore ? window.IeumStore.label() : ""}`;
    box.innerHTML = all.map(caseCard).join("");
    $$(".decide", box).forEach((b) => b.addEventListener("click", async () => {
      const card = b.closest(".case"), id = card.dataset.id, out = $(".decision", card);
      const c = saved.find((x) => x.case_id === id);
      if (!c) { out.textContent = `담당자 처리: ${b.dataset.v} (시연용 과거 건 — 저장되지 않음)`; return; }
      c.decision = { value: b.dataset.v, at: new Date().toLocaleString("ko-KR") };
      try { await window.IeumStore.put("cases", id, c); out.textContent = `담당자 처리: ${c.decision.value} · ${c.decision.at} (저장됨)`; }
      catch (err) { out.textContent = err.message; }
    }));
    $$("[data-view-contract]", box).forEach((b) => (b.onclick = () => window.IeumFlow.viewContract(b.dataset.viewContract)));
    $$("[data-view-pay]", box).forEach((b) => (b.onclick = () => window.IeumFlow.viewPays(b.dataset.viewPay)));
  } catch (err) {
    box.innerHTML = errorHtml(err);
  }
}
function caseCard(c) {
  const unsigned = c.contract_id && c.contract_status !== "체결 완료";  // 근로자 서명 전 계약서는 '검토 대기'가 될 수 없음
  if (unsigned && c.status === "검토 대기") c = { ...c, status: "확인 필요" };
  const tone = { "검토 대기": "적정", "확인 필요": "확인필요", "보완 필요": "위반의심" }[c.status];
  const s = c.schedule;
  const saved = c.contract_id ? `<div class="docs-in-case"><h4>채용 단계에서 저장된 서류 — 다시 요청하지 않습니다</h4>
      <div class="btn-row"><button class="btn ghost sm" type="button" data-view-contract="${esc(c.contract_id)}">📄 근로계약서 · ${esc(c.contract_status || "")}${c.sign_kind ? ` (근로자 ${esc(c.sign_kind)})` : ""}</button>
      <button class="btn ghost sm" type="button" data-view-pay="${esc(c.contract_id)}">💰 급여명세서·이체 확인 ${c.docs ? `${c.docs.uploaded}/${c.docs.expected}개월` : "0건"}</button></div></div>` : "";
  return `
  <article class="case panel ${c.fresh ? "fresh" : ""}" data-id="${esc(c.case_id)}">
    <header><div><small class="muted">${esc(c.case_id)} · ${esc(c.program)}${c.fresh ? " · 이음24 채용 확정 건" : " · 시연용 과거 건"}${c.as_of ? ` · 시연 기준일 ${esc(c.as_of)}` : ""}</small>
      <h3>${esc(c.company)} — ${esc(c.worker)}</h3><span class="muted">${esc(c.title)} · ${esc(c.region)} · 입사 ${esc(c.hire_date)}</span></div>
      <span class="badge ${tone}">${esc(c.status)}</span></header>
    <div class="grid2">
      <div>
        <h4>참여 이력 근거</h4>
        <div class="evidence ${c.evidence.open ? "" : "closed"}"><b>${esc(c.evidence.title)}</b><ul>${c.evidence.lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>
        <h4>신청 시기</h4>
        <p>고용유지 ${esc(s.months_kept)}개월 · 6개월 시점 ${esc(s.six_month_date)} · <b>${esc(s.state)}</b></p>
      </div>
      <div><h4>확인 항목</h4>${checkList(unsigned
        ? [...c.checklist, { level: "확인 필요", item: "근로계약서 서명", detail: "근로자 서명 대기 — 체결(양측 서명) 전 계약서", basis: "근로기준법 제17조 (근로조건 명시·교부)" }]
        : c.checklist)}
        ${c.manual && c.manual.length ? `<h4>담당자 확인 항목 <small class="muted">(자동 점검하지 않음)</small></h4><ul class="manual-list">${c.manual.map((m) => `<li><b>${esc(m.item)}</b> — ${esc(m.detail)} <small class="muted">${esc(m.basis)}</small></li>`).join("")}</ul>` : ""}</div>
    </div>
    ${saved}
    ${c.hiredocs && window.IeumHireDocs ? `<div class="docs-in-case">${window.IeumHireDocs.block(c.hiredocs)}</div>` : ""}
    ${c.docs && window.IeumDocs ? `<div class="docs-in-case">${window.IeumDocs.docsBlock(c.docs)}</div>` : ""}
    <footer><span class="decision muted">${c.decision ? `담당자 처리: ${esc(c.decision.value)} · ${esc(c.decision.at)} (저장됨)` : "자동 판정 없음 — 확인 후 처리하세요."}</span>
      <span><button class="btn ghost decide" data-v="보완 요청" type="button">보완 요청</button> <button class="btn primary decide" data-v="검토 완료" type="button">검토 완료</button></span></footer>
  </article>`;
}

/* ---------- 6. 연동 상태 ---------- */
async function loadStatus() {
  try {
    const s = await api("/api/health", { timeoutMs: 10000 });
    $("#status").textContent = `연동 상태 — AI: ${s.ai === "not_configured" ? "미설정(규칙 기반 기본 문장으로 동작)" : `${s.ai} (${s.model})`} · 고용24 채용정보: ${s.work24 === "configured" ? "연동" : "합성 공고 사용"} · 시연 데이터 저장: ${{ upstash: "서버 저장소(Upstash)", memory: "개발 서버 메모리", off: "각 브라우저(서버 저장소 미연결)" }[s.store] || "-"}`;
  } catch (err) {
    $("#status").textContent = `연동 상태 확인 실패: ${err.message}`;
  }
}
// route()는 index.html 마지막 스크립트에서 호출 (workflow.js까지 읽은 뒤)
