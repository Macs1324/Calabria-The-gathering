"""CLI entry points for Calabria server tooling."""

from __future__ import annotations

import argparse
from pathlib import Path

from calabria.scryfall.cards import CardMetaStore
from calabria.vision.build import build_card_index, load_persisted_index


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


def eval_scan_cli() -> None:
    """Score the scan pipeline on real photos or synthetic webcam frames."""
    from calabria.vision.evaluate import SIZE_BUCKETS, evaluate, photo_samples, synthetic_samples

    parser = argparse.ArgumentParser(description="Measure card recognition accuracy.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="built card data (default: ./data)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--photos", type=Path, help='folder of photos named after the card ("Lightning Bolt.jpg")')
    source.add_argument("--synthetic", type=int, metavar="N", help="N synthetic frames from Scryfall card images")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    index = load_persisted_index(args.data_dir)
    if not len(index):
        parser.error(f"no usable card index in {args.data_dir}: run calabria-build-index first")
    store = CardMetaStore(args.data_dir / "cards.db")
    if args.photos:
        samples = photo_samples(args.photos)
    else:
        samples = synthetic_samples(args.data_dir, store, index, n=args.synthetic, seed=args.seed)

    scores = evaluate(samples, index, store)
    order = ["all", "photo"] + [f"card {lo}-{hi}px" if hi < 10_000 else f"card {lo}px+" for lo, hi in SIZE_BUCKETS]
    for key in sorted(scores, key=lambda k: order.index(k) if k in order else len(order)):
        print(f"{key:16} {scores[key].line()}")
