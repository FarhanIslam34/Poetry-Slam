from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from game_manager import GameManager
import poetry_slam as game

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
        MANAGER.prune_rooms()
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
            with room.lock:
                room.engine.process_timers(difficulty)
                player_id = room.clients.get(client_id or "", None)
                payload = room.engine.payload(self_id=player_id)
            self._send_json(payload)
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
            with room.lock:
                payload = room.engine.rhyme_attempts_payload()
            self._send_json(payload)
            return
        if path == "/api/test_rhyme":
            qs = parse_qs(parsed.query)
            w1 = (qs.get("w1") or [""])[0]
            w2 = (qs.get("w2") or [""])[0]
            found1 = bool(w1 and game.get_prons(w1) or game.custom_rhyme_parts(w1))
            found2 = bool(w2 and game.get_prons(w2) or game.custom_rhyme_parts(w2))
            display1 = game.pronunciation_display(w1) if found1 else ""
            display2 = game.pronunciation_display(w2) if found2 else ""
            rhymes = bool(w1 and w2 and found1 and found2 and game.words_rhyme(w1, w2))
            self._send_json(
                {
                    "word1": w1,
                    "word2": w2,
                    "found1": found1,
                    "found2": found2,
                    "display1": display1,
                    "display2": display2,
                    "rhymes": rhymes,
                }
            )
            return

        self._send_text("Not found", status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        MANAGER.prune_rooms()
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
            with room.lock:
                room.engine.new_game()
                client_id = _get_client_id(data, {})
                player_id = room.clients.get(client_id or "", None)
                payload = room.engine.payload(self_id=player_id)
            self._send_json(payload)
            return
        if self.path == "/api/config":
            room_id = _get_room_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            with room.lock:
                bot_count = data.get("bot_count") if isinstance(data, dict) else None
                if bot_count is not None:
                    room.engine.set_bot_count(bot_count)
                client_id = _get_client_id(data, {})
                player_id = room.clients.get(client_id or "", None)
                payload = room.engine.payload(self_id=player_id)
            self._send_json(payload)
            return
        if self.path == "/api/guess":
            room_id = _get_room_id(data, {})
            client_id = _get_client_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            with room.lock:
                player_id = room.clients.get(client_id or "", None)
                if not player_id:
                    self._send_json({"error": "Not in room"}, status=HTTPStatus.BAD_REQUEST)
                    return
                guess = (data.get("guess") or "").strip()
                if guess:
                    info = room.engine.state.players.get(player_id)
                    if info and info.kind == "human":
                        room.last_human_action = time.time()
                room.engine.handle_guess(data, actor=player_id)
                payload = room.engine.payload(self_id=player_id)
            self._send_json(payload)
            return
        if self.path == "/api/bot_commit":
            room_id = _get_room_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            with room.lock:
                room.engine.handle_bot_commit()
                payload = room.engine.payload()
            self._send_json(payload)
            return
        if self.path == "/api/pause":
            room_id = _get_room_id(data, {})
            client_id = _get_client_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            with room.lock:
                room.engine.toggle_pause()
                player_id = room.clients.get(client_id or "", None)
                payload = room.engine.payload(self_id=player_id)
            self._send_json(payload)
            return
        if self.path == "/api/input":
            room_id = _get_room_id(data, {})
            client_id = _get_client_id(data, {})
            room = MANAGER.get_room(room_id) if room_id else None
            if not room:
                self._send_json({"error": "Room not found"}, status=HTTPStatus.NOT_FOUND)
                return
            with room.lock:
                player_id = room.clients.get(client_id or "", None)
                if not player_id:
                    self._send_json({"error": "Not in room"}, status=HTTPStatus.BAD_REQUEST)
                    return
                text = (data.get("text") or "").strip()
                room.engine.update_live_input(player_id, text)
                payload = room.engine.payload(self_id=player_id)
            self._send_json(payload)
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
            with room.lock:
                if prompt and guess:
                    room.engine.confirm_rhyme_attempt(prompt, guess, accepted)
                payload = room.engine.rhyme_attempts_payload()
            self._send_json(payload)
            return
        if self.path == "/api/rooms/create":
            bot_count = data.get("bot_count") if isinstance(data, dict) else 1
            client_id = _get_client_id(data, {})
            name = (data.get("name") or "").strip() if isinstance(data, dict) else ""
            if not client_id:
                self._send_text("Missing client_id", status=HTTPStatus.BAD_REQUEST)
                return
            room = MANAGER.create_room(bot_count=bot_count)
            _, player_id, err = MANAGER.join_room(room.room_id, client_id, name=name)
            if err:
                MANAGER.drop_room(room.room_id)
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
        if self.path == "/api/rooms/join":
            room_id = _get_room_id(data, {})
            client_id = _get_client_id(data, {})
            name = (data.get("name") or "").strip() if isinstance(data, dict) else ""
            if not room_id or not client_id:
                self._send_text("Missing room_id or client_id", status=HTTPStatus.BAD_REQUEST)
                return
            room, player_id, err = MANAGER.join_room(room_id, client_id, name=name)
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
