"""시연 데이터 저장 API (로그인 없이 시연하기 위한 단순 저장소).

GET  /api/store                 → {"mode": "upstash" | "memory" | "off"}
GET  /api/store?col=contracts   → 그 묶음의 저장값 목록
POST /api/store {"op": "put", "col", "id", "value"} | {"op": "del", "col", "id"} | {"op": "reset"}

mode가 "off"(배포 환경에 저장소 미연결)이면 화면은 브라우저(localStorage)에 저장한다.
합성(가상) 데이터만 넣는 시연용이다. 실제 개인정보를 입력하지 않도록 화면에서 안내한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))  # 공용 모듈 위치

import demostore as store  # noqa: E402  (api/store.py 와 이름이 겹치지 않게)
from common import ApiError, JsonHandler, rate_limited, text  # noqa: E402


class handler(JsonHandler):
    def handle_get(self):
        col = self.query().get("col")
        if not col:
            return {"ok": True, "mode": store.mode()}
        if store.mode() == "off":
            return {"ok": True, "mode": "off", "items": []}
        return {"ok": True, "mode": store.mode(), "items": store.list_items(text(col, 20))}

    def handle_post(self):
        b = self.read_json(max_body=220_000)
        op, col = text(b.get("op"), 10), text(b.get("col"), 20)
        if op == "put":
            return {"ok": True, "item": store.put(col, b.get("id"), b.get("value"))}
        if op == "del":
            store.delete(col, b.get("id"))
            return {"ok": True}
        if op == "reset":
            store.reset()
            return {"ok": True}
        raise ApiError(400, "invalid_input", "op는 put·del·reset 중 하나입니다.")

    def do_POST(self):
        # 저장은 AI를 부르지 않으므로 AI 보호용 1분 10회 제한과 따로 센다 (1분 120회)
        if rate_limited(self._client_ip() + ":store", limit=120):
            return self._send(429, {"ok": False, "error": "rate_limited", "message": "요청이 너무 많습니다. 1분 후 다시 시도하세요."})
        self._run(self.handle_post)
