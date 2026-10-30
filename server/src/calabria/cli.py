"""CLI entry points for Calabria server tooling."""

from __future__ import annotations

import argparse
from pathlib import Path

from calabria.vision.build import build_card_index


def build_card_index_cli() -> None:
    """Build the card index: bulk snapshot, metadata store, art cache, NN index."""
    parser = argparse.ArgumentParser(description="Build the Calabria card index.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="directory holding bulk snapshot, card image cache, cards.db, card_index.npz (default: ./data)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max number of card images to download this run (default: all missing)",
    )
    parser.add_argument("--concurrency", type=int, default=8, help="parallel image downloads")
    args = parser.parse_args()

    stats = build_card_index(
        args.data_dir,
        limit=args.limit,
        concurrency=args.concurrency,
    )
    print("index build complete:")
    for key, value in stats.items():
        print(f"  {key:10} {value}")
