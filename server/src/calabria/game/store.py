"""Room store: short room codes, seat tokens, and a JSON log per room on disk.

Identity is server-side: joining hands out a seat token, and every action is
attributed to the token's seat, never to a client-supplied name. Rejoining
with the token reclaims the seat (a dropped connection costs nothing).

Persistence is deliberately dumb: the whole room (seats + event log) is
rewritten atomically after each change. Rooms are a few hundred events at
most, and a full rewrite makes undo trivial. Pass `directory=None` to keep
everything in memory (tests, throwaway servers).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from calabria.game.room import Event, Room

# No 0/O, 1/I: codes get read out loud over voice chat.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 4
log = logging.getLogger(__name__)
MAX_NAME_LEN = 24


class RoomStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory
        self._rooms: dict[str, Room] = {}
        self._seats: dict[str, dict[str, str]] = {}  # room id -> {token: name}
        self._lock = threading.RLock()
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            for path in sorted(directory.glob("*.json")):
                try:
                    self._load(path)
                except (OSError, ValueError, KeyError) as e:  # one bad room must not block startup
                    log.warning("skipping unreadable room file %s: %s", path, e)

    def create(self) -> Room:
        with self._lock:
            code = _new_code()
            while code in self._rooms:
                code = _new_code()
            room = Room(code)
            self._rooms[code] = room
            self._seats[code] = {}
            self._save(code)
            return room

    def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id.upper())

    def join(self, room_id: str, name: str, *, token: str | None = None) -> str:
        """Seat `name` (or reclaim it with `token`) and return the seat token."""
        room = self._require(room_id)
        name = name.strip()
        if not name or len(name) > MAX_NAME_LEN:
            raise ValueError(f"name must be 1-{MAX_NAME_LEN} characters")
        with self._lock:
            seats = self._seats[room.id]
            if token is not None and seats.get(token) == name:
                return token
            if name in seats.values():
                raise ValueError(f"name {name!r} is taken in this room")
            room.apply("player_join", name)
            token = secrets.token_urlsafe(16)
            seats[token] = name
            self._save(room.id)
            return token

    def seat_of(self, room_id: str, token: str | None) -> str | None:
        room = self._require(room_id)
        return self._seats[room.id].get(token) if token else None

    def apply(self, room_id: str, token: str | None, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        room, actor = self._acting(room_id, token)
        if event_type == "player_join":
            raise ValueError("join through the room's join endpoint")
        with self._lock:
            snapshot = room.apply(event_type, actor, payload)
            if event_type == "player_leave":
                self._seats[room.id] = {t: n for t, n in self._seats[room.id].items() if n != actor}
            self._save(room.id)
            return snapshot

    def undo(self, room_id: str, token: str | None) -> dict[str, Any]:
        room, actor = self._acting(room_id, token)
        with self._lock:
            room.undo(actor)
            self._save(room.id)
            return room.snapshot()

    def _acting(self, room_id: str, token: str | None) -> tuple[Room, str]:
        room = self._require(room_id)
        actor = self.seat_of(room.id, token)
        if actor is None:
            raise PermissionError("not seated in this room (missing or unknown seat token)")
        return room, actor

    def _require(self, room_id: str) -> Room:
        room = self.get(room_id)
        if room is None:
            raise KeyError(room_id)
        return room

    def _save(self, room_id: str) -> None:
        if self.directory is None:
            return
        room = self._rooms[room_id]
        doc = {
            "id": room.id,
            "seats": self._seats[room_id],
            "events": [{"type": e.type, "actor": e.actor, "payload": e.payload} for e in room.events],
        }
        path = self.directory / f"{room_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc))
        os.replace(tmp, path)

    def _load(self, path: Path) -> None:
        doc = json.loads(path.read_text())
        events = [Event(e["type"], e["actor"], e.get("payload", {}), seq=i) for i, e in enumerate(doc["events"])]
        room = Room(doc["id"], events)
        self._rooms[room.id] = room
        self._seats[room.id] = dict(doc.get("seats", {}))


def _new_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))
