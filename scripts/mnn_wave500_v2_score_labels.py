#!/usr/bin/env python3
"""Score stub for Wave-500 MNN v2 human_review labels (no auto-labels)."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "redesign" / "artifacts" / "mnn_catalog_resolution_wave500_v2_human_review.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_IN)
    args = ap.parse_args()
    if not args.input.exists():
        raise SystemExit(f"missing {args.input}")
    rows = list(csv.DictReader(args.input.open(encoding="utf-8")))
    labeled = sum(1 for r in rows if (r.get("label_mnn") or "").strip())
    print(
        f"human_review_rows={len(rows)} labeled={labeled} unlabeled={len(rows) - labeled}"
    )
    print("No auto-labels. Fill label_mnn / label_notes manually before scoring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
