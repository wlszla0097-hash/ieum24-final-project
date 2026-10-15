/* 시연 데이터 저장 (로그인 없이 시연) — window.IeumStore
 *
 * 서버 저장소(Upstash Redis, /api/store)가 연결돼 있으면 서버에, 아니면 이 브라우저(localStorage)에 JSON으로 저장한다.
 * 묶음: seekers(구직자 이력·포트폴리오), companies(직접 등록한 기업), applications(지원), postings(기업이 게시한 공고), contracts(근로계약서),
 *       payslips(급여명세서·이체 확인), cases(담당자 확인 대시보드 신청 건)
 * 합성(가상) 데이터만 넣는 시연용이다.
 */
(function () {
"use strict";
const LS = "ieum24:demo:";
const COLS = ["seekers", "companies", "applications", "postings", "contracts", "payslips", "cases"];
let mode = null;          // "server" | "local"
let serverKind = "";      // upstash | memory
const mem = {};           // localStorage를 못 쓰는 환경(사생활 보호 모드 등)용

function lsGet(col) {
  try { return JSON.parse(localStorage.getItem(LS + col) || "{}") || {}; } catch (e) { return mem[col] || {}; }
}
function lsSet(col, obj) {
  mem[col] = obj;
  try { localStorage.setItem(LS + col, JSON.stringify(obj)); } catch (e) { /* 저장 불가 환경은 메모리만 */ }
}

async function init() {
  if (mode) return mode;
  try {
    const r = await fetch("/api/store", { cache: "no-store" });
    const d = await r.json();
    serverKind = d.mode;
    mode = d.mode === "upstash" || d.mode === "memory" ? "server" : "local";
  } catch (e) { mode = "local"; }
  return mode;
}
async function call(body) {
  const r = await fetch("/api/store", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json().catch(() => null);
  if (!r.ok || !d || d.ok === false) throw new Error((d && d.message) || `저장하지 못했습니다. (오류 코드 ${r.status})`);
  return d;
}

async function list(col) {
  await init();
  if (mode === "server") {
    const r = await fetch(`/api/store?col=${encodeURIComponent(col)}`, { cache: "no-store" });
    const d = await r.json().catch(() => null);
    if (!r.ok || !d || d.ok === false) throw new Error((d && d.message) || "저장된 시연 데이터를 불러오지 못했습니다.");
    return d.items || [];
  }
  return Object.values(lsGet(col));
}
async function get(col, id) { return (await list(col)).find((x) => x.id === id) || null; }
async function put(col, id, value) {
  await init();
  const v = { ...value, id, updated: new Date().toISOString() };
  if (mode === "server") return (await call({ op: "put", col, id, value: v })).item;
  const all = lsGet(col); all[id] = v; lsSet(col, all);
  return v;
}
async function del(col, id) {
  await init();
  if (mode === "server") return call({ op: "del", col, id });
  const all = lsGet(col); delete all[id]; lsSet(col, all);
}
async function reset() {
  await init();
  if (mode === "server") await call({ op: "reset" });
  COLS.forEach((c) => lsSet(c, {}));
}

/** 이 브라우저의 구직자 id (로그인 대신). 같은 브라우저로 다시 오면 같은 사람으로 본다 */
function me() {
  let id = null;
  try { id = localStorage.getItem(LS + "me"); } catch (e) { id = mem.me; }
  if (!id) {
    id = Math.random().toString(36).slice(2, 10);
    mem.me = id;
    try { localStorage.setItem(LS + "me", id); } catch (e) { /* 메모리만 */ }
  }
  return id;
}
/** 시연에서 다른 구직자로 새로 시작하거나(id 없음) 저장된 구직자로 바꾸기 (이 브라우저의 구직자 id 바꾸기) */
function newMe(given) {
  const id = given || Math.random().toString(36).slice(2, 10);
  mem.me = id;
  try { localStorage.setItem(LS + "me", id); } catch (e) { /* 메모리만 */ }
  return id;
}
/** 저장된 시연 데이터 전체 (JSON 내보내기·저장 현황용) */
async function dump() {
  const out = {};
  for (const c of COLS) out[c] = await list(c);
  return out;
}
function label() {
  if (mode === "server") return serverKind === "upstash" ? "서버 저장소(Upstash)에 저장 — 다른 기기에서도 같은 시연 데이터가 보여요" : "개발 서버 메모리에 저장 (서버를 끄면 사라짐)";
  return "이 브라우저에만 저장 — 같은 브라우저에서 구직자·기업·담당자 화면을 오가며 시연하세요";
}

window.IeumStore = { init, list, get, put, del, reset, me, newMe, dump, label, COLS, mode: () => mode };
})();
