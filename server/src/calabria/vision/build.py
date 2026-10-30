"""Offline card index build: bulk snapshot -> metadata store -> art cache -> index.

Run via `uv run python scripts/build_card_index.py` from server/ (or the
console script once registered). Resumable: the JSONL snapshot and art cache
are shared artifacts; re-runs only make one listing request and rebuild the
persisted index from whatever crops exist on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import httpx

from calabria.scryfall.bulk import (
    choose_artwork_file,
    download_bulk_file,
    fetch_bulk_listing,
    read_jsonl_entries,
)
from calabria.scryfall.cards import CardMetaStore, parse_card_row
from calabria.scryfall.images import art_cache_path, ensure_art_crops
from calabria.vision.index import CardIndex, DHashEmbedder, Embedder, save_index

BULK_FILENAME = "unique_artwork.jsonl"
INDEX_FILENAME = "card_index.npz"


def build_card_index(
    data_dir: Path,
    *,
    client: httpx.Client | None = None,
    limit: int | None = None,
    embedder: Embedder | None = None,
    meta_store: CardMetaStore | None = None,
    concurrency: int = 8,
) -> dict[str, int]:
    data_dir.mkdir(parents=True, exist_ok=True)
    client = client or httpx.Client()
    embedder = embedder or DHashEmbedder()

    bulk_path = data_dir / BULK_FILENAME
    listing = fetch_bulk_listing(client=client)
    info = choose_artwork_file(listing)
    if not bulk_path.exists():
        download_bulk_file(info.download_uri, bulk_path, client=client)

    entries = read_jsonl_entries(bulk_path)
    rows = [row for entry in entries if (row := parse_card_row(entry))]

    store = meta_store or CardMetaStore(data_dir / "cards.db")
    store.upsert_many(rows)

    cache_stats = ensure_art_crops(
        rows, data_dir / "art_cache", client=client, limit=limit, concurrency=concurrency
    )

    index = _index_cached_rows(rows, data_dir / "art_cache", embedder)
    save_index(data_dir / INDEX_FILENAME, index)

    return {"meta_rows": len(rows), **cache_stats, "indexed": len(index)}


def _index_cached_rows(
    rows: list[dict[str, Any]],
    cache_dir: Path,
    embedder: Embedder,
) -> CardIndex:
    index = CardIndex()
    for row in rows:
        crop = cv2.imread(str(art_cache_path(cache_dir, row["card_id"])))
        if crop is None:
            continue
        index.add_hash(row["card_id"], embedder.embed(crop))
    return index


def load_persisted_index(data_dir: Path) -> CardIndex:
    from calabria.vision.index import load_index

    return load_index(data_dir / INDEX_FILENAME)
