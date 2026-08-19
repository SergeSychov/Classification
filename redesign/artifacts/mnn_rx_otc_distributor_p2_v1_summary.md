# Distributor P2 probe

**route_feasibility:** `P2_DISTRIBUTOR_PUBLIC_CATALOG_ASNA_ONLY`
**recommendation:** `KEEP_RX_OTC_P2_SUPPORT_ONLY`
**valid P2 explicit (ASNA cards):** 9/10
**requests:** 26/40

Not official P1. B2B distributor catalogs were not publicly readable.
Competitive multi-distributor answers: **not possible** (only ASNA has a public SKU catalog).

ASNA is a **pharmacy-association retail** catalog, not Катрен/Пульс/Протек B2B. Even when brand+form+strength match, the card is often another manufacturer or line extension (not the SKU):

- 19370 hit **Дюспаталин ДУО** (combo), not plain 135 мг
- 26115 Ambroxol **Велфарм**, not Вертекс
- 10046 Папаверин **Медисорб**, not Ирбит
- 2621 Фурацилин **Авексима**, not Татхимфарм
- 18377 Йод 10 мл МФФ, not Гиппократ 25 мл
- 4924 крем: форма верная, завод в URL не ЛЕККО

Termicon spray vs cream split on ASNA **did** work (different `/cards/` URLs).

| host | public SKU search | blocker |
|---|---|---|
| asna.ru | True | public GET search returns /cards/*.html |
| katren.ru | False | site search is CMS articles (Поиск статьи), not SKU catalog |
| puls.ru | False | waf_or_auth_401 |
| protek.ru | False | corporate GET /search/ observed; product catalog not public |
| pharmk.ru | False | login_required |
| bsspharm.ru | False | corporate landing; pharmacy brands linked off-host (not fetched) |

| product_id | brand | access | grade | candidate | URL |
|---|---|---|---|---|---|
| 3065 | ФЛУКОНАЗОЛ-OBL | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/flukonazol_obl_150mg_1_sht__kapsuly_alium_ao.html |
| 4922 | ТЕРМИКОН | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/termikon_1_30g_sprey_dnaruzhnogo_primeneniya_farmstandart-tomskkhimfarm_oao.html |
| 4924 | ТЕРМИКОН | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/termikon_1_15g_krem_dnaruzhnogo_primeneniya_farmstandart-tomskkhimfarm_oao.html |
| 19370 | ДЮСПАТАЛИН | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/dyuspatalin_duo_135mg8443mg_n30_tab_pokrytye_plenochnoy_obolochkoy_verofarm_ao.html |
| 26115 | АМБРОКСОЛ | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/ambroksol_velfarm_30mg_n50_tab_velfarm_ooo.html |
| 10046 | ПАПАВЕРИН | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/papaverina_gidrokhlorid_ms_40mg_n20_tab_medisorb.html |
| 7275 | САНОВАСК | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/sanovask_50mg_n30_tab_pokrytye_kishechnorastvorimoy_plenochnoy_obolochkoy_irbitskiy_khimfarmzavod_oao.html |
| 1053 | ЭКЗОРОЛФИНЛАК | p2_record_found_identity_insufficient | D |  | https://www.asna.ru/cards/fitolaks_tab_500mg_n40_evalar.html |
| 2621 | ФУРАЦИЛИН | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/furatsilin_aveksima_20mg_n20_tab_shipuchie_dprigotovleniya_r-ra_dmestnogonaruzhnogo_primeneniya_irbitskiy_khfz.html |
| 18377 | ЙОД | p2_valid_explicit_status | A | otc | https://www.asna.ru/cards/yod_5__10ml_rastvor_dlya_narujnogo_primeneniya_spirtovoy_flakon_s_lopatkoy_moskovskaya_farmacevticheskaya_fabrika_zao.html |

## Isolation

- no n8n / DB / LLM / SearXNG
- no login/CAPTCHA bypass
- `final_rx_otc_value` empty; `outcome=feasibility_only`; `official_p1=false`
- no Phase A; prior M3.2b artifacts not overwritten
