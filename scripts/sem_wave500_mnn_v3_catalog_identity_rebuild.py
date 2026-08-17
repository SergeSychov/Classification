#!/usr/bin/env python3
"""Wave-500 MNN v3 identity-rich catalog rebuild (cache-first, product-card only).

Writes NEW artifacts:
  redesign/artifacts/sem_wave500_mnn_v3_from_catalogs_identity.{csv,json,_summary.md}

Does not overwrite lean v3 from_catalogs CSV.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_PATH = ROOT / "scripts" / "sem_wave500_mnn_from_catalogs.py"
LIB = ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from mnn_source_identity import (  # noqa: E402
    PARSER_VERSION,
    classify_source_url_or_page,
    extract_doses,
    extract_form,
    extract_pack,
)

ART = ROOT / "redesign" / "artifacts"
DEFAULT_INPUT = ART / "sem_wave500_mnn_v3_report.csv"
DEFAULT_OUT = ART / "sem_wave500_mnn_v3_from_catalogs_identity"
DEFAULT_CACHE = ART / "_catalog_cache"

SITES = ("uteka", "asna", "apteka", "vidal", "stolichki")


def _load_scraper():
    spec = importlib.util.spec_from_file_location("sem_wave500_mnn_from_catalogs", SCRAPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scraper {SCRAPER_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_query_ladder(row: dict[str, str], scraper: Any) -> list[tuple[str, str]]:
    """Return ordered (ladder_step, query) pairs."""
    brand = (row.get("attr_brand") or "").strip()
    dose = scraper.simplify_dose(row.get("attr_dosage") or "")
    form = (row.get("attr_dosage_form") or "").strip()
    text = (row.get("normalized_text") or "").split("|")[0].strip()
    text = scraper.re.sub(r"\b[N№]\s*\d+\b", " ", text, flags=scraper.re.I)
    text = scraper.re.sub(r"\s+", " ", text).strip()
    head = scraper.re.split(
        r"\b(?:таб\.|табл|капсул|порошок|р-р|раствор|суспенз|мазь|гель|спрей|крем)\b",
        text,
        maxsplit=1,
        flags=scraper.re.I,
    )[0].strip(" ,.-") or text[:60]

    ladder: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(step: str, q: str) -> None:
        q = scraper.re.sub(r"\s+", " ", (q or "").strip())
        if not q or q.casefold() in seen:
            return
        seen.add(q.casefold())
        ladder.append((step, q))

    core = brand or head
    add("exact", " ".join(x for x in (core, dose, form) if x))
    add("short", " ".join(x for x in (core, dose) if x))
    add("generic", " ".join(x for x in (head, dose, form) if x))
    add("fallback", scraper.build_query(row))
    return ladder


def card_usable(card: Any) -> bool:
    if not card or not getattr(card, "url", None):
        return False
    err = (getattr(card, "error", None) or "").lower()
    if err in {"not_found", "low_match"} or err.startswith("search:") or err.startswith("card:"):
        return False
    if err == "antibot":
        return False
    return bool(getattr(card, "title", None) or getattr(card, "mnn", None))


def fetch_with_ladder(
    fetcher: Callable[[str, str | None], Any],
    ladder: list[tuple[str, str]],
    brand: str | None,
    *,
    CatalogCard: Any,
    site: str,
) -> tuple[Any, str, str]:
    last = CatalogCard(site=site, error="not_found")
    last_query = ladder[-1][1] if ladder else ""
    last_step = ladder[-1][0] if ladder else "fallback"
    for step, query in ladder:
        try:
            card = fetcher(query, brand)
        except Exception as exc:  # noqa: BLE001
            last = CatalogCard(site=site, error=str(exc))
            last_query, last_step = query, step
            continue
        last, last_query, last_step = card, query, step
        if card_usable(card):
            return card, query, step
    return last, last_query, last_step


def enrich_identity_fields(
    scraper: Any,
    client: Any,
    card: Any,
    *,
    query: str,
    ladder_step: str,
) -> dict[str, Any]:
    url = getattr(card, "url", None)
    title = getattr(card, "title", None)
    err = getattr(card, "error", None)
    fetched_at = utc_now()
    http_status: int | None = None
    card_fetched = False
    html = None

    if url:
        cache_path = client._cache_path(url)
        was_cached = cache_path.exists()
        try:
            # Prefer cache; fetch only if missing (scraper fetch already populated cache)
            if was_cached:
                html = cache_path.read_text(encoding="utf-8", errors="replace")
                http_status = 0  # cache hit
                card_fetched = True
            else:
                html = client.get(url)
                http_status = 200
                card_fetched = True
        except Exception:  # noqa: BLE001
            card_fetched = False
            http_status = None

    source_class = classify_source_url_or_page(
        url,
        html=html,
        card_fetched=card_fetched and not err,
        http_status=http_status,
    )
    if err or not card_fetched or not url or not title:
        if source_class == "product_card":
            source_class = "search_only"

    blob = f"{title or ''} {getattr(card, 'mnn', None) or ''}"
    return {
        "mnn": scraper.display_mnn_value(getattr(card, "mnn", None)),
        "rx": getattr(card, "rx", None) or "",
        "url": url or "",
        "title": title or "",
        "brand": "",
        "form": extract_form(blob) or "",
        "dose": (extract_doses(blob) or [""])[0],
        "pack": extract_pack(blob) or "",
        "match_score": getattr(card, "match_score", 0.0) or 0.0,
        "match_status": "",  # filled later by identity gate
        "source_class": source_class,
        "query": query,
        "ladder_step": ladder_step,
        "fetched_at": fetched_at if card_fetched else "",
        "http_status": "" if http_status is None else str(http_status),
        "parser_version": PARSER_VERSION,
        "error": err or "",
    }


IDENTITY_FIELDS = [
    "normalized_text",
    "product_id",
    "product_kind",
    "attr_mnn",
    "attr_rx_otc",
    "attr_brand",
    "attr_dosage",
    "attr_dosage_form",
    "attr_package_hint",
]
for _site in SITES:
    IDENTITY_FIELDS.extend(
        [
            f"mnn_{_site}",
            f"rx_{_site}",
            f"url_{_site}",
            f"title_{_site}",
            f"brand_{_site}",
            f"form_{_site}",
            f"dose_{_site}",
            f"pack_{_site}",
            f"match_score_{_site}",
            f"match_status_{_site}",
            f"source_class_{_site}",
            f"query_{_site}",
            f"ladder_step_{_site}",
            f"fetched_at_{_site}",
            f"http_status_{_site}",
            f"parser_version_{_site}",
            f"error_{_site}",
        ]
    )


def main() -> int:
    scraper = _load_scraper()
    ap = argparse.ArgumentParser(description="Identity-rich catalog rebuild for Wave-500 v3")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--max-requests", type=int, default=4000)
    ap.add_argument(
        "--sites",
        default="uteka,asna,apteka,vidal,stolichki",
        help="Comma list of sites",
    )
    ap.add_argument("--drugs-only", action="store_true", default=True)
    args = ap.parse_args()

    sites = [s.strip() for s in args.sites.split(",") if s.strip()]
    with args.input.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if args.drugs_only:
        rows = [r for r in rows if (r.get("product_kind") or "") == "drug"]
    else:
        rows = [r for r in rows if scraper.is_eligible(r)]
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]

    client = scraper.HttpClient(
        sleep_sec=args.sleep,
        timeout_sec=args.timeout,
        cache_dir=args.cache_dir,
        max_requests=args.max_requests,
    )

    log_path = Path(str(args.out_prefix) + "_run.log")
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    started = time.time()
    log(f"start identity rebuild rows={len(rows)} sites={sites}")

    apteka_urls: list[str] = []
    if "apteka" in sites:
        log("loading apteka sitemap…")
        apteka_urls = scraper.ensure_apteka_sitemap(client)
        log(f"apteka sitemap urls={len(apteka_urls)}")

    fetchers: dict[str, Callable[..., Any]] = {
        "uteka": lambda q, b: scraper.fetch_uteka(client, q, b),
        "asna": lambda q, b: scraper.fetch_asna(client, q, b),
        "apteka": lambda q, b: scraper.fetch_apteka(client, q, b, apteka_urls),
        "vidal": lambda q, b: scraper.fetch_vidal(client, q, b),
        "stolichki": lambda q, b: scraper.fetch_stolichki(client, q, b),
    }

    records: list[dict[str, Any]] = []
    class_counts: dict[str, int] = {}

    for i, row in enumerate(rows, 1):
        brand = (row.get("attr_brand") or "").strip() or None
        ladder = build_query_ladder(row, scraper)
        rec: dict[str, Any] = {
            "normalized_text": row.get("normalized_text") or "",
            "product_id": row.get("product_id") or "",
            "product_kind": row.get("product_kind") or "",
            "attr_mnn": row.get("attr_mnn") or "",
            "attr_rx_otc": row.get("attr_rx_otc") or "",
            "attr_brand": row.get("attr_brand") or "",
            "attr_dosage": row.get("attr_dosage") or "",
            "attr_dosage_form": row.get("attr_dosage_form") or "",
            "attr_package_hint": row.get("attr_package_hint") or "",
        }
        for site in SITES:
            if site not in sites:
                for k in (
                    "mnn",
                    "rx",
                    "url",
                    "title",
                    "brand",
                    "form",
                    "dose",
                    "pack",
                    "match_score",
                    "match_status",
                    "source_class",
                    "query",
                    "ladder_step",
                    "fetched_at",
                    "http_status",
                    "parser_version",
                    "error",
                ):
                    rec[f"{k}_{site}"] = "skipped" if k == "error" else ""
                continue
            card, query, step = fetch_with_ladder(
                fetchers[site],
                ladder,
                brand,
                CatalogCard=scraper.CatalogCard,
                site=site,
            )
            fields = enrich_identity_fields(
                scraper, client, card, query=query, ladder_step=step
            )
            class_counts[fields["source_class"]] = class_counts.get(fields["source_class"], 0) + 1
            for k, v in fields.items():
                rec[f"{k}_{site}"] = v if not isinstance(v, float) else f"{v:.4f}"
        records.append(rec)
        log(
            f"[{i}/{len(rows)}] pid={rec['product_id']} "
            f"classes="
            + ",".join(rec.get(f"source_class_{s}") or "-" for s in sites)
            + f" http={client.request_count}"
        )
        if i % 10 == 0 or i == len(rows):
            _write(records, args.out_prefix, started, client.request_count, class_counts)

    summary = _write(records, args.out_prefix, started, client.request_count, class_counts)
    log(f"done {json.dumps(summary, ensure_ascii=False)}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _write(
    records: list[dict[str, Any]],
    out_prefix: Path,
    started: float,
    http_requests: int,
    class_counts: dict[str, int],
) -> dict[str, Any]:
    csv_path = Path(str(out_prefix) + ".csv")
    json_path = Path(str(out_prefix) + ".json")
    md_path = Path(str(out_prefix) + "_summary.md")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=IDENTITY_FIELDS, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            w.writerow({k: rec.get(k, "") for k in IDENTITY_FIELDS})
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elapsed = time.time() - started
    summary = {
        "rows": len(records),
        "elapsed_sec": round(elapsed, 2),
        "http_requests": http_requests,
        "source_class_counts": class_counts,
        "product_card_sites": class_counts.get("product_card", 0),
        "search_only_sites": class_counts.get("search_only", 0)
        + class_counts.get("listing", 0)
        + class_counts.get("generic_mnn_page", 0),
    }
    Path(str(out_prefix) + "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(
        "\n".join(
            [
                "# Identity-rich catalog rebuild",
                "",
                f"- rows: {summary['rows']}",
                f"- elapsed: {summary['elapsed_sec']}s",
                f"- http_requests: {summary['http_requests']}",
                f"- source_class_counts: {summary['source_class_counts']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
