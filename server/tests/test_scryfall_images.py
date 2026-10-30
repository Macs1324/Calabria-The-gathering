"""Spec for the art-crop cache: resumable downloads keyed by Scryfall id."""

import httpx

from calabria.scryfall.images import (
    art_cache_path,
    download_art_crop,
    ensure_art_crops,
    needs_download,
)

TRANSPORT = httpx.MockTransport(lambda request: httpx.Response(200, content=b"fake-jpeg"))


def rows(*ids: str) -> list[dict]:
    return [
        {"card_id": cid, "name": "n", "set_code": "s", "art_crop_uri": f"https://img/{cid}.jpg"}
        for cid in ids
    ]


def test_cache_path_is_sharded():
    path = art_cache_path(cache_dir := __import__("pathlib").Path("/tmp/x"), "abcdef123")
    assert path == cache_dir / "ab" / "abcdef123.jpg"


def test_needs_download_checks_existence_and_size(tmp_path):
    path = art_cache_path(tmp_path, "cardid123")
    assert needs_download(path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    assert needs_download(path)  # empty file is useless
    path.write_bytes(b"data")
    assert not needs_download(path)


def test_download_art_crop_writes_file(tmp_path):
    with httpx.Client(transport=TRANSPORT) as client:
        dest = art_cache_path(tmp_path, "cardid456")
        out = download_art_crop("https://img/cardid456.jpg", dest, client=client)
    assert out.read_bytes() == b"fake-jpeg"


def test_ensure_downloads_and_reports(tmp_path):
    with httpx.Client(transport=TRANSPORT) as client:
        stats = ensure_art_crops(rows("c1a", "c1b"), tmp_path, client=client)
    assert stats == {"downloaded": 2, "cached": 0, "failed": 0}
    assert (tmp_path / "c1" / "c1a.jpg").exists()


def test_ensure_skips_already_cached(tmp_path):
    art_cache_path(tmp_path, "c1a").parent.mkdir(parents=True)
    art_cache_path(tmp_path, "c1a").write_bytes(b"existing")
    with httpx.Client(transport=TRANSPORT) as client:
        stats = ensure_art_crops(rows("c1a", "c1b"), tmp_path, client=client)
    assert stats == {"downloaded": 1, "cached": 1, "failed": 0}


def test_ensure_limits_and_counts_failures(tmp_path):
    def failing(request):
        return httpx.Response(404, content=b"nope")

    with httpx.Client(transport=httpx.MockTransport(failing)) as client:
        stats = ensure_art_crops(rows("x1a", "x1b", "x1c"), tmp_path, client=client, limit=2)
    assert stats == {"downloaded": 0, "cached": 0, "failed": 2}
