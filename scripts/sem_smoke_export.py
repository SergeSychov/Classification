#!/usr/bin/env python3
"""Export Sem smoke report CSV (+ Wave-100 empty rubric label columns).

Can build from:
  - n8n execution analysis JSON (--from-execution via API), or
  - a hand-built JSON rows file (--from-rows).

Always includes empty per-attr Wave-100 rubric labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ART_DIR = ROOT / "redesign" / "artifacts"

ATTR_KEYS = [
    "mnn",
    "brand",
    "rx_otc",
    "nosology",
    "administration_route",
    "dosage_form",
    "dosage",
    "age_segment",
    "package_hint",
    "combination_hint",
]

RUBRIC_VALUES = ("correct", "incorrect", "unknown_acceptable", "missing_should_exist")


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str) -> dict:
    env = load_env()
    base_url = env["N8N_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    url = f"{base_url}{path}"
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    request = urllib.request.Request(url, headers=headers, method=method)
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def flat_node(run_data: dict, name: str) -> list[dict]:
    out: list[dict] = []
    for run in run_data.get(name) or []:
        for branch in (run.get("data", {}) or {}).get("main") or []:
            if not branch:
                continue
            for item in branch:
                out.append(item.get("json") or {})
    return out


def rows_from_execution(exec_id: str) -> tuple[list[dict], dict]:
    data = api_request("GET", f"/api/v1/executions/{exec_id}?includeData=true")
    run_data = data.get("data", {}).get("resultData", {}).get("runData", {})
    posts = flat_node(run_data, "Sem — Post-process")
    closes = flat_node(run_data, "Fin — Close Run")
    rows = []
    for j in posts:
        attrs = j.get("semantic_attrs") if isinstance(j.get("semantic_attrs"), dict) else {}
        row = {
            "product_id": j.get("product_id") or (j.get("context") or {}).get("product_id"),
            "run_id": j.get("run_id") or (j.get("context") or {}).get("run_id"),
            "normalized_text": j.get("normalized_text"),
            "semantic_confidence": j.get("semantic_confidence"),
            "semantic_explanation": j.get("semantic_explanation"),
            "semantic_validation_passed": j.get("semantic_validation_passed"),
            "semantic_reject_reason": j.get("semantic_reject_reason"),
            "decision_status": j.get("decision_status"),
            "next_action": j.get("next_action"),
            "selected_category_id": j.get("selected_category_id"),
            "stage": j.get("stage"),
            "log_status": j.get("log_status"),
        }
        for key in ATTR_KEYS:
            row[f"attr_{key}"] = attrs.get(key) if attrs else None
            row[f"label_{key}"] = ""  # Wave-100 rubric placeholder
        rows.append(row)
    meta = {
        "execution_id": exec_id,
        "status": data.get("status"),
        "fin_close": [
            {k: x.get(k) for k in ("id", "status", "success_count", "metadata")}
            for x in closes[-1:]
        ],
        "sem_count": len(posts),
        "upsert_snapshot_ran": "DB — Upsert Snapshot" in run_data,
        "sem_agent_ran": "Sem — AI Agent" in run_data,
    }
    return rows, meta


def csv_fieldnames() -> list[str]:
    base = [
        "product_id",
        "run_id",
        "normalized_text",
        "semantic_confidence",
        "semantic_explanation",
        "semantic_validation_passed",
        "semantic_reject_reason",
        "decision_status",
        "next_action",
        "selected_category_id",
        "stage",
        "log_status",
    ]
    for key in ATTR_KEYS:
        base.append(f"attr_{key}")
        base.append(f"label_{key}")
    return base


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = csv_fieldnames()
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_empty_wave100_template(path: Path) -> None:
    """Header-only CSV for Wave-100 labeling."""
    write_csv(path, [])
    note = path.with_suffix(".rubric.txt")
    note.write_text(
        "Wave-100 rubric labels (fill label_* columns):\n"
        + ", ".join(RUBRIC_VALUES)
        + "\nPer attr: "
        + ", ".join(ATTR_KEYS)
        + "\nDo not score final category_id.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Sem smoke / Wave-100 CSV")
    parser.add_argument("--from-execution", help="n8n execution id")
    parser.add_argument("--from-rows", help="JSON file with list of row dicts")
    parser.add_argument("--out", default=str(ART_DIR / "sem_smoke_s1_report.csv"))
    parser.add_argument(
        "--write-wave100-template",
        action="store_true",
        help="Also write empty Wave-100 CSV template + rubric note",
    )
    args = parser.parse_args()

    ART_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    meta: dict = {}

    if args.from_execution:
        rows, meta = rows_from_execution(args.from_execution)
    elif args.from_rows:
        payload = json.loads(Path(args.from_rows).read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
        for row in rows:
            for key in ATTR_KEYS:
                row.setdefault(f"label_{key}", "")
    else:
        print("Provide --from-execution or --from-rows", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    write_csv(out_path, rows)

    summary_path = out_path.with_suffix(".summary.json")
    summary = {
        "out": str(out_path.relative_to(ROOT)) if out_path.is_relative_to(ROOT) else str(out_path),
        "row_count": len(rows),
        "rubric_label_columns": [f"label_{k}" for k in ATTR_KEYS],
        "rubric_values": list(RUBRIC_VALUES),
        "meta": meta,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.write_wave100_template:
        tpl = ART_DIR / "sem_wave100_report_template.csv"
        write_empty_wave100_template(tpl)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
