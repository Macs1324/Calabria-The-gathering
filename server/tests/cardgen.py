"""Synthetic but card-like fixtures for the vision specs.

Real cards are mostly *black-bordered* with a bright text box; the old
fixtures (white rectangles) hid that the detector locked onto the text box.
These fakes keep the layout that matters: dark border, colored frame,
distinctive low-frequency art, light name/type/text bars.
"""

from __future__ import annotations

import cv2
import numpy as np

CARD_W, CARD_H = 315, 440


def fake_card(seed: int, *, border: tuple[int, int, int] = (18, 18, 18)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    card = np.full((CARD_H, CARD_W, 3), border, np.uint8)
    card[14:-14, 14:-14] = rng.integers(60, 160, 3)  # colored frame
    card[22:48, 24:-24] = 220  # name bar
    noise = rng.integers(0, 256, (5, 7, 3)).astype(np.uint8)
    card[52:245, 24:-24] = cv2.resize(noise, (CARD_W - 48, 193), interpolation=cv2.INTER_CUBIC)  # art
    card[250:272, 24:-24] = 215  # type line
    card[278:410, 24:-24] = 228  # text box
    return card


def place(
    card: np.ndarray,
    *,
    size: tuple[int, int] = (1280, 720),
    center: tuple[float, float] | None = None,
    height: float = 360,
    angle: float = 0.0,
    tapped: bool = False,
    mat: tuple[int, int, int] = (52, 40, 34),
    frame: np.ndarray | None = None,
) -> np.ndarray:
    """Lay `card` on a mat (or onto an existing `frame`): scale, rotate, tap."""
    w_img, h_img = size
    out = frame.copy() if frame is not None else np.full((h_img, w_img, 3), mat, np.uint8)
    if tapped:
        card = cv2.rotate(card, cv2.ROTATE_90_CLOCKWISE)
    h, w = card.shape[:2]
    scale = height / (CARD_H if not tapped else CARD_W)
    cx, cy = center if center is not None else (w_img / 2, h_img / 2)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    M[:, 2] += (cx - w / 2, cy - h / 2)
    warped = cv2.warpAffine(card, M, (w_img, h_img))
    mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), M, (w_img, h_img))
    return np.where(mask[..., None] > 127, warped, out)
