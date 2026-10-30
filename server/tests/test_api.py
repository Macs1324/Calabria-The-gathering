"""Executable spec for the FastAPI surface: /health, /vision/scan, /rooms.

Isolated apps are built per test via create_app() so test state never leaks.
"""

import base64

import cv2
import numpy as np
from cardgen import fake_card, place
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
    assert client().post("/rooms/nope/events", json={"type": "card_play"}).status_code == 404
    assert client().post("/rooms/nope/join", json={"name": "al"}).status_code == 404


def test_room_play_round_trip():
    c = client()
    room_id = c.post("/rooms").json()["room_id"]
    token = c.post(f"/rooms/{room_id}/join", json={"name": "al"}).json()["token"]
    c.post(f"/rooms/{room_id}/events", headers={"X-Seat-Token": token}, json={"type": "card_play", "payload": {"card_id": "isle"}})
    snap = c.get(f"/rooms/{room_id}").json()
    (entry,) = snap["battlefield"]
    assert entry["card_id"] == "isle"
    assert entry["controller"] == "al"
    assert entry["entry_seq"] == 1
    assert entry["tapped"] is False


def test_invalid_event_400_with_message():
    c = client()
    room_id = c.post("/rooms").json()["room_id"]
    token = c.post(f"/rooms/{room_id}/join", json={"name": "al"}).json()["token"]
    res = c.post(f"/rooms/{room_id}/events", headers={"X-Seat-Token": token}, json={"type": "card_tap", "payload": {"entry": 7, "tapped": True}})
    assert res.status_code == 400
    assert "no battlefield entry" in res.json()["detail"]


def test_scan_empty_index_returns_no_candidates():
    frame = card_frame(synthetic_art(*ART_CARD))
    res = client().post("/vision/scan", json={"image": encode(frame)})
    (cards,) = res.json()["cards"]
    assert cards["candidates"] == []
    assert cards["best"] is None


def seeded_app(names: dict[str, str] | None = None):
    """An app whose index holds fake_card(0..19) as card-0..card-19."""
    app = create_app()
    for seed in range(20):
        app.state.card_index.add(f"card-{seed}", fake_card(seed))
    rows = [{"card_id": cid, "name": name, "set_code": "tst", "art_crop_uri": "u"} for cid, name in (names or {}).items()]
    app.state.meta_store.upsert_many(rows)
    return app


def test_scan_returns_seeded_match():
    res = TestClient(seeded_app()).post("/vision/scan", json={"image": encode(place(fake_card(4), angle=8))})
    card = res.json()["cards"][0]
    assert card["best"]["card_id"] == "card-4"
    assert card["best"]["distance"] <= 40
    assert card["tapped"] is False
    assert len(card["quad"]) == 4


def test_scan_recognizes_tapped_card():
    res = TestClient(seeded_app()).post("/vision/scan", json={"image": encode(place(fake_card(6), tapped=True))})
    card = res.json()["cards"][0]
    assert card["tapped"] is True
    assert card["best"]["card_id"] == "card-6"


def test_scan_single_mode_returns_largest_card_only():
    frame = place(fake_card(1), center=(300, 360), height=250)
    frame = place(fake_card(2), center=(850, 360), height=400, frame=frame)
    c = TestClient(seeded_app())
    assert len(c.post("/vision/scan", json={"image": encode(frame)}).json()["cards"]) == 2
    (card,) = c.post("/vision/scan", json={"image": encode(frame), "mode": "single"}).json()["cards"]
    assert card["best"]["card_id"] == "card-2"


def test_scan_candidates_are_distinct_names():
    # two arts of the same card must not crowd out a third option
    names = {f"card-{i}": f"Card {i}" for i in range(20)}
    names["card-11"] = "Card 4"
    res = TestClient(seeded_app(names)).post("/vision/scan", json={"image": encode(place(fake_card(4)))})
    candidates = res.json()["cards"][0]["candidates"]
    assert len(candidates) == 3
    assert len({c["name"] for c in candidates}) == 3


def test_scan_frame_without_cards_is_empty():
    empty = np.full((640, 960, 3), 35, np.uint8)
    assert client().post("/vision/scan", json={"image": encode(empty)}).json()["cards"] == []


def test_scan_rejects_garbage_image():
    res = client().post("/vision/scan", json={"image": base64.b64encode(b"not an image").decode()})
    assert res.status_code == 400


# --- static web client ---------------------------------------------------------


def test_serves_web_client_when_built(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Calabria: The Gathering</title>")
    (web / "assets" / "app.js").write_text("console.log('hi')")
    c = TestClient(create_app(web_dir=web))
    assert "Calabria: The Gathering" in c.get("/").text
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/health").json() == {"status": "ok"}  # API routes still win


def test_no_web_client_is_fine(tmp_path):
    c = TestClient(create_app(web_dir=tmp_path / "missing"))
    assert c.get("/").status_code == 404
    assert c.get("/health").status_code == 200
