"""Card image cache: one image per Scryfall card id, resumable.

Images come from the cards.scryfall.io CDN, which Scryfall documents as
rate-limit-free; we still keep default concurrency modest. Failures are
counted, not swallowed, so a partial build can be re-run to fill gaps.

The index uses full-card images ("small", ~10 KB each: plenty for a 16x16
hash); every CDN version shares one path, so URLs are derived from the
stored art_crop URI.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Any

import httpx

from calabria.scryfall.bulk import USER_AGENT

_IMG_FORMAT = "jpg"
IMAGE_VERSIONS = ("small", "normal", "large", "png", "art_crop", "border_crop")


def image_url(art_crop_uri: str, version: str = "normal") -> str:
    """Scryfall CDN paths differ only by the version segment."""
    if version not in IMAGE_VERSIONS:
        raise ValueError(f"unknown image version {version!r}")
    return art_crop_uri.replace("/art_crop/", f"/{version}/", 1)


def card_cache_path(cache_dir: Path, card_id: str) -> Path:
    return cache_dir / card_id[:2] / f"{card_id}.{_IMG_FORMAT}"


def needs_download(path: Path) -> bool:
    return not path.exists() or path.stat().st_size == 0


def download_image(uri: str, dest: Path, *, client: httpx.Client) -> Path:
    response = client.get(uri, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    return dest


def ensure_card_images(
    rows: list[dict[str, Any]],
    cache_dir: Path,
    *,
    client: httpx.Client,
    limit: int | None = None,
    concurrency: int = 8,
    version: str = "small",
) -> dict[str, int]:
    """Download `version` images for rows missing from the cache. Returns stats.

    `limit` caps the number of *downloads* (already-cached entries don't count).
    """
    targets: list[tuple[str, Path]] = []
    cached = 0
    for row in rows:
        path = card_cache_path(cache_dir, row["card_id"])
        if needs_download(path):
            if limit is not None and len(targets) >= limit:
                break
            targets.append((image_url(row["art_crop_uri"], version), path))
        else:
            cached += 1

    stats = {"downloaded": 0, "cached": cached, "failed": 0}

    def work(job: tuple[str, Path]) -> bool:
        uri, dest = job
        try:
            download_image(uri, dest, client=client)
            return dest.exists()
        except httpx.HTTPError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for ok in pool.map(work, targets):
            stats["downloaded" if ok else "failed"] += 1

    return stats
