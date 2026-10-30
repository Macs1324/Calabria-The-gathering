"""Executable spec for the FastAPI surface: /health, /vision/scan, /rooms.

Isolated apps are built per test via create_app() so test state never leaks.
"""

import base64

import cv2
import numpy as np
from fastapi.testclient import TestClient

from calabria.api.main import create_app


def synthetic_art(h: int, w: int) -> np.ndarray:
    """A deterministic gradient+stripe pattern standing in for unique card art.

    Bright enough (>=130) to survive Otsu against the dark (35) playmat.
    """
    _yy, xx = np.mgrid[0:h, 0:w]
    base = 130 + (xx * 100 // max(w - 1, 1))  # horizontal ramp 130..230
    stripe = np.where((xx // 8) % 2, 20, 0)  # vertical stripes
    return np.clip(base + stripe, 0, 255).astype(np.uint8)


def card_frame(art: np.ndarray, size: tuple[int, int] = (960, 640)) -> np.ndarray:
    frame = np.full((size[1], size[0], 3), 35, np.uint8)
    h, w = art.shape
    x, y = size[0] // 2 - w // 2, size[1] // 2 - h // 2
    frame[y : y + h, x : x + w] = cv2.cvtColor(art, cv2.COLOR_GRAY2BGR)
    return frame


def encode(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf).decode()


def client() -> TestClient:
    return TestClient(create_app())


ART_CARD = (440, 315)  # portrait, like a real MTG card


def test_health():
    assert client().get("/health").json() == {"status": "ok"}


def test_unknown_room_404():
    assert client().get("/rooms/nope").status_code == 404
    assert client().post("/rooms/nope/events", json={"type": "card_play", "actor": "al"}).status_code == 404


def test_room_play_round_trip():
    c = client()
    room_id = c.post("/rooms").json()["room_id"]
    c.post(f"/rooms/{room_id}/events", json={"type": "player_join", "actor": "al"})
    c.post(f"/rooms/{room_id}/events", json={"type": "card_play", "actor": "al", "payload": {"card_id": "isle"}})
    snap = c.get(f"/rooms/{room_id}").json()
    assert snap["battlefield"] == [{"card_id": "isle", "controller": "al", "entry_seq": 1, "tapped": False}]


def test_invalid_event_400_with_message():
    c = client()
    room_id = c.post("/rooms").json()["room_id"]
    res = c.post(f"/rooms/{room_id}/events", json={"type": "card_play", "actor": "ghost", "payload": {"card_id": "x"}})
    assert res.status_code == 400
    assert "not seated" in res.json()["detail"]


def test_scan_empty_index_returns_no_candidates():
    frame = card_frame(synthetic_art(*ART_CARD))
    res = client().post("/vision/scan", json={"image": encode(frame)})
    (cards,) = res.json()["cards"]
    assert cards["candidates"] == []
    assert cards["best"] is None


def test_scan_returns_seeded_match():
    app = create_app()
    art = synthetic_art(*ART_CARD)
    app.state.card_index.add("omu-ingenious", art)
    res = TestClient(app).post("/vision/scan", json={"image": encode(card_frame(art))})
    card = res.json()["cards"][0]
    assert card["best"]["card_id"] == "omu-ingenious"
    assert card["best"]["distance"] <= 24
    assert len(card["quad"]) == 4


def test_scan_frame_without_cards_is_empty():
    empty = np.full((640, 960, 3), 35, np.uint8)
    assert client().post("/vision/scan", json={"image": encode(empty)}).json()["cards"] == []


def test_scan_rejects_garbage_image():
    res = client().post("/vision/scan", json={"image": base64.b64encode(b"not an image").decode()})
    assert res.status_code == 400
