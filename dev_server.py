"""로컬 실행용 개발 서버 (Vercel CLI 없이 테스트).

    python dev_server.py        → http://127.0.0.1:3000

- 정적 파일(index.html, css/, js/, images/)을 그대로 제공
- /api/<이름> 요청은 api/<이름>.py 의 handler 클래스로 넘김 (Vercel과 같은 방식)
- .env 파일이 있으면 환경 변수로 읽음
"""
import importlib.util
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = ROOT / "api"
sys.path.insert(0, str(ROOT / "core"))


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


_handlers = {}


def api_handler(name):
    if name not in _handlers:
        path = API / f"{name}.py"
        if not path.exists():
            return None
        spec = importlib.util.spec_from_file_location(f"api_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _handlers[name] = mod.handler
    return _handlers[name]


class Dev(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._dispatch_method("do_GET")
        if any(self.path.startswith(p) for p in ("/api", "/.env", "/.git", "/tests", "/dev_server")):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._dispatch_method("do_POST")
        self.send_error(405)

    def _dispatch_method(self, method):
        name = self.path.split("?")[0].removeprefix("/api/").strip("/")
        h = api_handler(name)
        if not h:
            return self.send_error(404)
        # 이미 읽은 요청을 api/ 의 handler 클래스로 넘겨 처리 (Vercel이 handler를 실행하는 것과 같은 효과)
        self.__class__ = h
        self.close_connection = True
        getattr(h, method)(self)

    def log_message(self, fmt, *args):
        sys.stderr.write("[dev] " + (fmt % args) + "\n")


if __name__ == "__main__":
    load_env()
    port = int(os.environ.get("PORT", 3000))
    print(f"지원사업 이음 AI 로컬 서버: http://127.0.0.1:{port}  (종료: Ctrl+C)")
    ThreadingHTTPServer(("127.0.0.1", port), Dev).serve_forever()
