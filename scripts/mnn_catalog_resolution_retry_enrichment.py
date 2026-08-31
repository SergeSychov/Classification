#!/usr/bin/env python3
"""Retry mnn-drug-enrichment for rows with enrichment status=error; merge into Wave-500 artifacts.

Typical cause: error_code=search_empty (retryable). Does not re-run catalog consensus.
"""

from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from mnn_enrichment_map import map_enrichment_response  # noqa: E402

ART = ROOT / "redesign" / "artifacts"
DEFAULT_CSV = ART / "mnn_catalog_resolution_wave500.csv"
DEFAULT_JSON = ART / "mnn_catalog_resolution_wave500.json"
ENV_PATH = ROOT / ".env"
CSV_FIELDS = None  # filled from existing header


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def post_enrichment(url: str, product: str, timeout: int = 180) -> dict[str, Any]:
    body = json.dumps({"product": product}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {"status": "error", "error_code": "bad_shape", "error_message": str(type(data))}
    return data


def shorten_product(text: str) -> str:
    """Brand-heavy short query — often recovers from search_empty on long normalized_text."""
    head = (text or "").split("|")[0].strip()
    head = head[:90].rsplit(" ", 1)[0] if len(head) > 90 else head
    return head or (text or "")[:80]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--max-attempts", type=int, default=2, help="Attempts per product (full then short)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    env = load_env(ENV_PATH)
    n8n = (env.get("N8N_URL") or "https://n8n.sychovtest.ru").rstrip("/")
    url = f"{n8n}/webhook/mnn-drug-enrichment"

    with args.csv.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    json_rows = json.loads(args.json.read_text(encoding="utf-8"))
    by_id = {str(r.get("product_id")): r for r in json_rows}

    targets = [
        r
        for r in rows
        if r.get("enrichment_called") == "True"
        and (r.get("mnn_enrichment_status") or "").lower() == "error"
    ]
    if args.limit:
        targets = targets[: args.limit]

    print(f"retry targets={len(targets)} url={url}")
    if args.dry_run:
        for r in targets:
            print(r["product_id"], r["normalized_text"][:70])
        return 0

    stats = {
        "attempted": 0,
        "ok_accepted": 0,
        "ok_partial": 0,
        "still_error": 0,
        "transport_error": 0,
    }
    log_path = ART / "mnn_catalog_resolution_wave500_enrich_retry.log"
    log_lines: list[str] = []

    for i, row in enumerate(targets, 1):
        pid = str(row.get("product_id") or "")
        full = row.get("normalized_text") or ""
        queries = [full]
        short = shorten_product(full)
        if short and short != full:
            queries.append(short)

        mapped = None
        raw = None
        used_q = full
        transport_fail = False
        for attempt, q in enumerate(queries[: args.max_attempts], 1):
            used_q = q
            try:
                raw = post_enrichment(url, q, timeout=args.timeout)
                mapped = map_enrichment_response(raw)
                status = (mapped.get("mnn_enrichment_status") or "").lower()
                msg = (
                    f"[{i}/{len(targets)}] id={pid} attempt={attempt} q={q[:60]!r} "
                    f"status={status} err={mapped.get('enrichment_error')} "
                    f"mnn={mapped.get('mnn_enriched')!r}"
                )
                print(msg)
                log_lines.append(msg)
                if status != "error" or mapped.get("enrichment_accepted"):
                    break
            except Exception as exc:  # noqa: BLE001
                transport_fail = True
                mapped = map_enrichment_response(
                    {
                        "status": "error",
                        "error_code": "transport",
                        "error_message": str(exc),
                        "retryable": True,
                    }
                )
                raw = None
                msg = f"[{i}/{len(targets)}] id={pid} attempt={attempt} TRANSPORT {exc}"
                print(msg)
                log_lines.append(msg)
                time.sleep(args.sleep)
                continue
            time.sleep(args.sleep)

        stats["attempted"] += 1
        if transport_fail and (mapped or {}).get("enrichment_error") == "transport":
            stats["transport_error"] += 1
        st = (mapped or {}).get("mnn_enrichment_status")
        if (mapped or {}).get("enrichment_accepted"):
            stats["ok_accepted"] += 1
        elif st == "ok_partial":
            stats["ok_partial"] += 1
        elif st == "error":
            stats["still_error"] += 1

        # Merge into CSV row
        row["mnn_enrichment_status"] = (mapped or {}).get("mnn_enrichment_status") or ""
        row["mnn_enriched"] = (mapped or {}).get("mnn_enriched") or ""
        row["rx_otc_enriched"] = (mapped or {}).get("rx_otc_enriched") or row.get("rx_otc_enriched") or ""
        row["age_enriched"] = (mapped or {}).get("age_enriched") or row.get("age_enriched") or ""
        row["needs_human_review"] = str(bool((mapped or {}).get("needs_human_review")))
        final = row.get("resolved_mnn") or row.get("mnn_enriched") or ""
        row["final_candidate_mnn"] = final
        # evidence urls from enrichment
        ev = []
        for e in (mapped or {}).get("mnn_evidence") or []:
            if isinstance(e, dict) and e.get("url"):
                ev.append(e["url"])
        if ev:
            prev = row.get("evidence_urls") or ""
            row["evidence_urls"] = (prev + " | " if prev else "") + " | ".join(ev)
        row["enrichment_retry_query"] = used_q
        row["enrichment_retried"] = "True"

        # Merge JSON
        j = by_id.get(pid)
        if j is not None:
            j["mnn_enrichment_status"] = row["mnn_enrichment_status"]
            j["mnn_enriched"] = row["mnn_enriched"]
            j["rx_otc_enriched"] = row["rx_otc_enriched"]
            j["age_enriched"] = row["age_enriched"]
            j["final_candidate_mnn"] = row["final_candidate_mnn"]
            j["needs_human_review"] = bool((mapped or {}).get("needs_human_review"))
            j["evidence_urls"] = row.get("evidence_urls") or ""
            j["enrichment_map"] = mapped
            j["enrichment_retry_query"] = used_q
            j["enrichment_retried"] = True
            if raw is not None:
                j["enrichment_raw_retry"] = raw

    # Ensure optional columns present
    for col in ("enrichment_retried", "enrichment_retry_query"):
        if col not in fieldnames:
            fieldnames.append(col)

    with args.csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    args.json.write_text(json.dumps(json_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # Recompute summary counters
    unresolved_final = sum(1 for r in rows if not (r.get("resolved_mnn") or r.get("mnn_enriched")))
    enrich_ok = sum(1 for r in rows if r.get("mnn_enriched"))
    enrich_called = sum(1 for r in rows if r.get("enrichment_called") == "True")
    catalog_resolved = sum(1 for r in rows if r.get("mnn_resolution_status") == "resolved_catalog")
    still_err = sum(
        1
        for r in rows
        if r.get("enrichment_called") == "True"
        and (r.get("mnn_enrichment_status") or "").lower() == "error"
    )
    progress = {
        "db_logging_mode": "artifacts_only_schema_blocked",
        "total": len(rows),
        "catalog_resolved": catalog_resolved,
        "unresolved_catalog": len(rows) - catalog_resolved,
        "enrichment_called": enrich_called,
        "enrichment_ok": enrich_ok,
        "enrichment_error_remaining": still_err,
        "unresolved_final": unresolved_final,
        "retry_stats": stats,
    }
    (ART / "mnn_catalog_resolution_wave500_progress.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log_path.write_text("\n".join(log_lines) + "\n" + json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(progress, ensure_ascii=False, indent=2))
    print(f"updated {args.csv}")
    print(f"updated {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
