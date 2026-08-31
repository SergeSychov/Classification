#!/usr/bin/env python3
"""Offline MNN Catalog Consensus + Enrichment Router (Wave-500).

Layers:
  1) Catalog consensus (no LLM) → resolved_mnn / unresolved_catalog
  2) For unresolved drug cases → POST mnn-drug-enrichment webhook

Does NOT touch prod Stage2 / live hierarchy-dev / attr_* / snapshot.
Logging follows schema gate: artifacts_only when DB unavailable; never run_id=null.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
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

from mnn_catalog_consensus import (  # noqa: E402
    is_eligible_drug_row,
    resolve_catalog_consensus,
    sources_from_catalog_row,
)
from mnn_enrichment_map import map_enrichment_response, should_call_enrichment  # noqa: E402
from mnn_normalization import is_homeopathy_text  # noqa: E402

ART = ROOT / "redesign" / "artifacts"
DEFAULT_REPORT = ART / "sem_wave500_report.csv"
DEFAULT_CATALOG = ART / "sem_wave500_mnn_from_catalogs.csv"
DEFAULT_OUT_PREFIX = ART / "mnn_catalog_resolution_wave500"
SCHEMA_GATE = ART / "mnn_catalog_resolution_schema_gate.md"
ENV_PATH = ROOT / ".env"

WORKFLOW_VERSION = "mnn_catalog_enrichment_v1"
PROMPT_VERSION = "mnn_catalog_consensus_v1"
ENRICHMENT_WF = "mnn-drug-enrichment"
ENRICHMENT_WF_ID = "bEyKA1JJr0swuLql"

CSV_FIELDS = [
    "product_id",
    "run_id_source",
    "normalized_text",
    "product_kind",
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
    "source_canonical_json",
    "component_stats_json",
    "resolved_mnn",
    "resolved_mnn_components",
    "mnn_resolution_status",
    "resolution_reason",
    "resolved_rx_otc",
    "resolved_age_segment",
    "needs_mnn_enrichment",
    "enrichment_called",
    "mnn_enrichment_status",
    "mnn_enriched",
    "rx_otc_enriched",
    "age_enriched",
    "final_candidate_mnn",
    "needs_human_review",
    "evidence_urls",
]


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def join_rows(report: list[dict[str, str]], catalog: list[dict[str, str]]) -> list[dict[str, str]]:
    by_text = {r["normalized_text"]: r for r in report}
    # Prefer catalog rows matched to report (have product_id)
    out: list[dict[str, str]] = []
    seen_text: set[str] = set()
    for c in catalog:
        text = c.get("normalized_text") or ""
        base = by_text.get(text, {})
        row = {**c, **{k: base.get(k, c.get(k, "")) for k in (
            "product_id", "run_id", "product_kind", "normalized_text",
            "attr_mnn", "attr_rx_otc", "attr_brand",
        )}}
        row["normalized_text"] = text or base.get("normalized_text", "")
        row["product_kind"] = base.get("product_kind") or row.get("product_kind") or ""
        row["product_id"] = base.get("product_id") or row.get("product_id") or ""
        row["run_id"] = base.get("run_id") or ""
        out.append(row)
        seen_text.add(text)
    # Also include report drugs missing from catalog (empty sources)
    for r in report:
        if r.get("normalized_text") in seen_text:
            continue
        if (r.get("product_kind") or "") != "drug":
            continue
        out.append({
            "product_id": r.get("product_id", ""),
            "run_id": r.get("run_id", ""),
            "normalized_text": r.get("normalized_text", ""),
            "product_kind": r.get("product_kind", ""),
            "attr_mnn": r.get("attr_mnn", ""),
            "attr_rx_otc": r.get("attr_rx_otc", ""),
            "attr_brand": r.get("attr_brand", ""),
        })
    return out


def post_enrichment(url: str, product: str, timeout: int = 120) -> dict[str, Any]:
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
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "error", "error_code": "bad_json", "error_message": raw[:500]}
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {"status": "error", "error_code": "bad_shape", "error_message": str(type(data))}
    return data


def eta_str(done: int, total: int, start: float) -> str:
    if done <= 0:
        return "?"
    elapsed = time.time() - start
    rate = done / elapsed
    left = (total - done) / rate if rate else 0
    return f"{left/60:.1f}m"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    ap.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    ap.add_argument("--limit", type=int, default=0, help="Limit eligible drug rows (0=all)")
    ap.add_argument("--enrich-limit", type=int, default=80, help="Max enrichment calls")
    ap.add_argument("--enrich-sleep", type=float, default=1.2)
    ap.add_argument("--skip-enrichment", action="store_true")
    ap.add_argument("--enrich-only-unresolved", action="store_true", default=True)
    ap.add_argument("--write-log", action="store_true", help="Attempt DB log (requires Mode 2)")
    args = ap.parse_args()

    env = load_env(ENV_PATH)
    n8n = (env.get("N8N_URL") or os.environ.get("N8N_URL") or "https://n8n.sychovtest.ru").rstrip("/")
    enrich_url = f"{n8n}/webhook/mnn-drug-enrichment"

    db_logging_mode = "artifacts_only_schema_blocked"
    schema_blocker = "docker_postgres_unreachable; cannot create classification_runs"
    if SCHEMA_GATE.exists():
        text = SCHEMA_GATE.read_text(encoding="utf-8")
        if "new_enrichment_run" in text and "artifacts_only" not in text.split("Chosen mode")[-1][:400]:
            pass  # keep gate file as source of truth
    # Force artifacts-only unless write-log and DB later wired
    if args.write_log:
        print("WARN: --write-log requested but schema gate is artifacts_only; refusing null run_id inserts")
        args.write_log = False

    report = read_csv(args.report)
    catalog = read_csv(args.catalog)
    rows = join_rows(report, catalog)
    eligible = [r for r in rows if is_eligible_drug_row(r)]
    if args.limit and args.limit > 0:
        eligible = eligible[: args.limit]

    records: list[dict[str, Any]] = []
    t0 = time.time()
    enrich_called = 0
    enrich_ok = 0
    catalog_resolved = 0

    print(f"eligible_drugs={len(eligible)} enrich_limit={args.enrich_limit} url={enrich_url}")

    for i, row in enumerate(eligible, 1):
        sources = sources_from_catalog_row(row)
        resolved = resolve_catalog_consensus(
            sources,
            product_kind=row.get("product_kind"),
            normalized_text=row.get("normalized_text"),
        )
        if resolved["mnn_resolution_status"] == "resolved_catalog":
            catalog_resolved += 1

        enrichment_called = False
        enrich_map = {
            "mnn_enriched": None,
            "rx_otc_enriched": "unknown",
            "age_enriched": "unknown",
            "mnn_enrichment_status": None,
            "mnn_evidence": [],
            "needs_human_review": False,
            "enrichment_accepted": False,
        }
        raw_enrich = None

        call = should_call_enrichment(
            product_kind=row.get("product_kind"),
            normalized_text=row.get("normalized_text"),
            needs_mnn_enrichment=bool(resolved.get("needs_mnn_enrichment")),
            is_homeopathy=is_homeopathy_text(row.get("normalized_text")),
        )
        if (
            call
            and not args.skip_enrichment
            and enrich_called < args.enrich_limit
        ):
            try:
                raw_enrich = post_enrichment(enrich_url, row.get("normalized_text") or "")
                enrich_map = map_enrichment_response(raw_enrich)
                enrichment_called = True
                enrich_called += 1
                if enrich_map.get("enrichment_accepted"):
                    enrich_ok += 1
            except Exception as exc:  # noqa: BLE001
                enrichment_called = True
                enrich_called += 1
                enrich_map = map_enrichment_response(
                    {"status": "error", "error_code": "transport", "error_message": str(exc)}
                )
            time.sleep(args.enrich_sleep)

        final_mnn = resolved.get("resolved_mnn") or enrich_map.get("mnn_enriched")
        evidence_urls = []
        for s in resolved.get("source_raw_mnn") or []:
            if s.get("url"):
                evidence_urls.append(s["url"])
        for e in enrich_map.get("mnn_evidence") or []:
            if isinstance(e, dict) and e.get("url"):
                evidence_urls.append(e["url"])

        rec = {
            "product_id": row.get("product_id") or "",
            "run_id_source": row.get("run_id") or "",
            "normalized_text": row.get("normalized_text") or "",
            "product_kind": row.get("product_kind") or "",
            "attr_mnn": row.get("attr_mnn") or "",
            "attr_rx_otc": row.get("attr_rx_otc") or "",
            "mnn_uteka": row.get("mnn_uteka") or "",
            "rx_uteka": row.get("rx_uteka") or "",
            "mnn_asna": row.get("mnn_asna") or "",
            "rx_asna": row.get("rx_asna") or "",
            "mnn_apteka": row.get("mnn_apteka") or "",
            "rx_apteka": row.get("rx_apteka") or "",
            "mnn_vidal": row.get("mnn_vidal") or "",
            "rx_vidal": row.get("rx_vidal") or "",
            "source_canonical_json": json.dumps(
                resolved.get("source_raw_mnn") or [], ensure_ascii=False
            ),
            "component_stats_json": json.dumps(
                resolved.get("resolved_mnn_component_stats") or [], ensure_ascii=False
            ),
            "resolved_mnn": resolved.get("resolved_mnn") or "",
            "resolved_mnn_components": ", ".join(resolved.get("resolved_mnn_components") or []),
            "mnn_resolution_status": resolved.get("mnn_resolution_status") or "",
            "resolution_reason": resolved.get("resolution_reason") or "",
            "resolved_rx_otc": resolved.get("resolved_rx_otc") or "unknown",
            "resolved_age_segment": resolved.get("resolved_age_segment") or "unknown",
            "needs_mnn_enrichment": bool(resolved.get("needs_mnn_enrichment")),
            "enrichment_called": enrichment_called,
            "mnn_enrichment_status": enrich_map.get("mnn_enrichment_status") or "",
            "mnn_enriched": enrich_map.get("mnn_enriched") or "",
            "rx_otc_enriched": enrich_map.get("rx_otc_enriched") or "",
            "age_enriched": enrich_map.get("age_enriched") or "",
            "final_candidate_mnn": final_mnn or "",
            "needs_human_review": bool(enrich_map.get("needs_human_review")),
            "evidence_urls": " | ".join(evidence_urls),
            # full payloads for JSON artifact
            "_resolved": resolved,
            "_enrich_map": enrich_map,
            "_enrich_raw": raw_enrich,
        }
        records.append(rec)

        if i % 10 == 0 or i == len(eligible):
            unresolved = sum(
                1 for r in records if r["mnn_resolution_status"] != "resolved_catalog"
            )
            print(
                f"[{i}/{len(eligible)}] catalog_resolved={catalog_resolved}/{i} "
                f"enrichment_called={enrich_called} enrichment_ok={enrich_ok}/{enrich_called or 1} "
                f"unresolved={unresolved}/{i} eta={eta_str(i, len(eligible), t0)}"
            )

    # Write artifacts
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(str(args.out_prefix) + ".csv")
    json_path = Path(str(args.out_prefix) + ".json")
    summary_path = Path(str(args.out_prefix) + "_summary.md")
    progress_path = Path(str(args.out_prefix) + "_progress.json")

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r)

    json_records = []
    for r in records:
        json_records.append(
            {
                k: r[k]
                for k in CSV_FIELDS
                if k in r
            }
            | {
                "resolved_payload": r["_resolved"],
                "enrichment_map": r["_enrich_map"],
            }
        )
    json_path.write_text(
        json.dumps(json_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = len(records)
    unresolved_final = sum(
        1
        for r in records
        if not (r.get("resolved_mnn") or r.get("mnn_enriched"))
    )
    summary = {
        "db_logging_mode": db_logging_mode,
        "schema_blocker": schema_blocker,
        "total": total,
        "catalog_resolved": catalog_resolved,
        "unresolved_catalog": total - catalog_resolved,
        "enrichment_called": enrich_called,
        "enrichment_ok": enrich_ok,
        "unresolved_final": unresolved_final,
        "elapsed_sec": round(time.time() - t0, 1),
        "workflow_version": WORKFLOW_VERSION,
        "prompt_version": PROMPT_VERSION,
        "enrichment_workflow": ENRICHMENT_WF,
        "enrichment_workflow_id": ENRICHMENT_WF_ID,
        "skip_enrichment": bool(args.skip_enrichment),
    }
    progress_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Examples for summary
    examples = []
    for r in records:
        if len(examples) >= 12:
            break
        if r["mnn_resolution_status"] == "resolved_catalog" and r["resolved_mnn"]:
            examples.append(r)
    for r in records:
        if len(examples) >= 15:
            break
        if r["enrichment_called"]:
            examples.append(r)

    lines = [
        "# MNN catalog resolution Wave-500 — summary",
        "",
        f"- **db_logging_mode:** `{db_logging_mode}`",
        f"- **schema_blocker:** {schema_blocker}",
        f"- total eligible drugs: **{total}**",
        f"- catalog resolved: **{catalog_resolved}**",
        f"- unresolved catalog: **{total - catalog_resolved}**",
        f"- enrichment called: **{enrich_called}**",
        f"- enrichment accepted (ok+Drug+evidence): **{enrich_ok}**",
        f"- unresolved final (no catalog/enrichment MNN): **{unresolved_final}**",
        f"- elapsed: {summary['elapsed_sec']}s",
        "",
        "## Notes",
        "",
        "- Baseline `attr_mnn` / `attr_rx_otc` not overwritten.",
        "- Prod Stage2 / live hierarchy-dev not modified.",
        "- No `product_classification_log` writes (artifacts-only).",
        "",
        "## Examples",
        "",
    ]
    for r in examples[:15]:
        lines.append(
            f"- `{r['product_id']}` status={r['mnn_resolution_status']}/{r['resolution_reason']}; "
            f"resolved=`{r['resolved_mnn'] or '—'}`; "
            f"enrich={r['mnn_enrichment_status'] or '—'} `{r['mnn_enriched'] or ''}`; "
            f"final=`{r['final_candidate_mnn'] or '—'}`"
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
