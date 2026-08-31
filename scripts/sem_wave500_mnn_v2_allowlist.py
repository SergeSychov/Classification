#!/usr/bin/env python3
"""Build stratified Wave-500 MNN v2 allowlist with deterministic quota reallocation.

- Excludes prior Wave-500 IDs and known smoke allowlists
- Hot-prod Stage2 24h isolation (same as sem_smoke_allowlist)
- Quotas + reallocation; writes allowlist JSON + prints summary
- Can apply via n8n settings (optional --apply)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "redesign" / "artifacts"
SEED_DEFAULT = "sem_wave500_mnn_v2_2026-08-12"
N_DEFAULT = 500

REQUESTED = {
    "drug": 200,
    "vitamin_or_baa": 100,
    "medical_device": 80,
    "cosmetic_hygiene": 60,
    "other": 60,
}
# Reallocation fill priority when a stratum is short
REALLOC_PRIORITY = [
    "drug",
    "vitamin_or_baa",
    "medical_device",
    "cosmetic_hygiene",
    "other",
]

EXCLUDE_ALLOWLIST_GLOBS = [
    "sem_wave500_allowlist.json",
    "sem_smoke_*allowlist*.json",
    "sem_smoke_wave*_allowlist.json",
]


def psql(sql: str) -> str:
    # Single-line SQL avoids psql meta-command misparse of escaped newlines via ssh.
    compact = " ".join(sql.split())
    cmd = (
        "PG=$(docker ps -qf name=pharmacypostgres); "
        f"docker exec \"$PG\" psql -U pharmacy_user -d pharmacy_ai -At -c {json.dumps(compact)}"
    )
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "vps-dokploy", cmd],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout or "psql failed")
    return (r.stdout or "").strip()


def load_excluded_ids() -> set[int]:
    out: set[int] = set()
    for pattern in EXCLUDE_ALLOWLIST_GLOBS:
        for path in ART.glob(pattern):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            ids = data.get("product_ids") or []
            for x in ids:
                try:
                    out.add(int(x))
                except (TypeError, ValueError):
                    pass
    return out


def guess_bucket(product_type_guess: str, text: str) -> str:
    g = (product_type_guess or "").strip().lower()
    t = (text or "").lower().replace("ё", "е")
    mapping = {
        "drug": "drug",
        "лекар": "drug",
        "ls": "drug",
        "vitamin": "vitamin_or_baa",
        "baa": "vitamin_or_baa",
        "bad": "vitamin_or_baa",
        "vitamin_or_baa": "vitamin_or_baa",
        "device": "medical_device",
        "medical_device": "medical_device",
        "издел": "medical_device",
        "cosmetic": "cosmetic_hygiene",
        "cosmetic_hygiene": "cosmetic_hygiene",
        "гигиен": "cosmetic_hygiene",
        "other": "other",
    }
    for k, v in mapping.items():
        if k in g:
            return v
    if re.search(r"бад|витамин|омега|коллаген|q10", t):
        return "vitamin_or_baa"
    if re.search(r"тонометр|шприц|тест[\s-]*полоск|перчатк|маска медицин|игла ", t):
        return "medical_device"
    if re.search(r"шампун|крем |зубн|мыло|гель для душа|дезодорант", t):
        return "cosmetic_hygiene"
    if re.search(r"табл|капсул|мазь|сироп|р-р|раствор|суспенз|амп\.|фл\.", t):
        return "drug"
    return "other"


def fetch_eligible() -> list[dict]:
    """Pool must match Load — Select Batch smoke SQL (else chunks finish empty).

    Only pending / needs_human_review + needs_llm|no_match. Tier1 classified
    fill is forbidden — hierarchy Load will not return those rows.
    """
    sql = r"""
WITH base AS (
  SELECT p.product_id,
         COALESCE(s.product_type_guess, '') AS product_type_guess,
         COALESCE(s.combined_text, '') AS combined_text,
         0 AS tier
  FROM product_classification p
  JOIN classification_shortlist s
    ON s.product_id = p.product_id
  WHERE p.decision_status IN ('pending', 'needs_human_review')
    AND p.rule_decision_status IN ('needs_llm', 'no_match')
    AND (s.stage IS NULL OR s.stage = 'primary_rules')
    AND COALESCE(s.combined_text, '') <> ''
    AND NOT EXISTS (
      SELECT 1
      FROM product_classification_log l
      JOIN classification_runs r ON r.id = l.run_id
      WHERE l.product_id = p.product_id
        AND l.created_at >= NOW() - INTERVAL '24 hours'
        AND (
          r.workflow_name = 'classification-stage2-dev'
          OR r.run_type = 'stage2_primary_llm'
          OR COALESCE(r.workflow_name, '') ILIKE '%stage2-dev%'
        )
    )
)
SELECT product_id || E'\t' || product_type_guess || E'\t' || tier::text || E'\t' || replace(left(combined_text, 180), E'\t', ' ')
FROM base
ORDER BY product_id;
"""
    raw = psql(sql)
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        if len(parts) < 1:
            continue
        pid = int(parts[0])
        guess = parts[1] if len(parts) > 1 else ""
        tier = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        text = parts[3] if len(parts) > 3 else ""
        rows.append(
            {
                "product_id": pid,
                "product_type_guess": guess,
                "combined_text": text,
                "tier": tier,
            }
        )
    return rows


def md5_key(pid: int, seed: str) -> str:
    import hashlib

    return hashlib.md5(f"{pid}{seed}".encode("utf-8")).hexdigest()


def pick_stratified(
    rows: list[dict], *, seed: str, n: int, exclude: set[int]
) -> tuple[list[int], dict]:
    pool = [r for r in rows if r["product_id"] not in exclude]
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in pool:
        b = guess_bucket(r["product_type_guess"], r["combined_text"])
        r = {
            **r,
            "bucket": b,
            # Prefer tier-0 (pending), then md5 for determinism
            "sort": (int(r.get("tier") or 1), md5_key(r["product_id"], seed)),
        }
        by_bucket[b].append(r)
    for b in by_bucket:
        by_bucket[b].sort(key=lambda x: x["sort"])

    actual = {k: 0 for k in REQUESTED}
    reallocated: list[dict] = []
    picked: list[dict] = []
    used: set[int] = set()

    for b, q in REQUESTED.items():
        take = by_bucket.get(b, [])[:q]
        for r in take:
            picked.append(r)
            used.add(r["product_id"])
            actual[b] += 1

    shortfall = {b: REQUESTED[b] - actual[b] for b in REQUESTED if actual[b] < REQUESTED[b]}
    need = n - len(picked)

    remaining = []
    for b, items in by_bucket.items():
        for r in items:
            if r["product_id"] not in used:
                remaining.append(r)
    remaining.sort(key=lambda x: x["sort"])

    rem_i = 0
    for b in REALLOC_PRIORITY:
        while shortfall.get(b, 0) > 0 and rem_i < len(remaining) and need > 0:
            r = remaining[rem_i]
            rem_i += 1
            if r["product_id"] in used:
                continue
            src = r["bucket"]
            picked.append(r)
            used.add(r["product_id"])
            actual[src] = actual.get(src, 0) + 1
            reallocated.append({"from_bucket": src, "to_quota_of": b, "product_id": r["product_id"]})
            shortfall[b] -= 1
            need -= 1

    while need > 0 and rem_i < len(remaining):
        r = remaining[rem_i]
        rem_i += 1
        if r["product_id"] in used:
            continue
        picked.append(r)
        used.add(r["product_id"])
        actual[r["bucket"]] = actual.get(r["bucket"], 0) + 1
        reallocated.append(
            {"from_bucket": r["bucket"], "to_quota_of": "top_up", "product_id": r["product_id"]}
        )
        need -= 1

    picked.sort(key=lambda x: x["product_id"])
    ids = [r["product_id"] for r in picked]
    tier0 = sum(1 for r in picked if int(r.get("tier") or 1) == 0)
    meta = {
        "requested_quotas": REQUESTED,
        "actual_quotas": actual,
        "reallocated_count": len(reallocated),
        "reallocated_quotas": reallocated[:50],
        "reallocated_by_target": {},
        "eligible_pool": len(pool),
        "excluded_prior_count": len(exclude),
        "tier0_pending_picked": tier0,
        "tier1_expanded_picked": len(picked) - tier0,
        "eligibility_note": "load-compatible only: pending|needs_human_review + needs_llm|no_match (matches Sem smoke Load SQL)",
    }
    by_target: dict[str, int] = defaultdict(int)
    for x in reallocated:
        by_target[x["to_quota_of"]] += 1
    meta["reallocated_by_target"] = dict(by_target)
    return ids, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED_DEFAULT)
    ap.add_argument("--n", type=int, default=N_DEFAULT)
    ap.add_argument("--out", type=Path, default=ART / "sem_wave500_mnn_v2_allowlist.json")
    ap.add_argument("--apply", action="store_true", help="Write allowlist via n8n settings API")
    args = ap.parse_args()

    exclude = load_excluded_ids()
    print(f"excluded_prior_ids={len(exclude)}", flush=True)
    rows = fetch_eligible()
    print(f"eligible_rows={len(rows)}", flush=True)
    ids, meta = pick_stratified(rows, seed=args.seed, n=args.n, exclude=exclude)
    if len(ids) < args.n:
        print(f"WARN: only picked {len(ids)} < {args.n}", file=sys.stderr)

    prior = json.loads((ART / "sem_wave500_allowlist.json").read_text(encoding="utf-8"))
    prior_ids = set(int(x) for x in prior.get("product_ids") or [])
    overlap = sorted(set(ids) & prior_ids)
    if overlap:
        raise SystemExit(f"OVERLAP with prior Wave-500: {len(overlap)} e.g. {overlap[:10]}")

    payload = {
        "wave_label": "Wave-500-MNN-v2",
        "seed": args.seed,
        "n": len(ids),
        "requested_n": args.n,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "product_ids": ids,
        "quotas": meta,
        "source": "sem_wave500_mnn_v2_allowlist.py",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== allowlist summary ===")
    print(f"seed={args.seed}")
    print(f"N={len(ids)}")
    print(f"excluded_prior={meta['excluded_prior_count']}")
    print(f"requested_quotas={meta['requested_quotas']}")
    print(f"actual_quotas={meta['actual_quotas']}")
    print(f"reallocated_count={meta['reallocated_count']} by_target={meta['reallocated_by_target']}")
    print(f"overlap_prior_wave500={len(overlap)}")
    print(f"first_ids={ids[:8]}")
    print(f"last_ids={ids[-8:]}")
    print(f"wrote {args.out}")

    if args.apply:
        print(
            "Apply separately:\n"
            f"  /usr/bin/python3 scripts/sem_smoke_settings_via_n8n.py apply "
            f"--ids-file {args.out}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
