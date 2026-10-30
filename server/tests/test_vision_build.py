"""Spec for the offline index build: bulk -> metadata store -> card image cache -> index.

The build is resumable and capped (`limit`), so a real run can be chunked;
the persisted index keeps card dHash (32-byte) rows behind an Embedder seam
for a future embedding swap.
"""

import base64
from pathlib import Path

import cv2
import httpx
import numpy as np
from cardgen import fake_card, place
from fastapi.testclient import TestClient

from calabria.api.main import create_app
from calabria.scryfall.cards import CardMetaStore
from calabria.vision.build import build_card_index, load_persisted_index
from calabria.vision.index import CardIndex, embed_card

ART_BYTES = b"fake-art-jpeg"  # unused placeholder kept for the docstring


def _art_jpeg(variant: int) -> bytes:
    """Small decodable jpg gradients, distinct per variant (deterministic)."""
    img = np.tile(np.linspace(0, 255, 124).astype(np.uint8), (174, 1))
    if variant % 2:
        img = img.T
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


ENTRIES = Path(__file__).parent / "fixtures" / "bulk_entries_sample.jsonl"


def listing() -> dict:
    return {
        "data": [
            {
                "type": "unique_artwork",
                "jsonl_download_uri": "https://c2.example/unique-artwork.jsonl",
                "compressed_size": 1,
                "updated_at": "2026-10-30T00:00:00.000+00:00",
            }
        ]
    }


def make_client(counter: dict[str, int]) -> httpx.Client:
    def responder(request: httpx.Request) -> httpx.Response:
        counter["requests"] = counter.get("requests", 0) + 1
        url = str(request.url)
        if "api.scryfall.com/bulk-data" in url:
            return httpx.Response(200, json=listing())
        if "unique-artwork.jsonl" in url:
            return httpx.Response(200, content=ENTRIES.read_bytes())
        return httpx.Response(200, content=_art_jpeg(counter["requests"]))

    return httpx.Client(transport=httpx.MockTransport(responder))


def synthetic_frame() -> str:
    """fake_card(3) lying slightly rotated on a mat, base64 PNG."""
    ok, buf = cv2.imencode(".png", place(fake_card(3), angle=7))
    assert ok
    return base64.b64encode(buf).decode()


def test_build_from_bulk(tmp_path):
    counter = {"requests": 0}
    client = make_client(counter)

    stats = build_card_index(tmp_path, client=client, limit=3)

    # 2 usable fixture rows (the third has no art), 2 art downloads.
    assert stats["meta_rows"] == 2
    assert stats["downloaded"] == 2
    assert stats["cached"] == 0
    assert stats["failed"] == 0
    assert stats["indexed"] == 2
    assert counter["requests"] == 4  # listing + jsonl + 2 card images

    store = CardMetaStore(tmp_path / "cards.db")
    assert store.count() == 2
    row = store.get("b3c2d1e8-0000-0000-0000-000000000008")
    assert row["name"] == "River"  # front-face name wins over 'River // Rooftop'

    index = load_persisted_index(tmp_path)
    assert isinstance(index, CardIndex)
    assert len(index) == 2


def test_build_is_resumable(tmp_path):
    counter = {"requests": 0}
    build_card_index(tmp_path, client=make_client(counter), limit=3)
    assert counter["requests"] == 4

    stats = build_card_index(tmp_path, client=make_client(counter))
    # second run: listing only — jsonl and art crops already cached on disk;
    # all 2 rows still get indexed from their cached crops
    assert counter["requests"] == 5
    assert stats["cached"] == 2
    assert stats["indexed"] == 2


def test_persisted_roundtrip_exact_match(tmp_path):
    build_card_index(tmp_path, client=make_client({"requests": 0}), limit=3)
    index = load_persisted_index(tmp_path)

    crop_path = (
        tmp_path / "card_cache" / "a2" / "a2b1c0d9-0000-0000-0000-000000000009.jpg"
    )
    query = embed_card(cv2.imread(str(crop_path)))
    results = index.search(query, k=1)
    assert results[0][0] == "a2b1c0d9-0000-0000-0000-000000000009"
    assert results[0][1] == 0


def test_load_persisted_index_missing_dir(tmp_path):
    index = load_persisted_index(tmp_path / "never-built")
    assert isinstance(index, CardIndex)
    assert len(index) == 0
    assert index.search(embed_card(np.zeros((440, 315, 3), np.uint8)), k=3) == []


def test_scan_route_joins_names(tmp_path):
    """The scan endpoint enriches candidates with names from the metadata store."""
    app = create_app(data_dir=tmp_path)
    app.state.card_index.add("sentinel", fake_card(3))
    for seed in range(10, 20):
        app.state.card_index.add(f"other-{seed}", fake_card(seed))
    app.state.meta_store.upsert_many(
        [{"card_id": "sentinel", "name": "Mana Castle", "set_code": "big", "art_crop_uri": "u"}]
    )

    res = TestClient(app).post("/vision/scan", json={"image": synthetic_frame()})
    assert res.status_code == 200
    cards = res.json()["cards"]
    assert cards
    best = cards[0]["best"]
    assert best["card_id"] == "sentinel"
    assert best["name"] == "Mana Castle"
    assert best["distance"] <= 40
