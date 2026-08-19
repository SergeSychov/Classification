# M3.2b.4 — GRLS technical access investigation

**contract_version:** `rx_otc_evidence_contract_v2`
**runner:** `scripts/run_rx_otc_grls_access_v1.py`
**route_feasibility:** `P1_ROUTE_NOT_FEASIBLE`
**recommendation:** `KEEP_RX_OTC_P2_SUPPORT_ONLY`

Feasibility only. Audit-only. No SearXNG/web search, LLM, n8n, DB, snapshot, `attr_*`, or Phase A.

Final artifact rows are the last live pass (login wall / WAF). Earlier in the same investigation the public form was reachable; that window is documented below and was **not** counted as valid P1 in the final CSVs.

## 1. Portal capability

- entry: `https://grls.rosminzdrav.ru/`
- **last live inspect** redirected to `https://grls.rosminzdrav.ru/cp/login` (HTTP 200 HTML login shell)
- host class: `official_grls_portal` — Official Minzdrav GRLS portal (`grls.rosminzdrav.ru`)
- TLS: official host presents an incomplete certificate chain; read-only GET/POST used the same unverified SSL context as the existing M3.2b runner. This is not a WAF/CAPTCHA bypass.
- captcha widget: not observed
- WAF: **HTTP 403** after ~30 official requests in this investigation; subsequent landing redirected to `/cp/login`
- cookie/session: ASP.NET cookies set on public GET
- CSRF/ViewState: `__VIEWSTATE` / `__EVENTVALIDATION` present on `GRLS.aspx` when the search page is public
- last-run `direct_public_lookup_feasible`: **false** (login wall)
- last-run HTTP used: **2** / 40 (inspect + one `GRLS.aspx` GET → 403); remaining SKUs not escalated

## 2. Official endpoint / interface discovered

When the public search page was still being served (same investigation, before WAF/login wall):

| Item | Observed public interface |
|------|---------------------------|
| Host | `grls.rosminzdrav.ru` (official) |
| Search page | `GET https://grls.rosminzdrav.ru/GRLS.aspx` |
| Search method | **POST** `application/x-www-form-urlencoded` to `./GRLS.aspx` |
| Trade name | `ctl00$plate$txtTorg` |
| INN | `ctl00$plate$txtMNN` |
| Form | `ctl00$plate$LF` (typeahead; not required if rows are disambiguated) |
| Manufacturer / holder | `ctl00$plate$txtMnf` / `ctl00$plate$ownName` |
| Reg. number | `ctl00$plate$txtRegNm` |
| Search submit | `ctl00$plate$bSeek` = `Найти` |
| Mode | `ctl00$plate$isFS=0` (checked radio; `isFS=1` is not the GRLS drug grid) |
| Must **not** POST | empty `ctl00$plate$ddlRegType` (server `AppErr.aspx`) |
| Result grid | `table#ctl00_plate_gr` |
| Row → card | public JS `det(routingGuid,0)` → `Grls_View_v2.aspx?routingGuid={uuid}` |
| GET `?TradeNmR=` without POST `token` | form chrome only; **does not** run search |

Product card (`Grls_View_v2.aspx?routingGuid=…`) **can** contain product-specific identity (brand / form / pack) and explicit dispensing text in the packaging table, e.g. `30 г - флаконы - пачки картонные - Без рецепта`. Instruction content is behind a JS button (`Показать инструкции`), not a stable public file href.

`GET ?TradeNmR=` without a server-issued `token` is not a working lookup. Third-party mirrors were not used as P1.

**Stability:** this public POST+View route is **not** a reliable unattended adapter. After a modest official-only volume the host returned **403**, then **`/cp/login`**. Login/CAPTCHA/WAF were not bypassed.

## 3. Per-SKU P1 access (final live artifacts)

| product_id | form | p1_access_status | grade | candidate | final | reqs | mismatch |
|------------|------|------------------|-------|-----------|-------|------|----------|
| 3065 | капсулы | `p1_portal_blocked` | `None` | `None` | `None` | 1 | False |
| 4922 | спрей | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 4924 | крем | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 19370 | таблетки | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 26115 | таблетки | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 10046 | таблетки | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 7275 | таблетки | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 1053 | лак | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 2621 | таблетки | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |
| 18377 | раствор | `p1_portal_blocked` | `None` | `None` | `None` | 0 | False |

All `final_rx_otc_value` = null; all `outcome` = `feasibility_only`.

## 4. Counts by p1_access_status

- `p1_budget_exhausted` = **0**
- `p1_endpoint_unknown` = **0**
- `p1_fetch_failed` = **0**
- `p1_portal_blocked` = **10**
- `p1_record_found_identity_insufficient` = **0**
- `p1_record_found_status_missing` = **0**
- `p1_record_not_found` = **0**
- `p1_valid_explicit_status` = **0**

## 5. Valid P1 explicit status count

- p1_valid_explicit_status_count = **0** (final artifacts)

During the earlier public window, six SKUs had **fetched** `Grls_View_v2` bodies with packaging-line `Без рецепта` (4922 spray, 4924 cream, 19370 tablets 135 mg, 26115, 10046, 7275). Those rows were **not** accepted as valid P1 in that pass because brand identity was matched against portal chrome title/GUID only (grade D). That matcher defect is fixed in the runner (`validate_official_card` uses fetched body). A corrected live pass could not be completed: the host was then 403 / `/cp/login`. Those earlier fetches are **not** in the final JSONL.

Search-row GUIDs observed while public (not current evidence): 4922 spray `fb5627c1-…` ≠ 4924 cream `05136b97-…`; a third Termicon **tablets** row was present and is a form mismatch for both spray and cream SKUs.

## 6. Form / brand mismatch guards

- Manifest: 4922 `спрей` ≠ 4924 `крем`; 19370 `таблетки` + `135 мг` (not capsules 200 mg)
- Final live rows did not fetch cards (portal blocked)
- While public, the GRLS grid listed Termicon spray, cream, and tablets as **separate** `routingGuid` rows. Capsule 200 mg was not used to validate 19370.

## 7. Request budget

- last live pass: used `2` / `40` HTTP requests (stopped after 403)
- investigation total across live attempts stayed within the 40-request cap **per run**; delay `1.5`s; timeout `20`s; concurrency=1
- rate-limit behavior: public POST search worked; after repeated official GETs/POSTs the host returned **403**, then **login redirect**. No aggressive retry.

## 8. Route feasibility

`P1_ROUTE_NOT_FEASIBLE`

Reasons (decision rules): **0** valid P1 in final artifacts; portal now requires **login** (`/cp/login`) and previously **WAF 403**. A public form exists but is not a stably unattended P1 adapter.

## 9. Recommendation

`KEEP_RX_OTC_P2_SUPPORT_ONLY`

No Phase A. Do not ship a GRLS P1 adapter until a **stable** official public interface exists that does not collapse to login/WAF under the investigation budget. Optional later work (not this task): official instruction/MAH adapter if a public instruction URL appears without JS-only session.

## 10. Limitations and no-write confirmation

- Search snippets / form titles never supply RX/OTC.
- Generic portal landing/search pages are not P1 product records.
- `final_rx_otc_value` is null on all rows; `outcome=feasibility_only`.
- CAPTCHA / login / WAF was not bypassed.
- Open-data bulk dump was not downloaded (mass catalog search forbidden).
- n8n `UqssZ24Jr7Qk9ef4` / `rx-otc-product-retrieval-dev` not modified, not executed, remains inactive.
- no PostgreSQL / `classification_runs` / snapshot / `attr_*` / `product_kind`.
- no LLM; prior M3.2b / M3.2b.2 / M3.2b.3 artifacts not overwritten; no commit/push.
- prior artifact SHA256 unchanged: `True`
