# Brandquad GRLS mirror probe (not official P1)

**host:** `https://pharm.brandquad.ru`
**source_class:** third-party commercial GRLS mirror (Brandquad)
**official_p1:** false
**mirror_feasibility:** `MIRROR_ROUTE_FEASIBLE`
**valid explicit status:** 6/10
**requests:** 11/20

Official M3.2b.4 decision is unchanged: `P1_ROUTE_NOT_FEASIBLE` / `KEEP_RX_OTC_P2_SUPPORT_ONLY`.
This source must not be used as official GRLS P1 evidence.

## Interface

- SPA `https://pharm.brandquad.ru/`
- `GET /api/grls/headers`
- `POST /api/grls` JSON `{page, page_size, order_by, filters:[{field:name, exp:term, value:[trade]}]}`
- Packaging field `is_recipe`: `По рецепту` / `Без рецепта`

## Per-SKU

| product_id | brand | access | grade | RU | status | candidate |
|---|---|---|---|---|---|---|
| 3065 | ФЛУКОНАЗОЛ-OBL | mirror_status_conflict | B | ЛП-№(001911)-(РГ-RU) | По рецепту; Без рецепта |  |
| 4922 | ТЕРМИКОН | mirror_valid_explicit_status | A | ЛСР-001548/07 | Без рецепта | OTC |
| 4924 | ТЕРМИКОН | mirror_valid_explicit_status | A | ЛС-002394 | Без рецепта | OTC |
| 19370 | ДЮСПАТАЛИН | mirror_valid_explicit_status | A | ЛП-001454 | Без рецепта | OTC |
| 26115 | АМБРОКСОЛ | mirror_valid_explicit_status | A | ЛП-№(008195)-(РГ-RU) | Без рецепта | OTC |
| 10046 | ПАПАВЕРИН | mirror_valid_explicit_status | A | ЛП-№(009756)-(РГ-RU) | Без рецепта | OTC |
| 7275 | САНОВАСК | mirror_record_found_identity_insufficient | C | ЛП-007754 | Без рецепта |  |
| 1053 | ЭКЗОРОЛФИНЛАК | mirror_record_found_status_missing | A | ЛП-003919 |  |  |
| 2621 | ФУРАЦИЛИН | mirror_valid_explicit_status | A | ЛС-001911 | Без рецепта | OTC |
| 18377 | ЙОД | mirror_record_found_identity_insufficient | C | ЛСР-006245/10 | Без рецепта |  |

## Isolation

- no official GRLS artifact overwrite
- no n8n / DB / LLM / search engines
- no commit/push
- `final_rx_otc_value` empty; `outcome=feasibility_only`
