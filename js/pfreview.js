/* 포트폴리오 검토 표시: AI 초안에서 '원문(내 경험)에 없는 말'과 '과장 표현'에 색을 입혀, 사용자가 그 부분부터 확인·수정하게 한다.
 * AI는 초안과 검토 포인트까지만, 최종 내용은 사용자가 정한다. 판단 근거는 글자 비교뿐이라 표시는 '확인해 보세요'이지 '틀렸다'가 아니다.
 * 방법: 문장의 낱말마다 글자 2개 묶음이 원문에 얼마나 있는지 본다(측정기를 → '측정·정기'가 원문에 있음 → 원문 낱말).
 */
(function (root) {
  // 과장·단정 표현 (서버 api/seeker.py PUFFERY와 같은 취지)
  const PUFF = /실무\s*(중심|능력|역량|전반)|전문(가|적|성)|능숙|뛰어난|탁월|완벽|숙련|최고의|누구보다|역량을\s*(갖추|키웠|쌓았)|갖추었|갖췄|갖춘|체계적|즉시|핵심\s*인재|빠르게\s*적응|준비가\s*되어|바로\s*(착수|적응|적용|투입|기여)|기여|입증|확고|이해하고\s*있|능력을\s*(키웠|길렀|향상)|니즈|완수/;
  const SKIP_LINE = /^■\s*(강점|사용 도구|경험)\s*$|^■\s*사용 도구/;

  const norm = (s) => String(s || "").toLowerCase().replace(/\s+/g, "");
  function grams(s) { const t = norm(s).replace(/[^0-9a-z가-힣]/g, ""); const g = new Set(); for (let i = 0; i < t.length - 1; i++) g.add(t.slice(i, i + 2)); return g; }

  // 명사 뒤에 붙는 조사 (긴 것부터) — 떼고 나면 명사 줄기
  const JOSA = ["에서는", "으로는", "에서", "에는", "으로", "에게", "까지", "부터", "처럼", "보다", "과의", "와의", "이나", "을", "를", "이", "가", "은", "는", "의", "에", "로", "와", "과", "도", "만", "나"];
  // 동사·형용사로 끝나는 말 — 덧붙은 '사실'은 주로 명사(치수, 장부, 전표…)이므로 동사는 비교하지 않는다
  const VERB_END = /(다|고|며|서|여|해|했|한|할|하는|하던|던|아|어|게|지|요|된|되는|될|운|은데|면|죠|니다|습니다|겠|려|도록|자|며는|기에|기|음|함|됨)[,.]?$/;
  // 원문에 없어도 내용을 덧붙인 것이 아닌 흔한 명사
  const COMMON_NOUN = new Set(("경험 직무 업무 기본 기초 활용 수행 담당 과정 이해 능력 역량 입사 후 이후 앞으로 데 수 것 등 및 또한 이 그 저 제 함께 직접 실제 " +
    "사용 도구 기술 신입 지원자 지원 강점 핵심 작업 일 부분 중심 연결 도움 분야 목표 관심 계기 태도 역할 노력 자세 흐름 개념 지식 기본기 방식 방법 내용 결과 " +
    "회사 기업 조직 팀 단계 순서 바탕 토대 기반 밑바탕 실무 현장 동안 총 회 주 개월 시간 차근차근 성실히 스스로 본인 처음 시작 경력 활동 교육 훈련 학습 수료 이수 참여 상담 " +
    "계획 준비 연습 실습 협업 완성 완료 스스로 순서대로 차례로 차례 꾸준히 적극적으로 성실히 정확히 빠르게 직접 이론 공부 프로그램 과목 시험 자격 자격증 합격 필기 실기 양성 입문 개요 전반 일상 일상적인 기본적인 기초적인 사내 부서 동료 고객 문서 자료 정리").split(/\s+/));

  /** 낱말 하나가 '원문에 없는 명사'인지 (동사·흔한 말·원문 낱말은 false) */
  function novelNoun(word, src) {
    let w = word.replace(/[^0-9A-Za-z가-힣·]/g, "").replace(/·/g, "");
    if (w.length < 2 || /^[0-9]+$/.test(w)) return false;
    // 꾸미는 말·동사형(다룬, 익힌, 수행하는, 정해진, 없이)은 먼저 걸러 낸다
    if (/(하는|되는|하던|했던|하며|하고|하여|해서|하게|하기|없이|있는|있던)$/.test(w)) return false;
    const last = w.charCodeAt(w.length - 1) - 0xac00;
    if (w.length <= 4 && last >= 0 && last < 11172 && last % 28 === 4 && !/(반|산|안|원|전|건|선|권|본|분|문|순|간|단|관|면)$/.test(w)) return false;  // 받침 ㄴ으로 끝나는 꾸미는 말(다룬·익힌·세운)
    let hadJosa = false;
    for (const j of JOSA) if (w.length > j.length && w.endsWith(j)) { w = w.slice(0, -j.length); hadJosa = true; break; }
    if (!hadJosa && VERB_END.test(w)) return false;
    if (w.length < 2 || COMMON_NOUN.has(w)) return false;
    const g = grams(w);
    let hit = 0; g.forEach((x) => { if (src.has(x)) hit++; });
    return hit / g.size < 0.5;
  }
  const grounded = (word, src) => !novelNoun(word, src);

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /** text(초안)와 source(내 경험 원문)를 받아, 표시한 HTML과 표시 건수를 돌려준다 */
  function mark(text, source) {
    const src = grams(source);
    let added = 0, puff = 0;
    const lines = String(text || "").split("\n").map((line) => {
      if (!line.trim() || SKIP_LINE.test(line.trim())) return esc(line);
      // 문장 단위로: 원문에 없는 명사가 2개 이상 모인 문장만 '덧붙은 내용'으로 본다 (1개는 자연스러운 바꿔 쓰기일 수 있음)
      return line.split(/(?<=[.!?])\s+/).map((sent) => {
        const words = sent.split(/(\s+)/);
        const novel = words.map((w) => /\S/.test(w) && novelNoun(w, src));
        const nNovel = novel.filter(Boolean).length;
        const isPuff = PUFF.test(sent);
        let html = words.map((w, i) => (nNovel >= 2 && novel[i] ? `<mark class="pf-add" title="내 경험에 없는 말 — 사실인지 확인">${esc(w)}</mark>` : esc(w))).join("");
        if (nNovel >= 2) added++;
        if (isPuff) { puff++; html = `<span class="pf-puff" title="과장·단정 표현 — 실제로 한 일로 바꿔 보세요">${html}</span>`; }
        return html;
      }).join(" ");
    });
    return { html: lines.join("<br>"), added, puff, total: added + puff };
  }

  const api = { mark, grounded };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.IeumReview = api;
})(typeof window !== "undefined" ? window : globalThis);
