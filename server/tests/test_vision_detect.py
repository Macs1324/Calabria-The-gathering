"""Executable spec for the card-detection stage.

Classic OpenCV: Canny → contours → quadrilateral → perspective warp.
A synthetic fixture (a white card on a dark mat, various rotations) must
produce one quad per card and an upright crop of the standard size.
"""

import cv2
import numpy as np

from calabria.vision.detect import ART_WINDOW, crop_art_window, find_card_quads, warp_card

CARD_W, CARD_H = 315, 440  # 63:88 standard MTG card ratio


def mat_with_card(angle: float = 0.0, size: tuple[int, int] = (960, 640)) -> np.ndarray:
    """A dark playmat with one bright card-shaped rectangle, optionally rotated.

    Coordinates are rotated about the image center just like a card would lie
    on a physically rotated mat. The canvas is sized so no angle clips the card.
    """
    img = np.full((size[1], size[0], 3), 35, np.uint8)
    rect = np.array(
        [
            [-CARD_W / 2, -CARD_H / 2],
            [CARD_W / 2, -CARD_H / 2],
            [CARD_W / 2, CARD_H / 2],
            [-CARD_W / 2, CARD_H / 2],
        ],
        np.float32,
    ) + np.float32([size[0] / 2, size[1] / 2])
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


def test_crop_art_window_returns_central_inset():
    """The scan flow hashes the art window of a full-card crop, not the border."""
    art = gradient(320, 224, horizontal=True)
    card = card_with_art_frame(art)
    window = crop_art_window(card)
    assert window.shape == art.shape
    # art survives as the exact pixels inside the frame
    assert np.array_equal(window, art)


def gradient(h: int, w: int, horizontal: bool = True) -> np.ndarray:
    axis = np.tile(np.linspace(0, 255, w).astype(np.uint8), (h, 1))
    return axis if horizontal else axis.T


def card_with_art_frame(art: np.ndarray) -> np.ndarray:
    """A full-card-sized canvas whose art window holds `art` (detect.py geometry)."""
    ha, wa = art.shape[:2]
    x0, y0, x1, y1 = ART_WINDOW
    h_card = int(ha / (y1 - y0))
    w_card = int(wa / (x1 - x0))
    card = np.full((h_card, w_card, 3), 235, np.uint8)
    card[int(y0 * h_card) : int(y0 * h_card) + ha, int(x0 * w_card) : int(x0 * w_card) + wa] = art
    return card


def test_warp_is_angle_invariant():
    """Same card at different rotations should warp to near-identical crops."""
    crops = [warp_card(mat_with_card(a), find_card_quads(mat_with_card(a))[0]) for a in (0.0, 25.0, -40.0)]
    hashes = [cv2.cvtColor(c, cv2.COLOR_BGR2GRAY).mean() for c in crops]
    # Grayscale mean of an identical cropped card must match across a few degrees.
    assert max(hashes) - min(hashes) <= 6.0
