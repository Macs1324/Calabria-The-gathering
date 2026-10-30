"""FastAPI surface: health, card scan, and tier-0 room REST endpoints.

Tier-0 rooms live in one process (a dict). The game state itself is already
event-sourced (see calabria.game.room), so swapping this for a durable store
later is a mechanical change. TODO(milestone-4): WebSocket sync per room.

NOTE: request models must live at module scope — with lazy annotations, a
model defined inside a closure resolves as a query parameter instead of a body.
"""

from __future__ import annotations

import base64
import uuid
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from calabria.game.room import Room
from calabria.vision.detect import find_card_quads, warp_card
from calabria.vision.index import CardIndex
from calabria.vision.phash import dhash


class ScanRequest(BaseModel):
    image: str = Field(description="base64-encoded PNG/JPEG frame")


class RoomEvent(BaseModel):
    type: str
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)


def create_app(*, rooms: dict[str, Room] | None = None, card_index: CardIndex | None = None) -> FastAPI:
    app = FastAPI(
        title="Calabria",
        version="0.1.0",
        description="Camera-driven MTG dueling platform",
    )
    app.state.rooms = rooms if rooms is not None else {}
    app.state.card_index = card_index if card_index is not None else CardIndex()
    _mount_routes(app)
    return app


def _mount_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/vision/scan")
    def scan(req: ScanRequest) -> dict[str, Any]:
        frame = _decode_image(req.image)
        cards = []
        for quad in find_card_quads(frame):
            hash_bytes = dhash(warp_card(frame, quad))
            candidates = [
                {"card_id": card_id, "distance": distance}
                for card_id, distance in app.state.card_index.search(hash_bytes, k=3)
            ]
            cards.append(
                {
                    "quad": np.asarray(quad).round(1).tolist(),
                    "candidates": candidates,
                    "best": candidates[0] if candidates else None,
                }
            )
        return {"cards": cards}

    @app.post("/rooms", status_code=201)
    def create_room() -> dict[str, str]:
        room_id = uuid.uuid4().hex[:12]
        app.state.rooms[room_id] = Room(room_id)
        return {"room_id": room_id}

    @app.get("/rooms/{room_id}")
    def room_snapshot(room_id: str) -> dict[str, Any]:
        return _room(app, room_id).snapshot()

    @app.post("/rooms/{room_id}/events")
    def room_event(room_id: str, req: RoomEvent) -> dict[str, Any]:
        room = _room(app, room_id)
        try:
            return room.apply(req.type, req.actor, req.payload)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e


def _room(app: FastAPI, room_id: str) -> Room:
    room = app.state.rooms.get(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"unknown room {room_id!r}")
    return room


def _decode_image(b64: str) -> np.ndarray:
    try:
        buf = base64.b64decode(b64)
        arr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise ValueError("invalid image payload")
        return arr
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad image: {e}") from e


app = create_app()
