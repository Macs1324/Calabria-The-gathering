"""Spec for the card image cache: resumable downloads keyed by Scryfall id.

The index is built from Scryfall's *full-card* images (version "small" by
default); URLs are derived from the stored art_crop URI by swapping the CDN
version segment.
"""

import httpx

from calabria.scryfall.images import (
    card_cache_path,
    download_image,
    ensure_card_images,
    image_url,
    needs_download,
)

TRANSPORT = httpx.MockTransport(lambda request: httpx.Response(200, content=b"fake-jpeg"))


def rows(*ids: str) -> list[dict]:
    return [
        {"card_id": cid, "name": "n", "set_code": "s", "art_crop_uri": f"https://img/{cid}.jpg"}
        for cid in ids
    ]


def test_cache_path_is_sharded():
    path = card_cache_path(cache_dir := __import__("pathlib").Path("/tmp/x"), "abcdef123")
    assert path == cache_dir / "ab" / "abcdef123.jpg"


def test_needs_download_checks_existence_and_size(tmp_path):
    path = card_cache_path(tmp_path, "cardid123")
    assert needs_download(path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    assert needs_download(path)  # empty file is useless
    path.write_bytes(b"data")
    assert not needs_download(path)


def test_download_image_writes_file(tmp_path):
    with httpx.Client(transport=TRANSPORT) as client:
        dest = card_cache_path(tmp_path, "cardid456")
        out = download_image("https://img/cardid456.jpg", dest, client=client)
    assert out.read_bytes() == b"fake-jpeg"


def test_ensure_downloads_and_reports(tmp_path):
    with httpx.Client(transport=TRANSPORT) as client:
        stats = ensure_card_images(rows("c1a", "c1b"), tmp_path, client=client)
    assert stats == {"downloaded": 2, "cached": 0, "failed": 0}
    assert (tmp_path / "c1" / "c1a.jpg").exists()


def test_ensure_skips_already_cached(tmp_path):
    card_cache_path(tmp_path, "c1a").parent.mkdir(parents=True)
    card_cache_path(tmp_path, "c1a").write_bytes(b"existing")
    with httpx.Client(transport=TRANSPORT) as client:
        stats = ensure_card_images(rows("c1a", "c1b"), tmp_path, client=client)
    assert stats == {"downloaded": 1, "cached": 1, "failed": 0}


def test_ensure_limits_and_counts_failures(tmp_path):
    def failing(request):
        return httpx.Response(404, content=b"nope")

    with httpx.Client(transport=httpx.MockTransport(failing)) as client:
        stats = ensure_card_images(rows("x1a", "x1b", "x1c"), tmp_path, client=client, limit=2)
    assert stats == {"downloaded": 0, "cached": 0, "failed": 2}


def test_ensure_fetches_requested_cdn_version(tmp_path):
    seen = []

    def record(request):
        seen.append(str(request.url))
        return httpx.Response(200, content=b"img")

    cdn = [{"card_id": "d1a", "name": "n", "set_code": "s", "art_crop_uri": "https://cards.scryfall.io/art_crop/front/d/1/d1a.jpg?1"}]
    with httpx.Client(transport=httpx.MockTransport(record)) as client:
        ensure_card_images(cdn, tmp_path, client=client)
    assert seen == ["https://cards.scryfall.io/small/front/d/1/d1a.jpg?1"]


def test_image_url_swaps_cdn_version():
    art = "https://cards.scryfall.io/art_crop/front/b/0/b01.jpg?1"
    assert image_url(art, "normal") == "https://cards.scryfall.io/normal/front/b/0/b01.jpg?1"
    assert image_url(art, "small") == "https://cards.scryfall.io/small/front/b/0/b01.jpg?1"
