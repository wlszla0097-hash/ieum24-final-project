"""data/synthetic 파일 읽기와 자가 점검 도구 테스트."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import datafiles as df  # noqa: E402


def test_postings_file_uses_api_format_and_links_company():
    posts = df.load_postings()
    assert posts, "예시 공고 파일이 있어야 함"
    p = next(x for x in posts if x["busino"] == "0008100012")
    assert p["id"].startswith("W24-") and p["emp_type"] == "정규직" and p["wage"] == 2800000
    assert p["insured"] == 18 and p["priority"] is True and p["arrears"] is False and p["close"] == "2026-12-31"
    failed = next(x for x in posts if x["busino"] == "0008100023")
    assert failed["arrears"] is None  # 조회 실패는 '확인 필요'로 남김


def test_live_and_file_share_parser():
    import work24
    xml = (df.DATA_DIR + "/work24_postings.xml")
    with open(xml, "rb") as f:
        assert [p["id"] for p in work24._parse(f.read())] == [p["id"] for p in df.parse_wanted(open(xml, "rb").read())]


def test_checker_passes_on_examples():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_synthetic.py")], capture_output=True, text=True,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_company_lookup_filters_excluded_and_arrears():
    sys.path.insert(0, str(ROOT / "api"))
    from rules import posting_check
    from userinput import parse_posting
    base = {"sido": "서울", "sigungu": "강남구", "title": "매장 관리 직원", "job": "매장 관리", "emp_type": "정규직", "wage": 2500000,
            "weekly_hours": 40, "priority": "모름"}
    cases = {"000-81-00089": "업종", "0008100112": "임금체불 명단공개", "0008100134": "고액·상습 체납"}
    for b, item in cases.items():
        post = parse_posting({**base, "busino": b})
        chk = posting_check(post)
        assert chk["verdict"] == "연계 어려움", (b, chk)
        assert any(i["item"] == item and i["level"] == "미충족" for i in chk["items"]), (b, chk["items"])
    ok = posting_check(parse_posting({**base, "busino": "0008100012"}))
    assert not any(i["level"] == "미충족" for i in ok["items"])
    unknown = parse_posting({**base, "busino": "0009999999"})
    assert unknown["lookup"].startswith("등록되지 않은")


def test_hiredoc_reads_and_cross_checks():
    import base64
    sys.path.insert(0, str(ROOT / "api"))
    import certificate as c
    f = {"media_type": "image/png", "data": base64.b64encode(b"\x89PNG" + b"x" * 10).decode()}
    truth = {"contract": {"worker": "김하늘", "employment_type": "정규직", "start_date": "2026-03-03", "end_date": "", "base_wage": "2500000",
                          "wage_type": "월급", "weekly_hours": "40", "daily_hours": "8", "break_minutes": "30",
                          "has_holiday": True, "has_leave": True, "has_place": True, "has_job": True, "has_payday": False},
             "bizreg": {"busino": "000-81-00112", "company": "한결전자(가상)", "ceo": "", "industry": "제조업 전자부품", "opened": "2012-07-01", "doc_type": "사업자등록증"}}
    r = c.hiredoc({"files": {"contract": f, "bizreg": f}, "sample_truth": truth, "worker": "김하늘",
                   "posting": {"wage": 2600000, "emp_type": "정규직", "region": "경북 구미시", "busino": "0008100112", "weekly_hours": 40}})
    items = {i["item"]: i["level"] for i in r["items"]}
    assert r["level"] == "위반 의심"
    assert items["계약서 · 휴게시간"] == "위반 의심"
    assert items["계약서 · 필수 기재사항"] == "확인 필요"
    assert items["공고 ↔ 계약서 임금"] == "확인 필요"
    assert items["사업자등록증 · 임금체불 명단공개"] == "미충족"
    assert "사업자등록증 · 업종" in items and items["사업자등록증 · 업종"] == "충족"  # 업태·종목 단어가 겹치면 불일치 아님
    assert r["bizreg"]["busino"] == "0008100112" and "ceo" in r["bizreg"]


def test_seekers_split_files_merge(tmp_path, monkeypatch):
    """팀원별 파일(seekers_A·B)을 합쳐 읽고, 같은 id는 한 번만, 형식이 깨진 파일은 건너뛴다."""
    import json
    one = lambda i, a: {"id": i, "alias": a, "age": 25}  # noqa: E731
    (tmp_path / "seekers.json").write_text(json.dumps([one("P-S01", "예시")]), encoding="utf-8")
    (tmp_path / "seekers_A.json").write_text(json.dumps([one("P-A01", "가"), one("P-S01", "중복")]), encoding="utf-8")
    (tmp_path / "seekers_B.json").write_text(json.dumps([one("P-B01", "나")]), encoding="utf-8")
    (tmp_path / "seekers_C.json").write_text("[ {깨진 파일", encoding="utf-8")
    monkeypatch.setattr(df, "DATA_DIR", str(tmp_path))
    assert df.seeker_files() == ["seekers.json", "seekers_A.json", "seekers_B.json", "seekers_C.json"]
    got = df.load_seekers()
    assert [p["id"] for p in got] == ["P-S01", "P-A01", "P-B01"]
    assert got[0]["alias"] == "예시"


def test_member_seeker_files_exist_and_are_lists():
    import json
    for name in ("seekers_A.json", "seekers_B.json"):
        assert isinstance(json.loads(Path(df.path(name)).read_text(encoding="utf-8")), list)
