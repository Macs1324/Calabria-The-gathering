"""Card index: nearest-neighbor lookup over card image hashes.

Milestone 0: an in-RAM dHash matrix with vectorized bit distance. Fine for
prototype scale; will be replaced by an embedding index over Scryfall
art crops (DINOv2/CLIP + FAISS) or a sqlite-vec store. TODO(milestone-1).
"""

from __future__ import annotations

import numpy as np

from calabria.vision.phash import HASH_BITS, dhash, hamming

_HASH_BYTES = 8  # 64 bits


class CardIndex:
    """Add card crops by id, then search for candidates by hash distance."""

    def __init__(self) -> None:
        self._hashes = np.zeros((0, _HASH_BYTES), dtype=np.uint8)
        self._ids: list[str] = []

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, card_id: str, image: np.ndarray) -> None:
        """Hash a card image (gray or BGR ndarray) and index it."""
        self.add_hash(card_id, dhash(image))

    def add_hash(self, card_id: str, hash_bytes: bytes) -> None:
        if len(hash_bytes) != _HASH_BYTES:
            raise ValueError(f"expected {HASH_BITS}-bit hash ({_HASH_BYTES} bytes), got {len(hash_bytes)}")
        self._ids.append(card_id)
        self._hashes = np.vstack([self._hashes, np.frombuffer(hash_bytes, dtype=np.uint8)])

    def search(self, hash_bytes: bytes, *, k: int = 3) -> list[tuple[str, int]]:
        """Return up to `k` (card_id, hamming_distance) pairs, closest first."""
        if not self._ids:
            return []
        query = np.frombuffer(hash_bytes, dtype=np.uint8)
        # Vectorized hamming: XOR rows, then count set bits row-wise.
        xor = np.bitwise_xor(self._hashes, query)
        counts = np.unpackbits(xor, axis=1).sum(axis=1)
        order = np.argsort(counts, kind="stable")[:k]
        return [(self._ids[i], int(counts[i])) for i in order]


__all__ = ["CardIndex", "hamming"]
