"""Perceptual hashing for card identification.

dHash (difference hash) over grayscale: small resize to 9x8, one bit per
horizontal difference. Fast to compute per frame and matches well enough
to stand in for the real embedding index until milestone 1 wires up the
full Scryfall art index (then: FAISS or sqlite-vec for ~100k vectors).
"""

from __future__ import annotations

import cv2
import numpy as np

HASH_BITS = 64  # 8x8 differences packed into 8 byte-size rows


def dhash(gray: np.ndarray) -> bytes:
    """dHash an image. Accepts 2D (grayscale) or 3D (BGR) arrays."""
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (resized[:, 1:] > resized[:, :-1]).astype(np.uint8)
    return np.packbits(bits).tobytes()


def hamming(a: bytes, b: bytes) -> int:
    """Count differing bits between two hashes."""
    aa = np.frombuffer(a, dtype=np.uint8)
    bb = np.frombuffer(b, dtype=np.uint8)
    if aa.shape != bb.shape:
        raise ValueError("hash length mismatch")
    return int(np.unpackbits(np.bitwise_xor(aa, bb)).sum())
