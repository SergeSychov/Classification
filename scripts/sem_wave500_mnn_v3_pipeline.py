#!/usr/bin/env python3
"""Full Wave-500 MNN v3 pipeline with wall-clock timing.

Sem (allowlist-wide) → rollback → catalog scrape → MNN catalog+enrichment+evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
PY = "/usr/bin/python3"
SEED = "sem_wave500_mnn_v3_2026-08-13"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-allowlist", action="store_true")
    ap.add_argument("--skip-sem", action="store_true")
    ap.add_argument("--skip-catalog", action="store_true")
    ap.add_argument("--skip-mnn", action="store_true")
    ap.add_argument("--resume-sem", action="store_true")
    args = ap.parse_args()

    timing = {
        "wave": "mnn_v3",
        "seed": SEED,
        "pipeline_started_at": utc_now(),
        "phases": {},
    }
    timing_path = ART / "sem_wave500_mnn_v3_timing.json"

    def mark(phase: str, started: str, ended: str | None = None, **extra):
        timing["phases"][phase] = {
            "started_at": started,
            "ended_at": ended or utc_now(),
            **extra,
        }
        s = datetime.fromisoformat(timing["phases"][phase]["started_at"])
        e = datetime.fromisoformat(timing["phases"][phase]["ended_at"])
        timing["phases"][phase]["elapsed_sec"] = round((e - s).total_seconds(), 1)
        timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")

    allowlist = ART / "sem_wave500_mnn_v3_allowlist.json"
    report = ART / "sem_wave500_mnn_v3_report.csv"
    catalog = ART / "sem_wave500_mnn_v3_from_catalogs.csv"
    mnn_prefix = ART / "mnn_catalog_resolution_wave500_v3"

    if not args.skip_allowlist:
        t0 = utc_now()
        run([PY, "scripts/sem_wave500_mnn_v3_allowlist.py", "--seed", SEED, "--n", "500", "--out", str(allowlist)])
        mark("allowlist", t0)

    if not args.skip_sem:
        t0 = utc_now()
        cmd = [PY, "scripts/sem_wave500_mnn_v3_orchestrator.py", "--seed", SEED, "--chunk-size", "10"]
        if args.resume_sem:
            cmd.append("--resume")
        run(cmd)
        mark("sem_plus_rollback", t0)
        # capture hierarchy run ids from report
        if report.exists():
            rows = list(csv.DictReader(report.open(encoding="utf-8")))
            run_ids = sorted({r["run_id"] for r in rows if r.get("run_id")})
            timing["hierarchy_run_ids"] = run_ids
            timing["sem_rows"] = len(rows)
            timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.skip_catalog:
        t0 = utc_now()
        run(
            [
                PY,
                "scripts/sem_wave500_mnn_from_catalogs.py",
                "--input",
                str(report),
                "--out-prefix",
                str(ART / "sem_wave500_mnn_v3_from_catalogs"),
                "--cache-dir",
                str(ART / "_catalog_cache"),
            ]
        )
        mark("catalog_scrape", t0)

    if not args.skip_mnn:
        t0 = utc_now()
        run_ids = ",".join(timing.get("hierarchy_run_ids") or [])
        run(
            [
                PY,
                "scripts/mnn_catalog_resolution_wave500_v2.py",
                "--report",
                str(report),
                "--catalog",
                str(catalog),
                "--out-prefix",
                str(mnn_prefix),
                "--raw-jsonl",
                str(ART / "mnn_wave500_v3_searxng_raw.jsonl"),
                "--research-csv",
                str(ART / "mnn_wave500_v3_research_context.csv"),
                "--research-json",
                str(ART / "mnn_wave500_v3_research_context.json"),
                "--human-review",
                str(ART / "mnn_catalog_resolution_wave500_v3_human_review.csv"),
                "--hierarchy-run-ids",
                run_ids,
            ]
        )
        mark("mnn_catalog_enrichment", t0)

    timing["pipeline_finished_at"] = utc_now()
    s = datetime.fromisoformat(timing["pipeline_started_at"])
    e = datetime.fromisoformat(timing["pipeline_finished_at"])
    timing["pipeline_elapsed_sec"] = round((e - s).total_seconds(), 1)
    timing["artifacts"] = {
        "full_sem_table": str(report.relative_to(ROOT)),
        "allowlist": str(allowlist.relative_to(ROOT)),
        "catalog_table": str(catalog.relative_to(ROOT)),
        "mnn_table": "redesign/artifacts/mnn_catalog_resolution_wave500_v3.csv",
        "timing": str(timing_path.relative_to(ROOT)),
        "searxng_raw": "redesign/artifacts/mnn_wave500_v3_searxng_raw.jsonl",
        "research_context": "redesign/artifacts/mnn_wave500_v3_research_context.csv",
    }
    timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(timing, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
