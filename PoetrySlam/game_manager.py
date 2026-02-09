from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Dict

from game_state import GameEngine


@dataclass
class Room:
    room_id: str
    engine: GameEngine
    clients: Dict[str, str]
    created_at: float


class GameManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}

    def list_rooms(self) -> list[dict]:
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
        room = Room(room_id=room_id, engine=engine, clients={}, created_at=time.time())
        self.rooms[room_id] = room
        return room

    def get_room(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)

    def join_room(self, room_id: str, client_id: str) -> tuple[Room | None, str | None, str | None]:
        room = self.rooms.get(room_id)
        if not room:
            return None, None, "Room not found"
        if client_id in room.clients:
            return room, room.clients[client_id], None
        if room.engine.player_count() >= room.engine.max_players:
            return room, None, "Room is full"
        player_id = room.engine.add_player(kind="human")
        room.clients[client_id] = player_id
        return room, player_id, None
