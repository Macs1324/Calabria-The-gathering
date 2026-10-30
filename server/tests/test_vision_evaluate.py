"""Spec for the recognition eval harness (labels and scoring)."""

import cv2
import numpy as np
from cardgen import fake_card, place

from calabria.vision.evaluate import Score, photo_samples, synthetic_frame


def test_photo_labels_come_from_filenames(tmp_path):
    img = place(fake_card(1))
    for name in ("Lightning Bolt.jpg", "Lightning Bolt 2.jpg", "Fire // Ice.png".replace("//", "-"), "notes.txt"):
        path = tmp_path / name
        if path.suffix == ".txt":
            path.write_text("ignore me")
        else:
            cv2.imwrite(str(path), img)
    labels = sorted(s.label for s in photo_samples(tmp_path))
    assert labels == ["Fire - Ice", "Lightning Bolt", "Lightning Bolt"]


def test_score_counts_top1_and_top3():
    score = Score()
    score.add(True, ["A", "B", "C"], "A")
    score.add(True, ["B", "A", "C"], "A")
    score.add(False, [], "A")
    assert (score.n, score.detected, score.top1, score.top3) == (3, 2, 1, 2)


def test_synthetic_frame_is_a_webcam_sized_jpeg_decode():
    frame = synthetic_frame(fake_card(2), np.random.default_rng(0), height=300, tapped=True)
    assert frame.shape == (720, 1280, 3)
