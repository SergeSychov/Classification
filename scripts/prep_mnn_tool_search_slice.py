#!/usr/bin/env python3
"""Slice Polza Qwen web-search test CSV down to bakeoff input columns."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"

DEFAULT_IN = ART / "sem_wave500_mnn_from_catalogs_qwen_web_search_test.csv"
DEFAULT_OUT = ART / "sem_wave500_mnn_tool_search_input.csv"

COLUMNS = [
    "normalized_text",
    "attr_mnn",
    "attr_rx_otc",
    "mnn_uteka",
    "rx_uteka",
    "mnn_asna",
    "rx_asna",
    "mnn_apteka",
    "rx_apteka",
    "mnn_vidal",
    "rx_vidal",
    "mnn_stolichki",
    "rx_stolichki",
    "win_mnn",
    "win_rx_otc",
    "product_id",
    "run_id",
    "product_kind",
    "attr_brand",
    "attr_dosage_form",
    "attr_dosage",
    "attr_administration_route",
    "semantic_explanation",
    "qwen_search_status",
    "qwen_search_mnn",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_IN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Missing input: {args.input}", file=sys.stderr)
        return 1

    with args.input.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            print("Input CSV has no header", file=sys.stderr)
            return 1
        missing = [c for c in COLUMNS if c not in reader.fieldnames]
        if missing:
            print(f"Missing columns: {missing}", file=sys.stderr)
            return 1
        rows = [{c: (row.get(c) or "") for c in COLUMNS} for row in reader]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Wrote {len(rows)} rows × {len(COLUMNS)} cols → {args.output.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
