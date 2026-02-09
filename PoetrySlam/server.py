from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from game_manager import GameManager

WEB_DIR = Path(__file__).parent / "web"

MANAGER = GameManager()


def _get_client_id(data: dict, qs: dict) -> str | None:
    cid = data.get("client_id") if isinstance(data, dict) else None
    if cid:
        return str(cid)
    if qs:
        return (qs.get("client_id") or [None])[0]
    return None


def _get_room_id(data: dict, qs: dict) -> str | None:
    rid = data.get("room_id") if isinstance(data, dict) else None
    if rid:
        return str(rid)
    if qs:
        return (qs.get("room_id") or [None])[0]
    return None


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
            room_id = _get_room_id({}, qs)
            client_id = _get_client_id({}, qs)
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            room.engine.process_timers(difficulty)
            player_id = room.clients.get(client_id or "", None)
            self._send_json(room.engine.payload(self_id=player_id))
            return
        if path == "/api/rooms":
            self._send_json({"rooms": MANAGER.list_rooms()})
            return
        if path == "/api/rhyme_attempts":
            qs = parse_qs(parsed.query)
            room_id = _get_room_id({}, qs)
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(room.engine.rhyme_attempts_payload())
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
            room_id = _get_room_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            room.engine.new_game()
            client_id = _get_client_id(data, {})
            player_id = room.clients.get(client_id or "", None)
            self._send_json(room.engine.payload(self_id=player_id))
            return
        if self.path == "/api/config":
            room_id = _get_room_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            bot_count = data.get("bot_count") if isinstance(data, dict) else None
            if bot_count is not None:
                room.engine.set_bot_count(bot_count)
            client_id = _get_client_id(data, {})
            player_id = room.clients.get(client_id or "", None)
            self._send_json(room.engine.payload(self_id=player_id))
            return
        if self.path == "/api/guess":
            room_id = _get_room_id(data, {})
            client_id = _get_client_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            player_id = room.clients.get(client_id or "", None)
            if not player_id:
                self._send_json({"error": "Not in room"}, status=HTTPStatus.BAD_REQUEST)
                return
            room.engine.handle_guess(data, actor=player_id)
            self._send_json(room.engine.payload(self_id=player_id))
            return
        if self.path == "/api/bot_commit":
            room_id = _get_room_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            room.engine.handle_bot_commit()
            self._send_json(room.engine.payload())
            return
        if self.path == "/api/pause":
            room_id = _get_room_id(data, {})
            client_id = _get_client_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            room.engine.toggle_pause()
            player_id = room.clients.get(client_id or "", None)
            self._send_json(room.engine.payload(self_id=player_id))
            return
        if self.path == "/api/confirm_rhyme":
            prompt = (data.get("prompt") or "").strip()
            guess = (data.get("guess") or "").strip()
            accepted = bool(data.get("accepted"))
            room_id = _get_room_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            if prompt and guess:
                room.engine.confirm_rhyme_attempt(prompt, guess, accepted)
            self._send_json(room.engine.rhyme_attempts_payload())
            return
        if self.path == "/api/rooms/create":
            bot_count = data.get("bot_count") if isinstance(data, dict) else 1
            client_id = _get_client_id(data, {})
            if not client_id:
                self._send_text("Missing client_id", status=HTTPStatus.BAD_REQUEST)
                return
            room = MANAGER.create_room(bot_count=bot_count)
            _, player_id, _ = MANAGER.join_room(room.room_id, client_id)
            self._send_json(
                {
                    "room_id": room.room_id,
                    "player_id": player_id,
                    "state": room.engine.payload(self_id=player_id),
                }
            )
            return
        if self.path == "/api/rooms/join":
            room_id = _get_room_id(data, {})
            client_id = _get_client_id(data, {})
            if not room_id or not client_id:
                self._send_text("Missing room_id or client_id", status=HTTPStatus.BAD_REQUEST)
                return
            room, player_id, err = MANAGER.join_room(room_id, client_id)
            if err:
                self._send_json({"error": err}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                {
                    "room_id": room.room_id,
                    "player_id": player_id,
                    "state": room.engine.payload(self_id=player_id),
                }
            )
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
