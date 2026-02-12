from __future__ import annotations

import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict

from game_state import GameEngine


@dataclass
class Room:
    room_id: str
    engine: GameEngine
    clients: Dict[str, str]
    created_at: float
    last_human_action: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class GameManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}
        self._lock = threading.Lock()

    def _prune_locked(self, now: float) -> None:
        expired = [
            room_id
            for room_id, room in self.rooms.items()
            if now - room.last_human_action >= 300
        ]
        for room_id in expired:
            self.rooms.pop(room_id, None)

    def prune_rooms(self) -> None:
        now = time.time()
        with self._lock:
            self._prune_locked(now)

    def list_rooms(self) -> list[dict]:
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            rooms = []
            for room in self.rooms.values():
                rooms.append(
                    {
                        "room_id": room.room_id,
                        "players": room.engine.player_count(),
                        "capacity": room.engine.max_players,
                    }
                )
            return rooms

    def create_room(self, bot_count: int) -> Room:
        room_id = uuid.uuid4().hex[:8]
        engine = GameEngine()
        engine.setup_room(bot_count=bot_count)
        now = time.time()
        room = Room(
            room_id=room_id,
            engine=engine,
            clients={},
            created_at=now,
            last_human_action=now,
        )
        with self._lock:
            self._prune_locked(now)
            self.rooms[room_id] = room
            return room

    def get_room(self, room_id: str) -> Room | None:
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            return self.rooms.get(room_id)

    def join_room(
        self, room_id: str, client_id: str, name: str | None = None
    ) -> tuple[Room | None, str | None, str | None]:
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            room = self.rooms.get(room_id)
            if not room:
                return None, None, "Room not found"
            if client_id in room.clients:
                player_id = room.clients[client_id]
                if name:
                    room.engine.set_player_name(player_id, name)
                return room, player_id, None
            if room.engine.player_count() >= room.engine.max_players:
                return room, None, "Room is full"
            player_id = room.engine.add_player(kind="human", name=name)
            room.clients[client_id] = player_id
            return room, player_id, None

    def drop_room(self, room_id: str) -> None:
        with self._lock:
            self.rooms.pop(room_id, None)
