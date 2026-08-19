# P1b official instruction / MAH probe

**route_feasibility:** `P1B_ROUTE_PARTIALLY_FEASIBLE`
**recommendation:** `DESIGN_OFFICIAL_INSTRUCTION_MAH_ADAPTER`
**valid P1b explicit status:** 2/10
**requests:** 37/40

No search engines. No pharmacy/Vidal as P1. Official GRLS M3.2b.4 decision unchanged.
Competitive check: two independent MAH docs with opposite status → `p1b_status_conflict`.
Termicon spray vs cream resolved to **different** instruction URLs; no P1 conflict.
Дюспаталин 135: HTML identity A, no explicit status in HTML; official PDF `dusp_Instruction_135.pdf` fetched but text layer not extracted (`pdftotext` unavailable).

| product_id | brand | access | grade | URL | candidate |
|---|---|---|---|---|---|
| 3065 | ФЛУКОНАЗОЛ-OBL | p1b_host_not_found |  |  |  |
| 4922 | ТЕРМИКОН | p1b_valid_explicit_status | A | https://termikon.ru/instrukcii/termikon-sprey-instrukciya.html | otc |
| 4924 | ТЕРМИКОН | p1b_valid_explicit_status | A | https://termikon.ru/instrukcii/termikon-krem-instrukciya.html | otc |
| 19370 | ДЮСПАТАЛИН | p1b_record_found_status_missing | A | https://duspatalin.ru/instruktsiya/135/ |  |
| 26115 | АМБРОКСОЛ | p1b_record_not_found |  |  |  |
| 10046 | ПАПАВЕРИН | p1b_host_not_found |  |  |  |
| 7275 | САНОВАСК | p1b_host_not_found |  |  |  |
| 1053 | ЭКЗОРОЛФИНЛАК | p1b_host_not_found |  |  |  |
| 2621 | ФУРАЦИЛИН | p1b_record_not_found |  |  |  |
| 18377 | ЙОД | p1b_record_found_identity_insufficient | D | https://gippokrat.ru/doc/price/price_31.07.2023_min.pdf |  |

## Isolation

- no n8n / DB / LLM / SearXNG
- no prior M3.2b artifact overwrite except new p1b_* files
- `final_rx_otc_value` empty; `outcome=feasibility_only`
- no commit/push
