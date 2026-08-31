#!/usr/bin/env python3
"""Orchestrate Wave-500 MNN v2 Sem run with mandatory post-Sem / finally rollback.

Order:
  1) apply allowlist + Load patch
  2) chunked Sem (wave100_chunked_run)
  3) on success OR failure: rollback hierarchy-dev to safe default
  4) verify safe
MNN catalog/enrichment must run separately AFTER this script exits cleanly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
PY = "/usr/bin/python3"


def run(cmd: list[str], *, check: bool = True) -> int:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    if check and r.returncode != 0:
        raise SystemExit(r.returncode)
    return r.returncode


def rollback() -> None:
    print("=== ROLLBACK hierarchy-dev safe defaults ===", flush=True)
    run([PY, "scripts/sem_smoke_settings_via_n8n.py", "revert"], check=False)
    run([PY, "scripts/sem_smoke_settings_via_n8n.py", "verify"], check=False)
    run([PY, "scripts/sem_smoke_patch_workflow.py", "revert"], check=False)
    run([PY, "scripts/sem_smoke_patch_workflow.py", "assert-safe"], check=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--ids-file",
        default=str(ART / "sem_wave500_mnn_v2_allowlist.json"),
    )
    ap.add_argument("--seed", default="sem_wave500_mnn_v2_2026-08-12")
    ap.add_argument("--chunk-size", type=int, default=10)
    ap.add_argument("--out", default=str(ART / "sem_wave500_mnn_v2_report.csv"))
    ap.add_argument(
        "--progress-artifact",
        default=str(ART / "sem_wave500_mnn_v2_progress.json"),
    )
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-apply", action="store_true")
    args = ap.parse_args()

    marker = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ids_file": args.ids_file,
        "seed": args.seed,
        "rollback_before_mnn": True,
    }
    (ART / "sem_wave500_mnn_v2_orchestrator.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rc = 1
    try:
        if not args.skip_apply:
            run(
                [
                    PY,
                    "scripts/sem_smoke_settings_via_n8n.py",
                    "apply",
                    "--ids-file",
                    args.ids_file,
                    "--n",
                    "500",
                    "--seed",
                    args.seed,
                    "--wave-label",
                    "wave500_mnn_v2",
                ]
            )
            run(
                [
                    PY,
                    "scripts/sem_smoke_patch_workflow.py",
                    "apply-s1",
                    "--seed",
                    args.seed,
                    "--allowlist-n",
                    "500",
                ]
            )

        cmd = [
            PY,
            "scripts/wave100_chunked_run.py",
            "--ids-file",
            args.ids_file,
            "--chunk-size",
            str(args.chunk_size),
            "--seed",
            args.seed,
            "--out",
            args.out,
            "--progress-artifact",
            args.progress_artifact,
        ]
        if args.resume:
            cmd.append("--resume")
        rc = run(cmd, check=False)
        marker["sem_exit_code"] = rc
        marker["sem_finished_at"] = datetime.now(timezone.utc).isoformat()
    finally:
        rollback()
        marker["rollback_at"] = datetime.now(timezone.utc).isoformat()
        marker["rollback_done"] = True
        (ART / "sem_wave500_mnn_v2_orchestrator.json").write_text(
            json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("=== post-rollback verify ===", flush=True)
        run([PY, "scripts/sem_smoke_settings_via_n8n.py", "verify"], check=False)
        run([PY, "scripts/sem_smoke_patch_workflow.py", "assert-safe"], check=False)

    if rc != 0:
        print(f"Sem wave failed rc={rc}; rollback already applied", file=sys.stderr)
        return rc
    print("Sem wave OK; hierarchy-dev rolled back; ready for offline MNN phase")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
