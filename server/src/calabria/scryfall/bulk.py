"""Scryfall bulk-data snapshots: the card index's source of truth.

Scryfall's rate-limit docs mandate bulk files for exactly our workload
("rapidly look up ... or resolve a large number of card images"). We make one
listing request per refresh, download `unique_artwork` (one row per distinct
print artwork), and take art crops from the CDN (which has no rate limit).

See https://scryfall.com/docs/api/bulk-data for the shape. Note the 2026 field
names: entries carry `jsonl_download_uri` and `compressed_size`.
"""

from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

import httpx

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
ARTWORK_BULK_TYPE = "unique_artwork"
USER_AGENT = "Calabria/0.4.0 (https://github.com/macs1324/Calabria)"


@dataclass(frozen=True)
class BulkFileInfo:
    type: str
    download_uri: str
    size_bytes: int
    updated_at: str


def fetch_bulk_listing(*, client: httpx.Client | None = None) -> dict[str, Any]:
    """One listing request (the only api.scryfall.com call per refresh)."""
    owned = client is None
    c = client or httpx.Client()
    try:
        response = c.get(BULK_DATA_URL, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.json()
    finally:
        if owned:
            c.close()


def choose_artwork_file(listing: dict[str, Any]) -> BulkFileInfo:
    """Pick the unique_artwork entry from a bulk-data listing."""
    for entry in listing["data"]:
        if entry["type"] == ARTWORK_BULK_TYPE:
            return BulkFileInfo(
                type=entry["type"],
                download_uri=entry["jsonl_download_uri"],
                size_bytes=entry["compressed_size"],
                updated_at=entry["updated_at"],
            )
    raise KeyError(f"{ARTWORK_BULK_TYPE} not present in bulk-data listing")


def download_bulk_file(
    download_uri: str,
    dest: Path,
    *,
    client: httpx.Client | None = None,
) -> Path:
    """Stream a bulk JSONL file to `dest` (CDN, no API rate limit applies)."""
    owned = client is None
    c = client or httpx.Client()
    try:
        with c.stream("GET", download_uri, headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
    finally:
        if owned:
            c.close()
    return dest


def read_jsonl_entries(path: Path) -> list[dict[str, Any]]:
    """Parse a downloaded bulk file (skipping blank lines).

    Scryfall serves the bulk files gzipped; sniff the magic bytes instead of
    trusting file extensions.
    """
    entries = []
    with path.open("rb") as raw:
        if raw.read(2) == b"\x1f\x8b":
            raw.seek(0)
            with gzip.open(raw, "rb") as inner:
                _parse_lines(inner, entries)
        else:
            raw.seek(0)
            _parse_lines(raw, entries)
    return entries


def _parse_lines(byte_handle: IO[bytes], entries: list[dict[str, Any]]) -> None:
    for line in io.TextIOWrapper(byte_handle, encoding="utf-8"):
        line = line.strip()
        if line:
            entries.append(json.loads(line))
