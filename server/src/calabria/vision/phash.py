"""Perceptual hashing for card identification.

dHash (difference hash) over grayscale: resize to (size+1) x size, one bit
per horizontal difference. size=8 gives 64 bits; card identification uses
size=16 (256 bits), which separates ~55k full-card references comfortably.
"""

from __future__ import annotations

import cv2
import numpy as np


def dhash(gray: np.ndarray, size: int = 8) -> bytes:
    """dHash an image into size*size bits. Accepts 2D (grayscale) or 3D (BGR) arrays."""
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (resized[:, 1:] > resized[:, :-1]).astype(np.uint8)
    return np.packbits(bits).tobytes()


def hamming(a: bytes, b: bytes) -> int:
    """Count differing bits between two hashes."""
    aa = np.frombuffer(a, dtype=np.uint8)
    bb = np.frombuffer(b, dtype=np.uint8)
    if aa.shape != bb.shape:
        raise ValueError("hash length mismatch")
    return int(np.unpackbits(np.bitwise_xor(aa, bb)).sum())
