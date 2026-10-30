"""FastAPI surface: health, card scan, and tier-0 room REST endpoints.

Tier-0 rooms live in one process (a dict). The game state itself is already
event-sourced (see calabria.game.room), so swapping this for a durable store
later is a mechanical change. TODO(milestone-4): WebSocket sync per room.

NOTE: request models must live at module scope — with lazy annotations, a
model defined inside a closure resolves as a query parameter instead of a body.

Card data: the index and metadata store load from CALABRIA_DATA_DIR (default
"data" relative to the working directory, built by scripts/build_card_index.py).
Missing artifacts degrade to an empty index.
"""

from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from calabria.game.room import Room
from calabria.scryfall.cards import CardMetaStore
from calabria.vision.build import load_persisted_index
from calabria.vision.detect import crop_art_window, find_card_quads, warp_card
from calabria.vision.index import CardIndex
from calabria.vision.phash import dhash


class ScanRequest(BaseModel):
    image: str = Field(description="base64-encoded PNG/JPEG frame")


class RoomEvent(BaseModel):
    type: str
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _relative_default_data_dir() -> Path:
    return Path(os.environ.get("CALABRIA_DATA_DIR", "data"))


def create_app(
    *,
    rooms: dict[str, Room] | None = None,
    card_index: CardIndex | None = None,
    meta_store: CardMetaStore | None = None,
    data_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Calabria",
        version="0.1.0",
        description="Camera-driven MTG dueling platform",
    )
    data_dir = data_dir if data_dir is not None else _relative_default_data_dir()
    app.state.rooms = rooms if rooms is not None else {}
    app.state.card_index = card_index if card_index is not None else load_persisted_index(data_dir)
    app.state.meta_store = meta_store if meta_store is not None else CardMetaStore(data_dir / "cards.db")
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
            # Webcam cards wear borders and name bars; hash only the art window
            # so the warp aligns with Scryfall art_crop index entries.
            art = crop_art_window(warp_card(frame, quad))
            hash_bytes = dhash(art)
            candidates = [_describe(app, card_id, distance) for card_id, distance in app.state.card_index.search(hash_bytes, k=3)]
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


def _describe(app: FastAPI, card_id: str, distance: int) -> dict[str, Any]:
    meta = app.state.meta_store.get(card_id)
    return {
        "card_id": card_id,
        "distance": distance,
        "name": meta["name"] if meta else None,
        "set_code": meta["set_code"] if meta else None,
    }


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
