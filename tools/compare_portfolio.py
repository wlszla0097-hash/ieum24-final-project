"""포트폴리오 수정 전·후 비교 — python3 tools/compare_portfolio.py [--personas P-A02,P-A07] [--repeat 3]

같은 구직자(data/synthetic/seekers_A.json)로 같은 모델·같은 날 다음을 실제 AI로 호출해 나란히 기록한다. (AI 키 필요, .env 사용)
  전: 기준 브랜치(기본 main)의 api/seeker.py  → 1회
  후: 현재 작업 중인 api/seeker.py            → 1회
결과: 표(글자 수·섹션·강점·차단·제외 문장·초) + 전체 본문을 results/portfolio_compare.md 에 저장.
※ 같은 입력도 실행마다 결과가 달라질 수 있어, 저장된 옛 결과(results/export_A.json)가 아니라 오늘 다시 돌린 '전'과 비교한다.
※ points(정리된 활동)는 화면의 AI 정리 결과 대신 합성 데이터의 활동 이름을 쓴다.
--dry-run: AI를 부르지 않고 가짜 응답으로 스크립트만 점검한다.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_module(name: str, source: str):
    mod = types.ModuleType(name)
    mod.__file__ = str(ROOT / "api" / "seeker.py")  # core 폴더를 찾는 경로 계산이 같게
    exec(compile(source, mod.__file__, "exec"), mod.__dict__)
    return mod


def fake_ai(system, user, **k):
    return {"headline": "시험용 한 줄 소개", "summary": "시험용 요약입니다.", "strengths": ["시험 강점"],
            "sections": [{"title": "시험 활동", "body": "시험용 본문입니다."}], "fit": "시험용 직무 연결입니다.", "skills": []}


def run_one(mod, p):
    t0 = time.time()
    try:
        r = mod.portfolio(p)
    except Exception as e:  # ApiError 포함: 실패도 기록
        return {"error": getattr(e, "message", None) or repr(e), "sec": round(time.time() - t0, 1)}
    m = r["meta"]
    doc = r["portfolio"]
    return {"sec": round(time.time() - t0, 1), "chars": m.get("chars", len(doc)), "sections": m.get("section_count", doc.count("\n• ") + doc.startswith("• ")),
            "strengths": m.get("strength_count"), "blocked": m.get("guard_blocked"), "removed": m.get("removed"), "doc": doc, "model": m.get("model")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", default="P-A02,P-A07")
    ap.add_argument("--base-ref", default="main")
    ap.add_argument("--repeat", type=int, default=1, help="같은 조건을 여러 번 돌려 평균을 낸다 (같은 입력도 실행마다 결과가 달라서)")
    ap.add_argument("--out", default=str(ROOT / "results" / "portfolio_compare.md"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    load_env()

    from userinput import parse_seeker, persona_to_form

    old_src = subprocess.run(["git", "show", f"{a.base_ref}:api/seeker.py"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    old, new = load_module("seeker_before", old_src), load_module("seeker_after", (ROOT / "api" / "seeker.py").read_text(encoding="utf-8"))
    if a.dry_run:
        old.generate_json = new.generate_json = fake_ai
        os.environ.setdefault("ANTHROPIC_API_KEY", "dry")
    elif not new.provider():
        sys.exit("AI 키가 없습니다. .env에 키를 넣고 다시 실행하세요. (점검만: --dry-run)")

    personas = {p["id"]: p for p in json.loads((ROOT / "data/synthetic/seekers_A.json").read_text(encoding="utf-8"))}
    rows, texts = [], []
    for pid in [x.strip() for x in a.personas.split(",") if x.strip()]:
        persona = personas[pid]
        form = {**persona_to_form(persona), "agree_privacy": True, "agree_ai": True, "points": [x["name"] for x in persona["activities"]]}
        p = parse_seeker(form)
        runs = [("전", old, None), ("후", new, None)]
        for label, mod, posting in [(f"{l} #{i + 1}" if a.repeat > 1 else l, m, po) for i in range(a.repeat) for l, m, po in runs]:
            res = run_one(mod, p)
            rows.append((pid, persona["alias"], label, res))
            texts.append((pid, persona["alias"], label, res))
            print(f"{pid} {persona['alias']} | {label} | " + (f"{res['chars']}자 섹션{res['sections']} 강점{res['strengths']} 차단{res['blocked']} {res['sec']}초" if "error" not in res else "오류: " + res["error"]))
            if not a.dry_run:
                time.sleep(2)  # 무료 키 한도 보호

    md = ["# 포트폴리오 수정 전·후 비교 (자동 생성)", "", f"- 기준(전): `{a.base_ref}` 의 api/seeker.py / 후: 작업 중인 api/seeker.py",
          f"- 모델: {next((r[3].get('model') for r in rows if r[3].get('model')), '(호출 실패)')} · 구직자 {a.personas}", "",
          "| 구직자 | 실행 | 글자 수 | 섹션 | 강점 | 차단 | 중복·과장·기술명 제외 | 초 |", "|---|---|---|---|---|---|---|---|"]
    for pid, alias, label, r in rows:
        if "error" in r:
            md.append(f"| {pid} {alias} | {label} | 오류: {r['error']} | | | | | {r['sec']} |")
        else:
            rm = r["removed"] or {}
            md.append(f"| {pid} {alias} | {label} | {r['chars']} | {r['sections']} | {r['strengths'] if r['strengths'] is not None else '-'} | {r['blocked']} | "
                      f"{rm.get('duplicate', 0)}·{rm.get('puffery', 0)}·{rm.get('unknown_term', 0)} | {r['sec']} |")
    if a.repeat > 1:
        md += ["", "### 평균 (오류 제외)", "", "| 구직자 | 실행 | 횟수 | 글자 수 | 섹션 | 차단 | 초 |", "|---|---|---|---|---|---|---|"]
        for pid in dict.fromkeys(r[0] for r in rows):
            for kind in ("전", "후"):
                ok_rows = [r[3] for r in rows if r[0] == pid and r[2].startswith(kind) and "error" not in r[3]]
                if ok_rows:
                    avg = lambda k: round(sum((x[k] or 0) for x in ok_rows) / len(ok_rows), 1)
                    md.append(f"| {pid} | {kind} | {len(ok_rows)} | {avg('chars')} | {avg('sections')} | {avg('blocked')} | {avg('sec')} |")
    md += ["", "※ 섹션·강점 수는 '전' 코드에는 meta가 없어 본문에서 센 값입니다(강점은 '-').", "", "## 전체 본문 (어색하거나 원문에 없는 문장은 사람이 직접 확인)", ""]
    for pid, alias, label, r in texts:
        md += [f"### {pid} {alias} — {label}", "", "```", r.get("doc") or r.get("error", ""), "```", ""]
    Path(a.out).write_text("\n".join(md), encoding="utf-8")
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
