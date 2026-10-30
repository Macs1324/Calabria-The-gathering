"""Executable spec for the card-detection stage.

Detection segments "not the mat": the mat color is the frame's dominant
color, and anything far enough from it (black borders included) is a card
candidate. Quads come out ordered TL, TR, BR, BL; landscape quads are tapped
cards, and `card_views` yields the upright warps worth hashing.
"""

import cv2
import numpy as np
from cardgen import CARD_H, CARD_W, fake_card, place

from calabria.vision.detect import (
    card_views,
    crop_hash_region,
    find_card_quads,
    order_corners,
    warp_card,
)
from calabria.vision.index import embed_card
from calabria.vision.phash import hamming


def area(quad: np.ndarray) -> float:
    return float(cv2.contourArea(quad.astype(np.float32)))


def test_black_bordered_card_on_dark_mat_is_found_whole():
    frame = place(fake_card(1), height=360)
    (quad,) = find_card_quads(frame)
    expected = 360 * 360 * CARD_W / CARD_H
    assert abs(area(quad) - expected) / expected < 0.08  # the card, not its text box


def test_white_bordered_card_still_found():
    assert len(find_card_quads(place(fake_card(2, border=(240, 240, 235))))) == 1


def test_light_mat_works_too():
    assert len(find_card_quads(place(fake_card(3), mat=(205, 210, 200)))) == 1


def test_rotated_card_is_still_one_quad():
    for angle in (15.0, -35.0, 83.0):
        assert len(find_card_quads(place(fake_card(4), angle=angle))) == 1


def test_several_cards_found_largest_first():
    frame = place(fake_card(5), center=(300, 360), height=300)
    frame = place(fake_card(6), center=(800, 360), height=360, frame=frame)
    quads = find_card_quads(frame)
    assert len(quads) == 2
    assert area(quads[0]) > area(quads[1])


def test_empty_mat_finds_nothing():
    assert find_card_quads(np.full((480, 640, 3), 35, np.uint8)) == []


def test_tiny_blobs_ignored():
    img = np.full((480, 640, 3), 35, np.uint8)
    cv2.rectangle(img, (10, 10), (40, 40), (250, 245, 240), cv2.FILLED)
    assert find_card_quads(img) == []


def test_non_card_shapes_ignored():
    img = np.full((480, 640, 3), 35, np.uint8)
    cv2.rectangle(img, (50, 100), (600, 160), (250, 245, 240), cv2.FILLED)  # a long strip (dice tray, pen)
    assert find_card_quads(img) == []


def test_order_corners_is_clockwise_from_top_left():
    pts = np.float32([[300, 50], [100, 60], [110, 400], [310, 390]])  # shuffled
    tl, tr, br, bl = order_corners(pts)
    assert tl.tolist() == [100, 60]
    assert tr.tolist() == [300, 50]
    assert br.tolist() == [310, 390]
    assert bl.tolist() == [110, 400]


def test_warp_produces_upright_crop():
    frame = place(fake_card(7))
    assert warp_card(frame, find_card_quads(frame)[0]).shape == (CARD_H, CARD_W, 3)


def test_upright_card_views():
    card = fake_card(8)
    frame = place(card, angle=10)
    views, tapped = card_views(frame, find_card_quads(frame)[0])
    assert tapped is False
    assert hamming(embed_card(views[0]), embed_card(card)) <= 40  # of 256 bits


def test_tapped_card_is_flagged_and_one_view_is_upright():
    card = fake_card(9)
    frame = place(card, tapped=True, angle=-5)
    views, tapped = card_views(frame, find_card_quads(frame)[0])
    assert tapped is True
    assert min(hamming(embed_card(v), embed_card(card)) for v in views) <= 40


def test_hash_region_is_card_relative():
    card = fake_card(10)
    region = crop_hash_region(card)
    assert 0.4 * CARD_H < region.shape[0] < 0.6 * CARD_H
    assert region.shape[1] > 0.8 * CARD_W


def busy_mat(seed: int = 0, size: tuple[int, int] = (1280, 720)) -> np.ndarray:
    """An illustrated-playmat stand-in: strong low-frequency color blotches."""
    rng = np.random.default_rng(seed)
    blotches = rng.integers(10, 140, (6, 10, 3)).astype(np.uint8)
    return cv2.resize(blotches, size, interpolation=cv2.INTER_CUBIC)


def test_card_on_busy_mat_is_found():
    frame = place(fake_card(11), frame=busy_mat(), angle=6)
    (quad,) = find_card_quads(frame)
    expected = 360 * 360 * CARD_W / CARD_H
    # The black border can melt into a dark busy mat; then the edge pass finds
    # the inner frame (~86% of the card), which the matcher tolerates. The
    # text box (~30%) is what must never win.
    assert 0.8 < area(quad) / expected < 1.1


def test_detection_paths_do_not_double_count():
    """Color and edge candidates for the same card collapse into one quad."""
    frame = place(fake_card(12), mat=(150, 60, 40))
    assert len(find_card_quads(frame)) == 1
