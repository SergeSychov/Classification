# MNN catalog resolution Wave-500 v2 — summary

- mnn_enrichment_run_id: **405**
- eligible drugs: **28**
- catalog resolved: **20**
- enrichment calls: **8**
- enrichment attempts (incl retries): **11**
- calls with raw SearXNG saved: **11**
- retries: **3**
- enrichment accepted: **7**
- avg search results per call: **16.0**
- selected evidence rows: **132**
- unresolved final: **1**
- unresolved with evidence: **1**
- human review CSV rows: **28**

## Evidence artifacts

- raw JSONL: `redesign/artifacts/mnn_wave500_v2_searxng_raw.jsonl`
- research context CSV: `redesign/artifacts/mnn_wave500_v2_research_context.csv`
- research context JSON: `redesign/artifacts/mnn_wave500_v2_research_context.json`

## Safety

- attr_* / snapshot not overwritten
- Sem/Dir/Need not live-wired to evidence

