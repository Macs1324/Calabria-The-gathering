"""Frame -> identified cards: the pipeline behind /vision/scan and the eval CLI.

detect quads -> per quad, upright views (tapped: both sides) -> hash -> nearest
references -> closest art per card name -> top candidates.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from calabria.vision.detect import card_views, find_card_quads
from calabria.vision.index import CardIndex, embed_card

CANDIDATES = 3
_SEARCH_DEPTH = 12  # nearest arts searched to find CANDIDATES distinct names

# card_id -> {"name": ..., "set_code": ...} or None when unknown
Lookup = Callable[[str], dict[str, Any] | None]


def scan_frame(frame: np.ndarray, index: CardIndex, lookup: Lookup, *, single: bool = False) -> list[dict[str, Any]]:
    quads = find_card_quads(frame)
    if single:
        quads = quads[:1]
    cards = []
    for quad in quads:
        views, tapped = card_views(frame, quad)
        # Upright vs upside down (or tapped left vs right): keep the closer view.
        hits = min(
            (index.search(embed_card(view), k=_SEARCH_DEPTH) for view in views),
            key=lambda found: found[0][1] if found else 1 << 30,
        )
        candidates = _distinct_names([_describe(lookup, cid, dist) for cid, dist in hits])[:CANDIDATES]
        cards.append(
            {
                "quad": np.asarray(quad).round(1).tolist(),
                "tapped": tapped,
                "candidates": candidates,
                "best": candidates[0] if candidates else None,
            }
        )
    return cards


def _distinct_names(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the closest art per card name (unknown names stay distinct)."""
    seen: set[str] = set()
    out = []
    for c in candidates:
        key = c["name"] or c["card_id"]
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _describe(lookup: Lookup, card_id: str, distance: int) -> dict[str, Any]:
    meta = lookup(card_id)
    return {
        "card_id": card_id,
        "distance": distance,
        "name": meta["name"] if meta else None,
        "set_code": meta["set_code"] if meta else None,
    }
