# Qwen Web Search — resume api_error + conflict review

## A. Resume api_error

- Targeted api_error rows: **59**
- Actually re-requested this session: **2**
- Recovered with confirmed web-search annotations: **0**
- Remaining api_error: **59**
- Remaining error types: `{"INSUFFICIENT_BALANCE": 59}`
- Elapsed resume: 13.75s

**Blocked:** aborted after consecutive INSUFFICIENT_BALANCE/daily-limit 402 responses (Polza wallet ~397 RUB remains, but daily spend cap is hit: «Достигнут дневной лимит по сумме»). Recovered 0/59.

Note: Polza wallet may still show balance while **daily spend limit** returns HTTP 402 `INSUFFICIENT_BALANCE` / «Достигнут дневной лимит по сумме». Retries cannot bypass this.

## Updated totals (full test CSV)

- Total rows: **224**
- Search confirmed (annotations>0): **165**
- found: **144**
- exact_match: **42**
- normalized_match: **65**
- conflict: **25**
- qwen_only: **12**
- catalog_only: **11**
- both_empty: **10**
- qwen_api_error: **59**
- Status breakdown: `{"found": 144, "not_found": 21, "api_error": 59}`

## B. Conflict review

- File: `/Users/serge/Developer/categories/redesign/artifacts/qwen_catalog_mnn_conflict_review.csv`
- Rows (conflict + qwen_only + catalog_only): **48**

### 10 illustrative conflicts / disagreements

| product | catalog | qwen | vs | source |
|---|---|---|---|---|
| ХЛОРОФИЛЛИПТ ТАБЛ. Д/РАССАС. 25МГ №20 ВИФИТЕХ /  | Эвкалипта листьев экстракт | хлорофиллипт | conflict | https://www.asna.ru/cards/khlorofillipt_25mg_n20_tab_drassasyvaniya_vi |
| ФЛИКСОТИД АЭРОЗ. Д/ИНГАЛ. ДОЗИР. 250МКГ/ДОЗА ФЛ. | Флутиказон | флутиказона пропионат | conflict | https://www.vidal.ru/drugs/flixotide__898 |
| ТИОЦЕТАМ Р-Р ДЛЯ В/В И В/М ВВЕД. 25МГ/МЛ+100МГ/М | Пирацетам | Морфолиния тиазотат+Пирацетам | conflict | https://www.pharmcontrol.ru/registry/drugs/133848/ |
| СИНТОМИЦИН ЛИНИМЕНТ 10% ТУБА 25Г НИЖФАРМ / НИЖФА | Хлорамфеникол [D,L] | Хлорамфеникол | conflict | https://www.vidal.ru/drugs/synthomycin |
| РИНЗА КИДС ПОР. Д/Р-РА Д/ПРИЕМА ВНУТРЬ МАЛИНА ПА | Парацетамол, Аскорбиновая кислота, Ф | Paracetamol + Pheniramine + Ascorbic | conflict | https://www.medixlife.com/rinza-kids-instructions/ |
| РЕННИ ТАБЛ. ЖЕВ. С АПЕЛЬСИНОВЫМ ВКУСОМ 680МГ+80М | Кальция карбонат, Магния карбонат | кальция карбонат + магния гидроксика | conflict | https://bor.farmani.ru/catalog/renni_tbl_zhev_apelsin_48_delfarm_gayya |
| ПИНОСОЛ СПРЕЙ НАЗ. ФЛ. 10МЛ / ФАРМАК ПАО / ФАРМА | Мяты Перечной Масло, Тимол, Эвкалипт | масло сосны горной + масло мяты пере | conflict | https://drugs.medelement.com/drug/%D0%BF%D0%B8%D0%BD%D0%BE%D1%81%D0%BE |
| ПЕРСЕН ТАБЛ. П/О №40 СОФАРМА / СОФАРМА / СОФАРМА | Валерианы лекарственной корневищ с к | экстракт валерианы + экстракт мелисс | conflict | https://gorodec.farmani.ru/catalog/persen_tabletki_pokrytye_obolochkoy |
| ПАНАВИР Р-Р ДЛЯ В/В ВВЕД. 0,04МГ/МЛ АМП. 5МЛ №2  | Полисахариды побегов Solanum tuberos | картофеля побегов сумма полисахаридо | conflict | https://apteka-info.ru/catalog/product/152895/ |
| НЕМОЗОЛ ТАБЛ. ЖЕВ. 400МГ №1 / ИПКА ЛАБОРАТОРИЗ Л | Албендазол | Альбендазол | conflict | https://clinline.ru/reestr-zaregistrirovannyh-preparatov.html?lp_page= |

Note: no merge into attr_mnn / win_mnn / DB. Journal not updated.

