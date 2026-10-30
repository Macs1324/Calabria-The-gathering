"""Executable spec for identification: card dHash + hamming NN index.

Both sides hash the same card-relative region of a *full card* image (query:
the warped webcam crop; index: Scryfall's full-card image), so card frame
styles never need calibrating. 16x16 dHash = 256 bits per card.
"""

from pathlib import Path

import cv2
import numpy as np
from cardgen import fake_card, place

from calabria.vision.detect import card_views, find_card_quads
from calabria.vision.index import INDEX_KIND, CardIndex, embed_card, load_index, save_index
from calabria.vision.phash import dhash, hamming


def gradient_gray(h: int, w: int, vertical: bool = False) -> np.ndarray:
    axis = np.tile(np.linspace(0, 255, w), (h, 1))
    if vertical:
        axis = axis.T
    return axis.astype(np.uint8)


def valid_hash(img: np.ndarray) -> bytes:
    return embed_card(img)


def test_dhash_default_is_8_bytes_and_size_scales():
    assert len(dhash(gradient_gray(200, 200))) == 8
    assert len(dhash(gradient_gray(200, 200), size=16)) == 32


def test_embed_card_is_32_bytes():
    assert len(embed_card(fake_card(1))) == 32


def test_embed_card_ignores_input_resolution():
    card = fake_card(2)
    small = cv2.resize(card, (146, 204), interpolation=cv2.INTER_AREA)  # Scryfall "small"
    assert hamming(embed_card(card), embed_card(small)) <= 24


def test_embed_card_tells_cards_apart():
    assert hamming(embed_card(fake_card(3)), embed_card(fake_card(4))) > 64


def test_webcam_view_matches_reference():
    """End to end: a placed, rotated card finds its own reference first."""
    index = CardIndex()
    for seed in range(40):
        index.add(f"card-{seed}", fake_card(seed))
    frame = place(fake_card(17), angle=12, height=300)
    views, _ = card_views(frame, find_card_quads(frame)[0])
    assert index.search(embed_card(views[0]), k=1)[0][0] == "card-17"


def test_dhash_stable_under_small_rescale():
    img = gradient_gray(200, 200)
    big = cv2.resize(img, (220, 220), interpolation=cv2.INTER_AREA)
    small = cv2.resize(img, (180, 180), interpolation=cv2.INTER_AREA)
    assert hamming(dhash(big), dhash(small)) <= 16


def test_dhash_distinguishes_different_images():
    a = gradient_gray(200, 200)
    b = gradient_gray(200, 200, vertical=True)
    assert hamming(dhash(a), dhash(b)) > 16


def test_index_returns_exact_match_first():
    index = CardIndex()
    index.add_hash("art_creative", valid_hash(fake_card(5)))
    index.add_hash("art_madness", valid_hash(fake_card(6)))
    results = index.search(valid_hash(fake_card(5)), k=2)
    assert results[0][0] == "art_creative"
    assert results[0][1] == 0  # perfect match distance
    assert results[1][0] == "art_madness"


def test_index_respects_k():
    index = CardIndex()
    for i in range(5):
        index.add_hash(f"card_{i}", valid_hash(fake_card(i)))
    assert len(index.search(valid_hash(fake_card(0)), k=3)) == 3


def test_index_empty_search():
    assert CardIndex().search(valid_hash(fake_card(0)), k=3) == []


def test_index_adds_card_image_directly():
    index = CardIndex()
    index.add("card_from_image", fake_card(7))
    results = index.search(valid_hash(fake_card(7)), k=1)
    assert results[0][0] == "card_from_image"


def test_stale_index_kind_loads_empty(tmp_path: Path):
    """An index built by an older pipeline must not be queried with new hashes."""
    index = CardIndex(width=8)
    index.add_hash("old", b"\x00" * 8)
    save_index(tmp_path / "card_index.npz", index, kind="dhash")
    assert len(load_index(tmp_path / "card_index.npz")) == 0


def test_saved_index_records_current_kind(tmp_path: Path):
    index = CardIndex()
    index.add("c", fake_card(8))
    save_index(tmp_path / "card_index.npz", index)
    with np.load(tmp_path / "card_index.npz") as npz:
        assert str(npz["kind"]) == INDEX_KIND
    assert len(load_index(tmp_path / "card_index.npz")) == 1
