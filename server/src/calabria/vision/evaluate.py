"""Measure the scan pipeline: real photos, or synthetic webcam frames.

Real photos (the number that matters): put pictures of physical cards in a
folder, named after the card ("Lightning Bolt.jpg", "Lightning Bolt 2.jpg").
Each photo is scanned in single-card mode and scored by name.

Synthetic frames: real Scryfall full-card images (version "normal", fetched
once into DATA/calib/normal) composited onto a textured mat with rotation,
perspective, glare, blur, noise and JPEG compression, some of them tapped.
Not a substitute for photos — it cannot model sleeves or real lenses — but it
catches regressions and exposes size limits.
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import httpx
import numpy as np

from calabria.scryfall.bulk import USER_AGENT
from calabria.scryfall.cards import CardMetaStore
from calabria.scryfall.images import card_cache_path, download_image, image_url
from calabria.vision.index import CardIndex
from calabria.vision.scan import scan_frame

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SIZE_BUCKETS = ((0, 160), (160, 240), (240, 340), (340, 10_000))  # card height in px


@dataclass
class Sample:
    label: str  # expected card name
    frame: np.ndarray
    bucket: str = "photo"


@dataclass
class Score:
    n: int = 0
    detected: int = 0
    top1: int = 0
    top3: int = 0

    def add(self, detected: bool, names: list[str], expected: str) -> None:
        self.n += 1
        self.detected += detected
        self.top1 += bool(names) and names[0] == expected
        self.top3 += expected in names[:3]

    def line(self) -> str:
        pct = lambda k: f"{100 * k / max(self.n, 1):5.1f}%"
        return f"n={self.n:4}  detected {pct(self.detected)}  name@1 {pct(self.top1)}  name@3 {pct(self.top3)}"


def evaluate(samples: Iterator[Sample], index: CardIndex, store: CardMetaStore, *, show_misses: int = 10) -> dict[str, Score]:
    scores: dict[str, Score] = defaultdict(Score)
    misses: list[str] = []
    for sample in samples:
        cards = scan_frame(sample.frame, index, store.get, single=True)
        names = [c["name"] for c in cards[0]["candidates"]] if cards else []
        for key in ("all", sample.bucket):
            scores[key].add(bool(cards), names, sample.label)
        if (not names or names[0] != sample.label) and len(misses) < show_misses:
            misses.append(f"  expected {sample.label!r}, got {names[:3] or 'no card detected'}")
    if misses:
        print("first misses:")
        print("\n".join(misses))
    return dict(scores)


def photo_samples(folder: Path) -> Iterator[Sample]:
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in PHOTO_SUFFIXES:
            continue
        frame = cv2.imread(str(path))
        if frame is None:
            continue
        label = re.sub(r"\s+\d+$", "", path.stem).strip()  # "Lightning Bolt 2" -> "Lightning Bolt"
        yield Sample(label, frame)


def synthetic_samples(
    data_dir: Path, store: CardMetaStore, index: CardIndex, *, n: int, seed: int = 0, client: httpx.Client | None = None
) -> Iterator[Sample]:
    rng = np.random.default_rng(seed)
    picks = random.Random(seed).sample(index._ids, min(n, len(index)))
    cache = data_dir / "calib" / "normal"
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30)
    for card_id in picks:
        meta = store.get(card_id)
        path = card_cache_path(cache, card_id)
        if meta is None:
            continue
        if not path.exists():
            try:
                download_image(image_url(meta["art_crop_uri"], "normal"), path, client=client)
            except httpx.HTTPError:
                continue
        card = cv2.imread(str(path))
        if card is None:
            continue
        height = float(rng.uniform(120, 480))
        frame = synthetic_frame(card, rng, height=height, tapped=bool(rng.random() < 0.3))
        lo, hi = next(b for b in SIZE_BUCKETS if b[0] <= height < b[1])
        yield Sample(meta["name"], frame, bucket=f"card {lo}-{hi}px" if hi < 10_000 else f"card {lo}px+")


def synthetic_frame(card: np.ndarray, rng: np.random.Generator, *, height: float, tapped: bool) -> np.ndarray:
    W, H = 1280, 720
    base = rng.integers(15, 120, 3).astype(np.float32)
    texture = cv2.resize(rng.normal(0, 12, (9, 16, 3)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    mat = np.clip(base + texture + rng.normal(0, 4, (H, W, 3)), 0, 255).astype(np.uint8)

    if tapped:
        card = cv2.rotate(card, cv2.ROTATE_90_CLOCKWISE)
    h, w = card.shape[:2]
    long_side, short_side = height, height * 63 / 88
    cw, ch = (long_side, short_side) if tapped else (short_side, long_side)
    cx = W / 2 + rng.uniform(-W / 4, W / 4)
    cy = H / 2 + rng.uniform(-H / 6, H / 6)
    angle = np.deg2rad(rng.uniform(-12, 12))
    rect = np.array([[-cw / 2, -ch / 2], [cw / 2, -ch / 2], [cw / 2, ch / 2], [-cw / 2, ch / 2]])
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    dst = rect @ rot.T + [cx, cy] + rng.normal(0, height * 0.015, (4, 2))  # perspective jitter
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), dst.astype(np.float32))
    warped = cv2.warpPerspective(card, M, (W, H))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (W, H))
    out = np.where(mask[..., None] > 127, warped, mat).astype(np.float32)

    if rng.random() < 0.5:  # glare: a soft bright ellipse somewhere on the card
        gx, gy = dst[rng.integers(4)] * 0.6 + np.array([cx, cy]) * 0.4
        yy, xx = np.mgrid[0:H, 0:W]
        r = height * rng.uniform(0.08, 0.2)
        out += 120 * rng.uniform(0.3, 0.8) * np.exp(-(((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * r * r)))[..., None]

    out = out * rng.uniform(0.8, 1.15) + rng.uniform(-20, 20)
    out = cv2.GaussianBlur(np.clip(out, 0, 255).astype(np.uint8), (0, 0), rng.uniform(0.5, 1.4))
    _ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(60, 90))])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)
