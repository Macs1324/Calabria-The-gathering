"""Executable spec for identification: dHash + hamming NN index.

The index is a placeholder until we build the full Scryfall vector index
(milestone 1); matrix dHash search stands in. FAISS swap is projected later.
"""

import cv2
import numpy as np

from calabria.vision.index import CardIndex
from calabria.vision.phash import dhash, hamming


def gradient_gray(h: int, w: int, vertical: bool = False) -> np.ndarray:
    axis = np.tile(np.linspace(0, 255, w), (h, 1))
    if vertical:
        axis = axis.T
    return axis.astype(np.uint8)


def valid_hash(gray: np.ndarray) -> bytes:
    return dhash(gray)


def test_dhash_is_8_bytes():
    assert len(valid_hash(gradient_gray(200, 200))) == 8


def test_dhash_stable_under_small_rescale():
    img = gradient_gray(200, 200)
    big = cv2.resize(img, (220, 220), interpolation=cv2.INTER_AREA)
    small = cv2.resize(img, (180, 180), interpolation=cv2.INTER_AREA)
    assert hamming(valid_hash(big), valid_hash(small)) <= 16


def test_dhash_distinguishes_different_images():
    a = gradient_gray(200, 200)
    b = gradient_gray(200, 200, vertical=True)
    assert hamming(valid_hash(a), valid_hash(b)) > 16


def test_index_returns_exact_match_first():
    index = CardIndex()
    index.add_hash("art_creative", valid_hash(gradient_gray(200, 200)))
    index.add_hash("art_madness", valid_hash(gradient_gray(200, 200, vertical=True)))
    results = index.search(valid_hash(gradient_gray(200, 200)), k=2)
    assert results[0][0] == "art_creative"
    assert results[0][1] == 0  # perfect match distance
    assert results[1][0] == "art_madness"


def test_index_respects_k():
    index = CardIndex()
    for i in range(5):
        index.add_hash(f"card_{i}", valid_hash(gradient_gray(160 + 8 * i, 160)))
    assert len(index.search(valid_hash(gradient_gray(160, 160)), k=3)) == 3


def test_index_empty_search():
    assert CardIndex().search(valid_hash(gradient_gray(100, 100)), k=3) == []


def test_index_adds_greyscale_image_directly():
    index = CardIndex()
    index.add("card_from_image", gradient_gray(200, 200))
    results = index.search(valid_hash(gradient_gray(200, 200)), k=1)
    assert results[0][0] == "card_from_image"
