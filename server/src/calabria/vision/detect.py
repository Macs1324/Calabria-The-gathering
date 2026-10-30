"""Locate playing cards in a frame and warp them into upright crops.

Stage 1 detector, still training-free: a playmat is (mostly) one color, so a
card is whatever is far enough from it. The mat color is the frame's median
in Lab space; the threshold rides on the mat's own noise (median + k * MAD),
so black-bordered cards on dark mats still separate. Bright-blob (Otsu)
detection locked onto the light *text box* of black-bordered cards, which is
why it was replaced. Heavily illustrated playmats remain a known weak spot
(see docs/architecture.md); the confirm/search UI absorbs misses.

Crops are 63:88 (standard MTG card aspect); the fixed output size keeps
hashes comparable across frames. Landscape quads are tapped cards.
"""

from __future__ import annotations

import cv2
import numpy as np

CARD_W, CARD_H = 315, 440  # 63:88 standard MTG card ratio
_MIN_AREA_RATIO = 0.004  # ~ a card 1/9 of the frame height; smaller is noise
_MIN_DIST = 10  # Lab units; floor for very clean (synthetic) mats
_NOISE_K = 6.0  # threshold = mat median + K * MAD of the color distance
_ASPECT = (1.15, 1.75)  # 88/63 = 1.40, with room for perspective

# Region hashed for identification, as fractions (x0, y0, x1, y1) of an
# upright full card: name bar through the art. Both sides of the match (the
# warped webcam crop and Scryfall's full-card image) are cut identically, so
# no per-frame-style calibration is needed. The rules text is left out: it is
# low-contrast at webcam resolution and similar across cards.
HASH_REGION = (0.08, 0.10, 0.92, 0.56)


def find_card_quads(
    img: np.ndarray,
    *,
    min_area_ratio: float = _MIN_AREA_RATIO,
    max_cards: int = 12,
) -> list[np.ndarray]:
    """Return up to `max_cards` card-shaped quadrilaterals, largest first.

    Each quad is a (4, 2) float array ordered TL, TR, BR, BL.
    """
    h, w = img.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.int16)
    mat = np.median(lab.reshape(-1, 3), axis=0)
    dist = np.abs(lab - mat).max(axis=2).astype(np.uint8)
    med = float(np.median(dist))
    mad = float(np.median(np.abs(dist.astype(np.float32) - med))) + 1.0
    _, blob = cv2.threshold(dist, max(med + _NOISE_K * mad, _MIN_DIST), 255, cv2.THRESH_BINARY)
    blob = cv2.morphologyEx(blob, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    blob = cv2.morphologyEx(blob, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    # Fill each blob so dark art or mat-colored patches inside a card don't
    # punch holes that break its outline.
    contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = min_area_ratio * h * w

    quads: list[np.ndarray] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        hull = cv2.convexHull(contour)
        if area < cv2.contourArea(hull) * 0.85:  # concave blob: overlapping cards or clutter
            continue
        quad = _quad_from_hull(hull)
        (_, _), (rw, rh), _ = cv2.minAreaRect(quad)
        aspect = max(rw, rh) / max(min(rw, rh), 1.0)
        if not _ASPECT[0] <= aspect <= _ASPECT[1]:
            continue
        quads.append(order_corners(quad))

    quads.sort(key=cv2.contourArea, reverse=True)
    return quads[:max_cards]


def _quad_from_hull(hull: np.ndarray) -> np.ndarray:
    """4 corners for a (round-cornered) card outline; min-area box as fallback."""
    perimeter = cv2.arcLength(hull, True)
    for eps in (0.02, 0.03, 0.04, 0.05):
        approx = cv2.approxPolyDP(hull, eps * perimeter, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)
    return cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points clockwise as TL, TR, BR, BL (screen coordinates).

    Sorting by angle around the centroid keeps the four corners distinct at
    any rotation; the start is the corner nearest the top-left.
    """
    c = pts.astype(np.float32).reshape(4, 2)
    center = c.mean(axis=0)
    c = c[np.argsort(np.arctan2(c[:, 1] - center[1], c[:, 0] - center[0]))]
    return np.roll(c, -int(np.argmin(c.sum(axis=1))), axis=0)


def warp_card(img: np.ndarray, quad: np.ndarray, out_size: tuple[int, int] = (CARD_W, CARD_H)) -> np.ndarray:
    """Perspective-warp an ordered quad (TL, TR, BR, BL) into an `out_size` crop."""
    dst = np.float32([[0, 0], [out_size[0] - 1, 0], [out_size[0] - 1, out_size[1] - 1], [0, out_size[1] - 1]])
    M = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(img, M, out_size)


def card_views(img: np.ndarray, quad: np.ndarray) -> tuple[list[np.ndarray], bool]:
    """Upright portrait warps worth hashing for one quad, and whether it is tapped.

    A portrait quad is either upright or upside down; a landscape quad is a
    tapped card whose top edge is on the left or the right. Both candidates
    are returned and the matcher keeps the closer one.
    """
    q = order_corners(quad)
    top, side = np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[1])
    tapped = bool(top > side)
    shifts = (1, -1) if tapped else (0, 2)
    return [warp_card(img, np.roll(q, s, axis=0)) for s in shifts], tapped


def crop_hash_region(card: np.ndarray) -> np.ndarray:
    """Cut the identification region out of an upright full-card image."""
    x0, y0, x1, y1 = HASH_REGION
    h, w = card.shape[:2]
    return card[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
