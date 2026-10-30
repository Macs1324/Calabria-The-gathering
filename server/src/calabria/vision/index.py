"""Card index: nearest-neighbor lookup over card image hashes.

Entries are 256-bit dHashes of a card-relative region (detect.HASH_REGION)
of Scryfall's full-card images; queries hash the same region of a warped
webcam crop. An in-RAM bit matrix with vectorized hamming distance answers a
query over ~55k cards in a few milliseconds. The Embedder seam stays for an
eventual learned embedding (DINOv2/CLIP + FAISS).

Persisted indexes carry a `kind`; one built by an older pipeline loads as
empty (rebuild with `calabria-build-index`) rather than answering garbage.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from calabria.vision.detect import CARD_H, CARD_W, crop_hash_region
from calabria.vision.phash import dhash, hamming  # noqa: F401 (hamming re-export)

INDEX_KIND = "card-dhash16-v2"
HASH_SIZE = 16
_DEFAULT_WIDTH = HASH_SIZE * HASH_SIZE // 8  # 32 bytes

log = logging.getLogger(__name__)


def embed_card(card: np.ndarray) -> bytes:
    """Hash an upright full-card image (any resolution, BGR or grayscale)."""
    if card.ndim == 2:
        card = cv2.cvtColor(card, cv2.COLOR_GRAY2BGR)
    upright = cv2.resize(card, (CARD_W, CARD_H), interpolation=cv2.INTER_AREA)
    return dhash(crop_hash_region(upright), size=HASH_SIZE)


class Embedder:
    """Turns an image into fixed-width bytes. One seam for future embedders."""

    def embed(self, image: np.ndarray) -> bytes:
        raise NotImplementedError


class CardDHashEmbedder(Embedder):
    def embed(self, image: np.ndarray) -> bytes:
        return embed_card(image)


class CardIndex:
    """Add card hashes by id, then search for candidates by bit distance."""

    def __init__(
        self,
        hashes: np.ndarray | None = None,
        ids: list[str] | None = None,
        *,
        width: int = _DEFAULT_WIDTH,
    ):
        self._width = width
        self._hashes = np.zeros((0, width), dtype=np.uint8)
        self._ids: list[str] = []
        if hashes is not None and ids is not None:
            self._extend(hashes, ids)

    def __len__(self) -> int:
        return len(self._ids)

    def _extend(self, hashes: np.ndarray, ids: list[str]) -> None:
        arr = np.asarray(hashes, dtype=np.uint8).reshape(-1, self._width)
        self._hashes = np.vstack([self._hashes, arr])
        self._ids.extend(ids)

    def add(self, card_id: str, image: np.ndarray) -> None:
        self.add_hash(card_id, embed_card(image))

    def add_hash(self, card_id: str, hash_bytes: bytes) -> None:
        arr = np.frombuffer(hash_bytes, dtype=np.uint8)
        if arr.size != self._width:
            raise ValueError(f"expected {self._width * 8}-bit hash, got {arr.size * 8}")
        self._extend(arr.reshape(1, self._width), [card_id])

    def search(self, hash_bytes: bytes, *, k: int = 3) -> list[tuple[str, int]]:
        """Return up to `k` (card_id, distance) pairs, closest first."""
        if not self._ids:
            return []
        query = np.frombuffer(hash_bytes, dtype=np.uint8)
        xor = np.bitwise_xor(self._hashes, query)
        counts = np.unpackbits(xor, axis=1).sum(axis=1)
        k = min(k, len(self._ids))
        top = np.argpartition(counts, k - 1)[:k]
        order = top[np.lexsort((top, counts[top]))]  # by distance, ties by insertion
        return [(self._ids[i], int(counts[i])) for i in order]


def save_index(path: Path, index: CardIndex, *, kind: str = INDEX_KIND) -> None:
    """Persist an index (binary NN-flat: hash rows + ids + kind)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        hashes=index._hashes,
        ids=np.asarray(index._ids, dtype=np.str_),
        kind=np.asarray(kind),
        width=np.asarray(index._width),
    )


def load_index(path: Path) -> CardIndex:
    if not path.exists():
        return CardIndex()
    with np.load(path, allow_pickle=False) as npz:
        kind = str(npz["kind"]) if "kind" in npz.files else "dhash"
        if kind != INDEX_KIND:
            log.warning("card index %s is %r, expected %r: rebuild with calabria-build-index", path, kind, INDEX_KIND)
            return CardIndex()
        width = int(npz["width"])
        index = CardIndex(width=width)
        index._extend(npz["hashes"].astype(np.uint8).reshape(-1, width), [str(i) for i in npz["ids"]])
    return index
