"""Card metadata store backed by SQLite + bulk-row parsing.

The store deliberately mirrors only what identification needs: id, name,
set, and the CDN art_crop URL. Gameplay rules text is not our concern yet;
add columns when a feature asks for them (keep this lean).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    card_id      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    set_code     TEXT NOT NULL,
    art_crop_uri TEXT NOT NULL
);
"""

_ROW_FIELDS = ("card_id", "name", "set_code", "art_crop_uri")


class CardMetaStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connect()

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads during build
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert_many(self, rows: list[dict[str, Any]]) -> None:
        with self._conn:
            self._conn.executemany(
                "INSERT INTO cards (card_id, name, set_code, art_crop_uri) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(card_id) DO UPDATE SET "
                "name=excluded.name, set_code=excluded.set_code, art_crop_uri=excluded.art_crop_uri",
                [(r["card_id"], r["name"], r["set_code"], r["art_crop_uri"]) for r in rows],
            )

    def get(self, card_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        return dict(row) if row else None

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0])

    def all(self) -> Iterator[dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM cards ORDER BY card_id")
        while row := cursor.fetchone():
            yield dict(row)


def parse_card_row(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Map a unique_artwork bulk entry to a store row, or None if unusable.

    Double-faced cards carry their art inside `card_faces`; the *front* face is
    what a camera sees while the card is face-up in play.
    """
    image_uris = entry.get("image_uris")
    name, art = entry.get("name"), (image_uris or {}).get("art_crop")
    if not art:
        # Double-faced cards: the *front* face is what a camera sees face-up;
        # use its standalone name and art.
        front = (entry.get("card_faces") or [{}])[0]
        art = (front.get("image_uris") or {}).get("art_crop")
        name = front.get("name", name)
    if not art or not name:
        return None
    return {
        "card_id": entry["id"],
        "name": name,
        "set_code": entry.get("set", ""),
        "art_crop_uri": art,
    }
