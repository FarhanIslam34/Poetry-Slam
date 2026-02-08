from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from game_state import GameEngine

WEB_DIR = Path(__file__).parent / "web"

ENGINE = GameEngine()


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = HTTPStatus.OK) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        resolved = path.resolve()
        if WEB_DIR not in resolved.parents or not resolved.exists() or not resolved.is_file():
            self._send_text("Not found", status=HTTPStatus.NOT_FOUND)
            return

        content = resolved.read_bytes()
        if resolved.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif resolved.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif resolved.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        else:
            content_type = "application/octet-stream"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._send_file(WEB_DIR / "index.html")
            return
        if path.startswith("/") and not path.startswith("/api/"):
            self._send_file(WEB_DIR / path.lstrip("/"))
            return
        if path == "/api/state":
            qs = parse_qs(parsed.query)
            difficulty = (qs.get("difficulty") or ["Medium"])[0]
            ENGINE.process_timers(difficulty)
            self._send_json(ENGINE.payload())
            return
        if path == "/api/rhyme_attempts":
            self._send_json(ENGINE.rhyme_attempts_payload())
            return

        self._send_text("Not found", status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"

        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._send_text("Invalid JSON", status=HTTPStatus.BAD_REQUEST)
            return

        if self.path == "/api/new":
            bot_count = data.get("bot_count") if isinstance(data, dict) else None
            ENGINE.new_game(bot_count=bot_count)
            self._send_json(ENGINE.payload())
            return
        if self.path == "/api/config":
            bot_count = data.get("bot_count") if isinstance(data, dict) else None
            if bot_count is not None:
                ENGINE.set_bot_count(bot_count)
            self._send_json(ENGINE.payload())
            return
        if self.path == "/api/guess":
            ENGINE.handle_guess(data)
            self._send_json(ENGINE.payload())
            return
        if self.path == "/api/bot_commit":
            ENGINE.handle_bot_commit()
            self._send_json(ENGINE.payload())
            return
        if self.path == "/api/pause":
            ENGINE.toggle_pause()
            self._send_json(ENGINE.payload())
            return
        if self.path == "/api/confirm_rhyme":
            prompt = (data.get("prompt") or "").strip()
            guess = (data.get("guess") or "").strip()
            accepted = bool(data.get("accepted"))
            if prompt and guess:
                ENGINE.confirm_rhyme_attempt(prompt, guess, accepted)
            self._send_json(ENGINE.rhyme_attempts_payload())
            return

        self._send_text("Not found", status=HTTPStatus.NOT_FOUND)


def main() -> None:
    if not WEB_DIR.exists():
        raise SystemExit(f"Missing web assets in {WEB_DIR}")

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Web app running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
