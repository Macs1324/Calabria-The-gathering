"""FastAPI surface: health, card scan, and tier-0 room REST endpoints.

Rooms live in a RoomStore (one JSON log per room under CALABRIA_DATA_DIR/rooms).
Seat tokens identify players: REST calls send `X-Seat-Token`, WebSockets pass
`?token=`. Every change is broadcast as a full "view" to the room's sockets —
rooms are small, so clients just re-render instead of patching.

NOTE: request models must live at module scope — with lazy annotations, a
model defined inside a closure resolves as a query parameter instead of a body.

Card data: the index and metadata store load from CALABRIA_DATA_DIR (default
"data" relative to the working directory, built by `calabria-build-index`).
Missing artifacts degrade to an empty index.

The web client (app/ `pnpm build`) is served at / when CALABRIA_WEB_DIR
(default "../app/dist") holds an index.html: friends just open the URL.
"""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from calabria.game.room import Room
from calabria.game.store import RoomStore
from calabria.scryfall.cards import CardMetaStore
from calabria.scryfall.images import IMAGE_VERSIONS, image_url
from calabria.scryfall.search import CardSearch
from calabria.vision.build import load_persisted_index
from calabria.vision.index import CardIndex
from calabria.vision.scan import scan_frame


class ScanRequest(BaseModel):
    image: str = Field(description="base64-encoded PNG/JPEG frame")
    mode: Literal["all", "single"] = Field(
        default="all", description="'single': only the largest card (hold-it-up-to-the-camera scans)"
    )


class RoomEvent(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class JoinRequest(BaseModel):
    name: str
    token: str | None = None


LOG_TAIL = 200  # events sent with each view; the full log stays on the server


def _relative_default_data_dir() -> Path:
    return Path(os.environ.get("CALABRIA_DATA_DIR", "data"))


def _default_web_dir() -> Path:
    # Quickstart runs from server/, next to the client's build output.
    return Path(os.environ.get("CALABRIA_WEB_DIR", "../app/dist"))


def create_app(
    *,
    room_store: RoomStore | None = None,
    card_index: CardIndex | None = None,
    meta_store: CardMetaStore | None = None,
    data_dir: Path | None = None,
    web_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Calabria: The Gathering",
        version="0.1.0",
        description="Camera-driven MTG dueling platform",
    )
    data_dir = data_dir if data_dir is not None else _relative_default_data_dir()
    app.state.rooms = room_store if room_store is not None else RoomStore(data_dir / "rooms")
    app.state.hub = Hub()
    app.state.card_index = card_index if card_index is not None else load_persisted_index(data_dir)
    app.state.meta_store = meta_store if meta_store is not None else CardMetaStore(data_dir / "cards.db")
    app.state.card_search = CardSearch(
        (row["card_id"], row["name"], row["set_code"]) for row in app.state.meta_store.all()
    )
    _mount_routes(app)
    web_dir = web_dir if web_dir is not None else _default_web_dir()
    if (web_dir / "index.html").exists():
        # Mounted last so API routes win; the client routes with #/CODE, so
        # no SPA fallback is needed.
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def _mount_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/vision/scan")
    def scan(req: ScanRequest) -> dict[str, Any]:
        frame = _decode_image(req.image)
        cards = scan_frame(frame, app.state.card_index, app.state.meta_store.get, single=req.mode == "single")
        return {"cards": cards}

    @app.get("/cards/search")
    def card_search(q: str = "", limit: int = Query(default=8, ge=1, le=50)) -> dict[str, Any]:
        return {"results": app.state.card_search.query(q, limit=limit)}

    @app.get("/cards/{card_id}/image")
    def card_image(card_id: str, version: str = "normal") -> RedirectResponse:
        meta = app.state.meta_store.get(card_id)
        if meta is None:
            raise HTTPException(status_code=404, detail=f"unknown card {card_id!r}")
        if version not in IMAGE_VERSIONS:
            raise HTTPException(status_code=400, detail=f"version must be one of {IMAGE_VERSIONS}")
        # Browsers cache the redirect; the CDN serves the bytes (no image proxying here).
        return RedirectResponse(image_url(meta["art_crop_uri"], version), headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/rooms", status_code=201)
    def create_room() -> dict[str, str]:
        return {"room_id": app.state.rooms.create().id}

    @app.get("/rooms/{room_id}")
    def room_snapshot(room_id: str) -> dict[str, Any]:
        return _room(app, room_id).snapshot()

    @app.post("/rooms/{room_id}/join")
    async def join_room(room_id: str, req: JoinRequest) -> dict[str, str]:
        room = _room(app, room_id)
        try:
            token = app.state.rooms.join(room.id, req.name, token=req.token)
        except ValueError as e:
            status = 409 if "taken" in str(e) else 400
            raise HTTPException(status_code=status, detail=str(e)) from e
        await app.state.hub.broadcast(app, room.id)
        return {"room_id": room.id, "name": req.name.strip(), "token": token}

    @app.post("/rooms/{room_id}/events")
    async def room_event(
        room_id: str, req: RoomEvent, x_seat_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        room = _room(app, room_id)
        payload = _enrich(app, req.type, req.payload)
        snapshot = _guard(lambda: app.state.rooms.apply(room.id, x_seat_token, req.type, payload))
        await app.state.hub.broadcast(app, room.id)
        return snapshot

    @app.post("/rooms/{room_id}/undo")
    async def room_undo(room_id: str, x_seat_token: str | None = Header(default=None)) -> dict[str, Any]:
        room = _room(app, room_id)
        snapshot = _guard(lambda: app.state.rooms.undo(room.id, x_seat_token))
        await app.state.hub.broadcast(app, room.id)
        return snapshot

    @app.websocket("/rooms/{room_id}/ws")
    async def room_ws(ws: WebSocket, room_id: str, token: str | None = None) -> None:
        room = app.state.rooms.get(room_id)
        if room is None:
            await ws.close(code=4404, reason="unknown room")
            return
        await ws.accept()
        you = app.state.rooms.seat_of(room.id, token)
        hub: Hub = app.state.hub
        hub.add(room.id, ws, you)
        try:
            await hub.broadcast(app, room.id)  # newcomer gets a view; others see presence
            while True:
                msg = await ws.receive_json()
                try:
                    _ws_op(app, room.id, token, msg)
                except HTTPException as e:
                    await ws.send_json({"kind": "error", "detail": e.detail})
                    continue
                await hub.broadcast(app, room.id)
        except WebSocketDisconnect:
            pass
        finally:
            hub.remove(room.id, ws)
            await hub.broadcast(app, room.id)


class Hub:
    """Open room sockets and who they belong to (None = spectator)."""

    def __init__(self) -> None:
        self._sockets: dict[str, dict[WebSocket, str | None]] = {}

    def add(self, room_id: str, ws: WebSocket, seat: str | None) -> None:
        self._sockets.setdefault(room_id, {})[ws] = seat

    def remove(self, room_id: str, ws: WebSocket) -> None:
        self._sockets.get(room_id, {}).pop(ws, None)

    def online(self, room_id: str, players: list[str]) -> list[str]:
        seats = set(self._sockets.get(room_id, {}).values())
        return [p for p in players if p in seats]  # seat order, not connect order

    async def broadcast(self, app: FastAPI, room_id: str) -> None:
        sockets = dict(self._sockets.get(room_id, {}))
        if not sockets:
            return
        room = app.state.rooms.get(room_id)
        state = room.snapshot()
        base = {
            "kind": "view",
            "room_id": room_id,
            "state": state,
            "log": [
                {"seq": e.seq, "type": e.type, "actor": e.actor, "payload": e.payload}
                for e in room.events[-LOG_TAIL:]
            ],
            "online": self.online(room_id, state["players"]),
        }
        results = await asyncio.gather(
            *(ws.send_json({**base, "you": seat}) for ws, seat in sockets.items()),
            return_exceptions=True,
        )
        for ws, result in zip(sockets, results, strict=True):
            if isinstance(result, Exception):  # half-closed socket; its handler cleans up too
                self.remove(room_id, ws)


def _ws_op(app: FastAPI, room_id: str, token: str | None, msg: Any) -> None:
    op = msg.get("op") if isinstance(msg, dict) else None
    if op == "event":
        payload = msg.get("payload") or {}
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="payload must be an object")
        event_type = str(msg.get("type"))
        payload = _enrich(app, event_type, payload)
        _guard(lambda: app.state.rooms.apply(room_id, token, event_type, payload))
    elif op == "undo":
        _guard(lambda: app.state.rooms.undo(room_id, token))
    else:
        raise HTTPException(status_code=400, detail=f"unknown op {op!r}")


def _enrich(app: FastAPI, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp the card name onto plays server-side, so logs and boards read well."""
    if event_type != "card_play" or payload.get("name"):
        return payload
    meta = app.state.meta_store.get(str(payload.get("card_id", "")))
    return {**payload, "name": meta["name"]} if meta else payload


def _guard(action: Any) -> Any:
    """Map store errors onto HTTP errors (also reused as WS error messages)."""
    try:
        return action()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
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
