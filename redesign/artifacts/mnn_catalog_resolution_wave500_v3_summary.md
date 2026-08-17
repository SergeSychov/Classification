# MNN catalog resolution Wave-500 v2 — summary

- mnn_enrichment_run_id: **459**
- eligible drugs: **184**
- catalog resolved: **103**
- enrichment calls: **81**
- enrichment attempts (incl retries): **95**
- calls with raw SearXNG saved: **95**
- retries: **14**
- enrichment accepted: **60**
- avg search results per call: **16.0**
- selected evidence rows: **1140**
- unresolved final: **21**
- unresolved with evidence: **21**
- human review CSV rows: **80**

## Evidence artifacts

- raw JSONL: `redesign/artifacts/mnn_wave500_v3_searxng_raw.jsonl`
- research context CSV: `redesign/artifacts/mnn_wave500_v3_research_context.csv`
- research context JSON: `redesign/artifacts/mnn_wave500_v3_research_context.json`

## Safety

- attr_* / snapshot not overwritten
- Sem/Dir/Need not live-wired to evidence
