"""GET /api/health — 연동 상태 확인 (키 값은 내보내지 않고 설정 여부만)."""
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))  # 공용 모듈 위치

from ai import model_name, provider  # noqa: E402
from common import JsonHandler  # noqa: E402


class handler(JsonHandler):
    def handle_get(self):
        base = os.environ.get("ANTHROPIC_BASE_URL") if provider() == "claude" else os.environ.get("GEMINI_BASE_URL")
        return {"ok": True, "ai": provider() or "not_configured", "model": model_name() if provider() else None,
                "ai_endpoint": urlparse(base).netloc if base else "official",  # 중계 서버 사용 시 호스트 이름만 표시
                "work24": "configured" if os.environ.get("WORK24_KEY") else "synthetic"}
