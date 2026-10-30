"""Executable spec for the card-detection stage.

Classic OpenCV: Canny → contours → quadrilateral → perspective warp.
A synthetic fixture (a white card on a dark mat, various rotations) must
produce one quad per card and an upright crop of the standard size.
"""

import cv2
import numpy as np
import pytest

from calabria.vision.detect import find_card_quads, warp_card

CARD_W, CARD_H = 315, 440  # 63:88 standard MTG card ratio


def mat_with_card(angle: float = 0.0, size: tuple[int, int] = (640, 480)) -> np.ndarray:
    """A dark playmat with one bright card-shaped rectangle, optionally rotated.

    Coordinates are rotated about the image center just like a card would lie
    on a physically rotated mat.
    """
    img = np.full((size[1], size[0], 3), 35, np.uint8)
    rect = np.array(
        [
            [140, 40],
            [140 + CARD_W, 40],
            [140 + CARD_W, 40 + CARD_H],
            [140, 40 + CARD_H],
        ],
        np.float32,
    )
    if angle != 0.0:
        M = cv2.getRotationMatrix2D((size[0] / 2, size[1] / 2), angle, 1.0)
        rect = cv2.transform(rect.reshape(-1, 1, 2), M).reshape(-1, 2)
    cv2.fillPoly(img, [rect.astype(np.int32)], (250, 245, 240))
    return img


def test_finds_upright_card():
    quads = find_card_quads(mat_with_card())
    assert len(quads) == 1
    assert quads[0].shape == (4, 2)


def test_rotated_card_is_still_one_quad():
    assert len(find_card_quads(mat_with_card(angle=15.0))) == 1
    assert len(find_card_quads(mat_with_card(angle=83.0))) == 1


def test_empty_mat_finds_nothing():
    img = np.full((480, 640, 3), 35, np.uint8)
    assert find_card_quads(img) == []


def test_tiny_blobs_ignored():
    img = np.full((480, 640, 3), 35, np.uint8)
    cv2.fillPoly(img, [np.array([[10, 10], [40, 10], [40, 40], [10, 40]], np.int32)], (250, 245, 240))
    assert find_card_quads(img) == []


def test_warp_produces_upright_crop():
    crop = warp_card(mat_with_card(), find_card_quads(mat_with_card())[0])
    assert crop.shape == (CARD_H, CARD_W, 3)


def test_warp_is_angle_invariant():
    """Same card at different rotations should warp to near-identical crops."""
    crops = [warp_card(mat_with_card(a), find_card_quads(mat_with_card(a))[0]) for a in (0.0, 25.0, -40.0)]
    hashes = [cv2.cvtColor(c, cv2.COLOR_BGR2GRAY).mean() for c in crops]
    # Grayscale mean of an identical cropped card must match across a few degrees.
    assert max(hashes) - min(hashes) < pytest.approx(6.0, abs=6.0)
