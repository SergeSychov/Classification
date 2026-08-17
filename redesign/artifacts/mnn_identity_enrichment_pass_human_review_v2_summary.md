# Human review v2 summary (identity enrichment pass)

Audit-only display resolution for RX/OTC and Age. Not a production attribute update.

## Inputs
- human_review_v1: found
- results: found
- research_context: found
- searxng_raw: found
- sem_report: found
- identity_gate: found
- baseline_v3_csv: found
- baseline_v3_json: found
- identity_catalog: found
- product_classification_ro: ok_rows=100

## Integrity
- human_review v1 rows: 100
- human_review v2 rows: 100
- duplicate product_id: 0
- v1 file unchanged: True
- webhook/LLM calls: none
- DB writes: none (read-only attempted: ok_rows=100)

## Distributions
- final_rx_otc: {'rx': 60, 'otc': 25, 'not_applicable': 15}
- final_age: {'взрослые': 43, 'unknown': 6, 'универсальный': 36, 'not_applicable': 15}
- final_rx_otc_method: {'sem_baseline': 23, 'previous_enrichment': 25, 'identity_enrichment': 37, 'not_applicable': 15}
- final_age_method: {'sem_baseline': 16, 'not_resolved': 6, 'previous_enrichment': 26, 'identity_enrichment': 37, 'not_applicable': 15}
- needs_human_review_rx_otc: {'false': 100}
- needs_human_review_age: {'false': 94, 'true': 6}
- review_priority: {'low': 78, 'high': 22}

## Gaps / conflicts
- Drug-ish unknown RX/OTC: 0
- Drug-ish unknown Age: 6
- conflict rows (rx or age): 0
- rows with audit_data_gaps: 85

## Sample rows
- pid=68 | MNN=Эплеренон | RX=rx (sem_baseline/sem1) | Age=взрослые (sem_baseline/sem1) | prio=low | gaps=previous enrichment RX/OTC absent; previous enrichment Age absent; catalog Age absent/unknown
- pid=28 | MNN=Метформин | RX=rx (sem_baseline/sem1) | Age=взрослые (sem_baseline/sem1) | prio=low | gaps=previous enrichment RX/OTC absent; previous enrichment Age absent; catalog Age absent/unknown
- pid=26038 | MNN=Амлодипин | RX=rx (sem_baseline/sem1) | Age=взрослые (sem_baseline/sem1) | prio=low | gaps=previous enrichment RX/OTC absent; catalog RX/OTC absent/unknown; previous enrichment Age absent; catalog Age absent/unknown
- pid=26001 | MNN=Амлодипин | RX=rx (sem_baseline/sem1) | Age=взрослые (sem_baseline/sem1) | prio=low | gaps=previous enrichment RX/OTC absent; catalog RX/OTC absent/unknown; previous enrichment Age absent; catalog Age absent/unknown
- pid=21019 | MNN=Глицин | RX=otc (previous_enrichment/previous_mnn_enrichment) | Age=универсальный (previous_enrichment/previous_mnn_enrichment) | prio=low | gaps=catalog RX/OTC absent/unknown; catalog Age absent/unknown
- pid=21137 | MNN=Глибенкламид | RX=rx (previous_enrichment/previous_mnn_enrichment) | Age=универсальный (previous_enrichment/previous_mnn_enrichment) | prio=low | gaps=catalog RX/OTC absent/unknown; catalog Age absent/unknown
- pid=4481 | MNN=Транексамовая кислота | RX=rx (identity_enrichment/mnn_identity_enrichment) | Age=универсальный (identity_enrichment/mnn_identity_enrichment) | prio=low | gaps=previous enrichment RX/OTC absent; catalog RX/OTC absent/unknown; previous enrichment Age absent; catalog Age absent/unknown
- pid=24255 | MNN=Бетаметазон | RX=rx (identity_enrichment/mnn_identity_enrichment) | Age=универсальный (identity_enrichment/mnn_identity_enrichment) | prio=low | gaps=previous enrichment RX/OTC absent; catalog RX/OTC absent/unknown; previous enrichment Age absent; catalog Age absent/unknown
- pid=72 | MNN= | RX=otc (sem_baseline/sem1) | Age=универсальный (previous_enrichment/previous_mnn_enrichment) | prio=high | gaps=previous enrichment RX/OTC absent; catalog RX/OTC absent/unknown; Sem Age absent; catalog Age absent/unknown
- pid=21387 | MNN= | RX=not_applicable (not_applicable/mnn_identity_enrichment) | Age=not_applicable (not_applicable/mnn_identity_enrichment) | prio=high | gaps=

## Output
- redesign/artifacts/mnn_identity_enrichment_pass_human_review_v2.csv
