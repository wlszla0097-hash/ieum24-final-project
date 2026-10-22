"""포트폴리오 검토 표시(js/pfreview.js): 팀원 A 테스트에서 찾은 '원문에 없는 말'이 표시되는지, 원문 그대로의 문장은 표시되지 않는지.
node가 있을 때만 실행 (브라우저 코드와 같은 파일을 그대로 시험)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "js" / "pfreview.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node 없음")


def mark(text, source):
    code = f"const R=require({json.dumps(str(JS))});process.stdout.write(JSON.stringify(R.mark({json.dumps(text)},{json.dumps(source)})))"
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


def test_marks_words_not_in_my_experience():
    src = "사무\n- 사무행정 실무 (엑셀·문서 작성·전산회계 기초) (160시간)\n- 컴퓨터활용능력 2급 필기 합격"
    r = mark("일상적인 전표 확인이나 행정 서류 정리에 활용될 수 있습니다. 기본적인 데이터 입력과 서류 편철 업무부터 맡겠습니다.", src)
    assert r["added"] == 2 and "전표" in r["html"] and "<mark" in r["html"]
    ok = mark("160시간 동안 엑셀과 문서 작성, 전산회계 기초를 배웠습니다.", src)
    assert ok["total"] == 0  # 원문 그대로면 표시 없음


def test_marks_puffery():
    r = mark("실무 중심의 역량을 갖추었습니다.", "엑셀 교육")
    assert r["puff"] == 1 and "pf-puff" in r["html"]
