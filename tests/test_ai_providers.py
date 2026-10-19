"""AI 호출 형식 테스트 — 가짜 AI 서버를 띄워 실제 요청 모양을 확인 (외부 호출·비용 없음)."""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import ai  # noqa: E402

_SRV = [None]  # 지금 떠 있는 가짜 서버 (응답 방식 바꾸기용)
KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "AI_MODEL", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "GEMINI_BASE_URL")


@pytest.fixture()
def fake():
    """요청을 기록하고, 경로별로 각 회사 형식의 응답을 돌려주는 가짜 서버."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
            if self.path.endswith("/chat/completions") and "response_format" in body and _SRV[0].reject_format:
                self.send_response(400); self.send_header("content-length", "2"); self.end_headers(); self.wfile.write(b"{}"); return
            if self.path.endswith("/chat/completions"):
                out = {"choices": [{"message": {"role": "assistant", "content": '{"ok": "openai"}'}}]}
            else:
                out = {"content": [{"type": "text", "text": '{"ok": "claude"}'}]}
            data = json.dumps(out).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    srv.reject_format = False
    _SRV[0] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", seen
    srv.shutdown()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def test_openai_key_selects_openai_with_gateway_url(fake, monkeypatch):
    url, seen = fake
    monkeypatch.setenv("OPENAI_API_KEY", ' "sk-test" ')  # 따옴표·공백 붙여넣기 실수도 허용
    monkeypatch.setenv("OPENAI_BASE_URL", url + "/v1/")  # 끝에 /v1/ 를 붙여도 동작
    assert ai.provider() == "openai" and ai.model_name() == "gpt-4o-mini"
    assert ai.generate_json("시스템", "질문", max_tokens=300) == {"ok": "openai"}
    req = seen[-1]
    assert req["path"] == "/v1/chat/completions" and req["headers"]["authorization"] == "Bearer sk-test"
    b = req["body"]
    assert b["model"] == "gpt-4o-mini" and b["max_tokens"] == 300 and b["response_format"] == {"type": "json_object"}
    assert b["messages"][0] == {"role": "system", "content": "시스템"} and b["messages"][1]["content"] == "질문"


def test_openai_images_pdf_and_new_models(fake, monkeypatch):
    url, seen = fake
    monkeypatch.setenv("OPENAI_API_KEY", "k"); monkeypatch.setenv("OPENAI_BASE_URL", url); monkeypatch.setenv("AI_MODEL", "gpt-5-mini")
    files = [{"media_type": "image/png", "data": "AAAA"}, {"media_type": "application/pdf", "data": "BBBB"}]
    ai.generate_json("s", "서류 판독", file=files)
    b = seen[-1]["body"]
    assert "max_completion_tokens" in b and "max_tokens" not in b and "temperature" not in b  # 최신 모델 규칙
    parts = b["messages"][1]["content"]
    assert parts[0] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    assert parts[1]["type"] == "file" and parts[1]["file"]["file_data"] == "data:application/pdf;base64,BBBB"
    assert parts[2] == {"type": "text", "text": "서류 판독"}


def test_anthropic_still_first_and_unchanged(fake, monkeypatch):
    url, seen = fake
    monkeypatch.setenv("OPENAI_API_KEY", "o"); monkeypatch.setenv("ANTHROPIC_API_KEY", "a"); monkeypatch.setenv("ANTHROPIC_BASE_URL", url + "/v1")
    assert ai.provider() == "claude"
    assert ai.generate_json("s", "u") == {"ok": "claude"}
    assert seen[-1]["path"] == "/v1/messages" and seen[-1]["headers"]["x-api-key"] == "a"


def test_no_key_means_rule_based(monkeypatch):
    assert ai.provider() is None and ai.model_name() == "-"


def test_health_shows_openai_without_key(monkeypatch):
    sys.path.insert(0, str(ROOT / "api"))
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value"); monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example.com/v1")
    import health
    h = health.handler.__new__(health.handler)
    out = h.handle_get()
    assert out["ai"] == "openai" and out["model"] == "gpt-4o-mini" and out["ai_endpoint"] == "gateway.example.com"
    assert "secret-value" not in json.dumps(out)


def test_openai_gateway_without_json_option_retries(fake, monkeypatch):
    url, seen = fake
    monkeypatch.setenv("OPENAI_API_KEY", "k"); monkeypatch.setenv("OPENAI_BASE_URL", url)
    _SRV[0].reject_format = True  # JSON 응답 옵션을 거절하는 중계 서버 흉내
    assert ai.generate_json("s", "u") == {"ok": "openai"}
    assert "response_format" in seen[-2]["body"] and "response_format" not in seen[-1]["body"]


def test_openai_gateway_json_option_rejected_only_once(fake, monkeypatch):
    """교육용 게이트웨이처럼 JSON 옵션을 거절하면, 두 번째 호출부터는 처음부터 옵션 없이 1번만 보낸다."""
    url, seen = fake
    monkeypatch.setenv("OPENAI_API_KEY", "k"); monkeypatch.setenv("OPENAI_BASE_URL", url)
    _SRV[0].reject_format = True
    assert ai.generate_json("s", "u") == {"ok": "openai"}
    n = len(seen)
    assert ai.generate_json("s", "u") == {"ok": "openai"}
    assert len(seen) == n + 1 and "response_format" not in seen[-1]["body"]
