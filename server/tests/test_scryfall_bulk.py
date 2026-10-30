"""Spec for fetching/parsing Scryfall bulk-data listings.

Network calls are injected (httpx client) and replaced in tests; the parsers
and decisions are pure.
"""

import json
from pathlib import Path

import httpx
import pytest

from calabria.scryfall.bulk import (
    ARTWORK_BULK_TYPE,
    BulkFileInfo,
    choose_artwork_file,
    download_bulk_file,
    fetch_bulk_listing,
    read_jsonl_entries,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bulk_listing_sample.json"


def listing() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parse_bulk_listing():
    files = choose_artwork_file(listing())
    assert isinstance(files, BulkFileInfo)
    assert files.type == ARTWORK_BULK_TYPE
    assert files.download_uri == "https://c2.scryfall.com/unique-artwork.jsonl"
    assert files.size_bytes == 38815462


def test_missing_artwork_file_raises():
    payload = {"data": [{"type": "oracle_cards", "jsonl_download_uri": "x", "compressed_size": 1, "updated_at": "y"}]}
    with pytest.raises(KeyError):
        choose_artwork_file(payload)


def test_fetch_bulk_listing_sets_user_agent(monkeypatch):
    captured = {}

    def responder(request):
        captured["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(responder)
    payload = fetch_bulk_listing(client=httpx.Client(transport=transport))
    assert payload == {"data": []}
    assert captured["ua"].startswith("Calabria/")


def test_download_bulk_file_streams_to_disk(tmp_path):
    def responder(request):
        return httpx.Response(200, content=b'{"id": "a"}\n{"id": "b"}\n')

    transport = httpx.MockTransport(responder)
    dest = tmp_path / "unique-artwork.jsonl"
    path = download_bulk_file(
        "https://c2.scryfall.com/unique-artwork.jsonl",
        dest,
        client=httpx.Client(transport=transport),
    )
    assert path == dest
    entries = read_jsonl_entries(dest)
    assert [e["id"] for e in entries] == ["a", "b"]


def test_read_jsonl_entries_skips_blank_lines(tmp_path):
    dest = tmp_path / "bulk.jsonl"
    dest.write_text('{"id": "a"}\n\n{"id": "b"}\n   \n')
    entries = read_jsonl_entries(dest)
    assert len(entries) == 2


def test_read_jsonl_entries_handles_gzip(tmp_path):
    import gzip

    dest = tmp_path / "bulk.jsonl.gz"
    dest.write_bytes(gzip.compress(b'{"id": "a"}\n{"id": "b"}\n'))
    entries = read_jsonl_entries(dest)
    assert [e["id"] for e in entries] == ["a", "b"]
