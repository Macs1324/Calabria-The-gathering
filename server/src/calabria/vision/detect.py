"""Locate playing cards in a frame and warp them into upright crops.

Stage 0 detector, intentionally bias-light: cards are bright blobs on a dark
mat, so Otsu threshold + quadrilateral contours needs no training data and
works on tidy playmats with half-decent lighting. Edge-based detectors (Canny)
are notoriously corner-brittle on solid fills — avoided here.

Failure modes to revisit with real frames (glare, sleeves, light mats) map to
the planned upgrade: a YOLO-nano detector trained on synthetic composites
(see docs/architecture.md).

Crops are 63:88 (standard MTG card aspect); the fixed output size keeps
hashes comparable across frames.
"""

from __future__ import annotations

import cv2
import numpy as np

CARD_W, CARD_H = 315, 440  # 63:88 standard MTG card ratio
_MIN_AREA_RATIO = 0.02  # cards smaller than this are noise, not cards


def find_card_quads(
    img: np.ndarray,
    *,
    min_area_ratio: float = _MIN_AREA_RATIO,
    max_cards: int = 8,
) -> list[np.ndarray]:
    """Return up to `max_cards` card-shaped quadrilaterals, largest first.

    Each quad is a (4, 2) float array ordered TL, TR, BR, BL.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Flat frames (no texture) make Otsu degenerate — nothing to find.
    if float(gray.std()) < 5.0:
        return []
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, blob = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Close small holes (light glare splitting the card) with a modest kernel.
    blob = cv2.morphologyEx(blob, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = min_area_ratio * img.shape[0] * img.shape[1]

    quads: list[np.ndarray] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        epsilon = 0.02 * cv2.arcLength(contour, True)
        corners = cv2.approxPolyDP(contour, epsilon, True)
        if len(corners) != 4:
            continue
        pts = corners.reshape(-1, 2).astype(np.float32)
        hull = cv2.convexHull(pts)
        if area < cv2.contourArea(hull) * 0.88:  # reject bananas with 4 approx points
            continue
        quads.append(order_corners(pts))

    quads.sort(key=cv2.contourArea, reverse=True)
    return quads[:max_cards]


def warp_card(img: np.ndarray, quad: np.ndarray, out_size: tuple[int, int] = (CARD_W, CARD_H)) -> np.ndarray:
    """Perspective-warp a card quad into an upright `out_size` crop."""
    dst = np.float32([[0, 0], [out_size[0] - 1, 0], [out_size[0] - 1, out_size[1] - 1], [0, out_size[1] - 1]])
    M = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(img, M, out_size)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as TL, TR, BR, BL (screen coordinates)."""
    c = pts.astype(np.float32)
    tl = c[np.argmin(c.sum(axis=1))]
    br = c[np.argmax(c.sum(axis=1))]
    tr = c[np.argmin(c[:, 0] - c[:, 1])]
    bl = c[np.argmax(c[:, 0] - c[:, 1])]
    return np.array([tl, tr, br, bl], np.float32)
