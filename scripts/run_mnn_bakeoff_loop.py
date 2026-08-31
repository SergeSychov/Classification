#!/usr/bin/env python3
"""Single-process chunk loop for bakeoff — keep one foreground process alive."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.mnn_tool_search_bakeoff as b  # noqa: E402

CHUNK = int(sys.argv[1]) if len(sys.argv) > 1 else 10
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
TIMEOUT = int(sys.argv[3]) if len(sys.argv) > 3 else 120
LOG = b.ART / "mnn_tool_search_bakeoff_run.log"


def pending_count() -> int:
    import csv

    rows = list(csv.DictReader(b.DEFAULT_INPUT.open(encoding="utf-8")))
    total = 0
    for m in b.MODELS:
        done = b.load_done_ids(b.out_paths(m["slug"])[0])
        total += sum(1 for r in rows if (r.get("product_id") or "") not in done)
    return total


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    pass_no = 0
    while True:
        pending = pending_count()
        log(f"loop pending={pending}")
        if pending == 0:
            log("ALL COMPLETE")
            break
        pass_no += 1
        log(f"start pass={pass_no} chunk={CHUNK}")
        rc = subprocess.call(
            [
                sys.executable,
                str(ROOT / "scripts" / "mnn_tool_search_bakeoff.py"),
                "--workers",
                str(WORKERS),
                "--timeout",
                str(TIMEOUT),
                "--limit",
                str(CHUNK),
            ],
            cwd=str(ROOT),
        )
        log(f"pass={pass_no} rc={rc} pending_after={pending_count()}")
        if pass_no > 120:
            log("safety stop")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
