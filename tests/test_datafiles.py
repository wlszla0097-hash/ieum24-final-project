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
