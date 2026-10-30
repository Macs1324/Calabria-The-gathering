"""Card index: nearest-neighbor lookup over card image hashes.

Milestone 0: an in-RAM dHash matrix with vectorized bit distance. Fine for
prototype scale; will be replaced by an embedding index over Scryfall
art crops (DINOv2/CLIP + FAISS) or a sqlite-vec store. TODO(milestone-1).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from calabria.vision.phash import dhash, hamming  # noqa: F401 (hamming re-export)

_DEFAULT_WIDTH = 8  # 64-bit dHash, 8 bytes


class Embedder:
    """Turns an image into fixed-width bytes. One seam for future embedders."""

    def embed(self, image: np.ndarray) -> bytes:
        raise NotImplementedError


class DHashEmbedder(Embedder):
    def embed(self, image: np.ndarray) -> bytes:
        return dhash(image)


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
        self.add_hash(card_id, dhash(image))

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
        order = np.argsort(counts, kind="stable")[:k]
        return [(self._ids[i], int(counts[i])) for i in order]


def save_index(path: Path, index: CardIndex, *, kind: str = "dhash") -> None:
    """Persist an index (binary NN-flat, dHash bytes today; vectors later)."""
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
        width = int(npz["width"]) if "width" in npz.files else _DEFAULT_WIDTH
        index = CardIndex(width=width)
        make_array = npz["hashes"].astype(np.uint8).reshape(-1, width)
        index._extend(make_array, [str(i) for i in npz["ids"]])
    return index
