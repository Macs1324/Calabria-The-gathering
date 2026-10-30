"""Art-crop image cache: one image per Scryfall card id, resumable.

Images come from the cards.scryfall.io CDN, which Scryfall documents as
rate-limit-free; we still keep default concurrency modest. Failures are
counted, not swallowed, so a partial build can be re-run to fill gaps.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Any

import httpx

from calabria.scryfall.bulk import USER_AGENT

_IMG_FORMAT = "jpg"


def art_cache_path(cache_dir: Path, card_id: str) -> Path:
    return cache_dir / card_id[:2] / f"{card_id}.{_IMG_FORMAT}"


def needs_download(path: Path) -> bool:
    return not path.exists() or path.stat().st_size == 0


def download_art_crop(uri: str, dest: Path, *, client: httpx.Client) -> Path:
    response = client.get(uri, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    return dest


def ensure_art_crops(
    rows: list[dict[str, Any]],
    cache_dir: Path,
    *,
    client: httpx.Client,
    limit: int | None = None,
    concurrency: int = 8,
) -> dict[str, int]:
    """Download art crops for rows missing from the cache. Returns stats.

    `limit` caps the number of *downloads* (already-cached entries don't count).
    """
    targets: list[tuple[str, Path]] = []
    cached = 0
    for row in rows:
        path = art_cache_path(cache_dir, row["card_id"])
        if needs_download(path):
            if limit is not None and len(targets) >= limit:
                break
            targets.append((row["art_crop_uri"], path))
        else:
            cached += 1

    stats = {"downloaded": 0, "cached": cached, "failed": 0}

    def work(job: tuple[str, Path]) -> bool:
        uri, dest = job
        try:
            download_art_crop(uri, dest, client=client)
            return dest.exists()
        except httpx.HTTPError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for ok in pool.map(work, targets):
            stats["downloaded" if ok else "failed"] += 1

    return stats
