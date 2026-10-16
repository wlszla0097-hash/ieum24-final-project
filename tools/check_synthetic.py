"""합성데이터 자가 점검 — python3 tools/check_synthetic.py

data/synthetic/ 의 파일이 docs/data-spec.md 형식에 맞는지 확인하고,
일부러 넣은 오류 사례를 서비스의 점검 기능이 실제로 잡는지 보여 준다. (AI 호출 없음, 비용 0)
형식 오류가 있으면 종료 코드 1.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

import datafiles as df  # noqa: E402
import labor  # noqa: E402
from claimdocs import check_month  # noqa: E402
from rules import judge, posting_check  # noqa: E402

errors, warns = [], []
err = errors.append
warn = warns.append


def section(title):
    print(f"\n━━ {title}")


def busino_ok(b, where):
    b = df._digits(b)
    if len(b) != 10:
        err(f"{where}: 사업자등록번호는 숫자 10자리여야 함 → '{b}'")
    elif not b.startswith("000"):
        err(f"{where}: 사업자등록번호는 000으로 시작하는 가짜 번호만 사용 → '{b}'")
    return b


def load_json(name):
    if not os.path.exists(df.path(name)):
        return None
    try:
        return df.load_json(name)
    except json.JSONDecodeError as e:
        err(f"{name}: JSON 형식 오류 — {e}")
        return []


# ── 기업 정보 (연번 9) ──
section("연번 9 · 기업 정보 companies.json")
companies = load_json("companies.json")
comp_ids = set()
if companies is None:
    print("  파일 없음 (선택)")
else:
    for i, c in enumerate(companies, 1):
        w = f"companies.json {i}번"
        for k in ("busino", "company", "indTpNm", "region", "insured", "priority", "weekly_hours"):
            if k not in c:
                err(f"{w}: '{k}' 항목 없음")
        b = busino_ok(c.get("busino"), w)
        if b in comp_ids:
            err(f"{w}: 사업자번호 중복 {b}")
        comp_ids.add(b)
        if "(가상)" not in str(c.get("company", "")):
            warn(f"{w}: 회사명에 '(가상)'을 붙여 주세요")
    print(f"  {len(companies)}곳")

# ── 임금체불 조회 (연번 2) ──
section("연번 2 · 임금체불 명단공개 work24_arrears.xml")
if not os.path.exists(df.path("work24_arrears.xml")):
    print("  파일 없음 (선택)")
else:
    try:
        root = ET.parse(df.path("work24_arrears.xml")).getroot()
        rows = [root] if root.tag == "jdgnList" else list(root.iter("jdgnList"))
        for i, r in enumerate(rows, 1):
            w = f"work24_arrears.xml {i}번"
            miss = [t for t in df.ARREARS_TAGS if r.find(t) is None]
            if miss:
                err(f"{w}: 항목 없음 {miss}")
            b = busino_ok(r.findtext("brno"), w)
            if comp_ids and b not in comp_ids:
                err(f"{w}: brno {b} 가 companies.json 에 없음")
        res = df.load_arrears()
        print(f"  {len(rows)}건 · 명단공개 대상 {sum(1 for v in res.values() if v)} · 조회 실패 {sum(1 for v in res.values() if v is None)}")
        for b in sorted(comp_ids - set(res)):
            warn(f"companies.json 의 {b} 에 대한 임금체불 조회 결과가 없음")
    except ET.ParseError as e:
        err(f"work24_arrears.xml: XML 형식 오류 — {e}")

# ── 채용공고 (연번 1) ──
section("연번 1 · 채용정보 work24_postings.xml")
posts = []
if not os.path.exists(df.path("work24_postings.xml")):
    print("  파일 없음 (선택)")
else:
    try:
        root = ET.parse(df.path("work24_postings.xml")).getroot()
        seen = set()
        for i, w_el in enumerate(root.iter("wanted"), 1):
            w = f"work24_postings.xml {i}번"
            miss = [t for t in df.WANTED_TAGS if w_el.find(t) is None]
            if miss:
                err(f"{w}: 항목 없음 {miss}")
            no = (w_el.findtext("wantedAuthNo") or "").strip()
            if no in seen:
                err(f"{w}: 구인인증번호 중복 {no}")
            seen.add(no)
            b = busino_ok(w_el.findtext("busino"), w)
            if comp_ids and b not in comp_ids:
                err(f"{w}: busino {b} 가 companies.json 에 없음 (기업 정보로 연결 불가)")
            if (w_el.findtext("empTpCd") or "").strip() not in ("10", "11", "20", "21"):
                err(f"{w}: empTpCd 는 10·11·20·21 중 하나")
        posts = df.load_postings()
        comp_map = df.load_companies()
        print(f"  {len(posts)}건 — 서비스 점검 결과:")
        for p in posts:
            chk = posting_check(p)
            flags = [f"{x['item']}({x['level']})" for x in chk["items"] if x["level"] in ("미충족", "확인 필요")]
            exp = (comp_map.get(p.get("busino")) or {}).get("expect")
            mark = "" if not exp else (" ✅" if exp == chk["verdict"] else f" ❌ 기대 '{exp}'")
            print(f"   · {p['company']} — {p['title'][:22]} → {chk['verdict']}{mark}" + (f" | {', '.join(flags)}" if flags else ""))
            if exp and exp != chk["verdict"]:
                warn(f"{p['company']}: 기대 '{exp}' 와 공고 점검 결과 '{chk['verdict']}' 가 다름")
    except ET.ParseError as e:
        err(f"work24_postings.xml: XML 형식 오류 — {e}")

# ── 구직자 (연번 4·5) ── 기존 예시 seekers.json + 팀원별 seekers_A.json·seekers_B.json …
section("연번 4·5 · 구직자 seekers.json · seekers_*.json")
seeker_names = df.seeker_files()
if not seeker_names:
    print("  파일 없음 (선택)")
else:
    ref = next((p for p in posts if p.get("emp_type") == "정규직" and str(p.get("region", ""))[:2] in ("서울", "경기", "인천")
                and p.get("priority")), {"region": "서울", "emp_type": "정규직", "priority": True})
    id_owner = {}
    for name in seeker_names:
        seekers = load_json(name) or []
        if not isinstance(seekers, list):
            err(f"{name}: 맨 바깥은 [ ] 목록이어야 함")
            continue
        tag = name[len("seekers_"):-len(".json")] if name.startswith("seekers_") else ""
        print(f"  [{name}] {len(seekers)}명" + ("  ← 아직 비어 있음" if not seekers else ""))
        for i, s in enumerate(seekers, 1):
            w = f"{name} {i}번"
            if not isinstance(s, dict):
                err(f"{w}: {{ }} 묶음이어야 함")
                continue
            for k in ("id", "alias", "age", "label", "programs", "activities", "insurance", "desire"):
                if k not in s:
                    err(f"{w}: '{k}' 항목 없음")
            sid = s.get("id")
            if sid in id_owner:
                err(f"{w}: id '{sid}' 가 {id_owner[sid]} 와 겹침 — id를 바꿔 주세요")
            elif sid:
                id_owner[sid] = name
            if tag and sid and not str(sid).startswith(f"P-{tag}"):
                warn(f"{w}: {name} 의 id는 'P-{tag}01' 처럼 P-{tag} 로 시작하기로 함 → '{sid}'")
            for pr in s.get("programs") or []:
                if pr.get("type") not in ("국민취업지원제도", "청년도전지원사업"):
                    err(f"{w}: programs.type 은 '국민취업지원제도' 또는 '청년도전지원사업'")
            try:
                j = judge(s, ref, True)
                print(f"   · {s.get('alias')} ({s.get('age')}세) → 수도권 정규직 공고 기준 배지 {'대상' if j['eligible'] else '비대상'}"
                      + (f" ({j.get('reason')})" if j.get("reason") else ""))
            except Exception as e:  # noqa: BLE001
                err(f"{w}: 배지 판단 중 오류 — {e!r}")

# ── 근로계약서 (연번 6) ──
section("연번 6 · 근로계약서 contracts.json")
contracts = load_json("contracts.json")
if contracts is None:
    print("  파일 없음 (선택)")
else:
    for i, c in enumerate(contracts, 1):
        res = labor.check(c)
        viol = [r["item"] for r in res if r["level"] == labor.VIOLATION]
        got = labor.VIOLATION if viol else (labor.CHECK if any(r["level"] == labor.CHECK for r in res) else labor.OK)
        mark = "" if not c.get("expect") else (" ✅" if c["expect"] == got else f" ❌ 기대 '{c['expect']}'")
        print(f"   · {c.get('id')} {c.get('note', '')[:24]} → {got}{(' ' + ', '.join(viol)) if viol else ''}{mark}")
        if c.get("expect") and c["expect"] != got:
            warn(f"contracts.json {c.get('id')}: 기대 '{c['expect']}' 와 점검 결과 '{got}' 가 다름")

# ── 급여명세서·이체확인증 (연번 7·8) ──
section("연번 7·8 · 급여명세서·이체확인증 docs_answer.json")
answers = load_json("docs_answer.json")
if answers is None:
    print("  파일 없음 (선택)")
else:
    cases = defaultdict(dict)
    for i, a in enumerate(answers, 1):
        w = f"docs_answer.json {i}번"
        if a.get("kind") not in ("payslip", "transfer"):
            err(f"{w}: kind 는 payslip 또는 transfer")
            continue
        if not a.get("case"):
            err(f"{w}: 같은 달 명세서·이체확인증을 묶는 'case' 값이 없음")
        if a.get("file") and not os.path.exists(df.path(a["file"])):
            err(f"{w}: 이미지 파일 없음 → data/synthetic/{a['file']}")
        cases[a.get("case")][a["kind"]] = a
    for case, pair in cases.items():
        p, t = pair.get("payslip"), pair.get("transfer")
        if not (p and t):
            err(f"docs_answer.json case '{case}': 명세서와 이체확인증이 한 쌍이 아님")
            continue
        res = check_month(p["ym"], {"name": p["name"], "ym": p["ym"], "gross": p["gross"], "net": p["net"]},
                          {"recipient": t["recipient"], "amount": t["amount"], "date": t["date"]},
                          {"worker": p["name"], "weekly_hours": 40, "history": []})
        bad = [x["item"] for x in res["items"] if x["level"] != "일치"]
        exp = p.get("expect")
        mark = "" if not exp else (" ✅" if exp == res["level"] else f" ❌ 기대 '{exp}'")
        print(f"   · {case} → {res['level']}{(' ' + ', '.join(bad)) if bad else ''}{mark}")
        if exp and exp != res["level"]:
            warn(f"docs_answer.json {case}: 기대 '{exp}' 와 점검 결과 '{res['level']}' 가 다름")

# ── 결과 ──
print("\n━━ 결과")
for w in warns:
    print("  ⚠", w)
for e in errors:
    print("  ✖", e)
print(f"  형식 오류 {len(errors)}건 · 확인 필요 {len(warns)}건" + (" — 통과 ✅" if not errors else ""))
sys.exit(1 if errors else 0)
