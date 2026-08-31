# Qwen Web Search MNN test — summary

- Input catalog: `/Users/serge/Developer/categories/redesign/artifacts/sem_wave500_mnn_from_catalogs.csv` (245 rows)
- Wave join: `/Users/serge/Developer/categories/redesign/artifacts/sem_wave500_report.csv` (drugs in wave: 224)
- Drug rows run: **224**
- Catalog MNN columns used for comparison: `mnn_uteka, mnn_asna, mnn_apteka, mnn_vidal, mnn_stolichki, win_mnn`
- Comparison field: `win_mnn` → `catalog_mnn_for_comparison`
- Elapsed: 0.0s (avg 0.0s/row)

## Integration

- Provider: Polza (`https://polza.ai/api/v1`)
- Real web search path: `plugins: [{id: "web", engine: "exa"}]`
- Source metadata: `message.annotations[].url_citation.{url,title,content}`
- DashScope `enable_search` / `search_options`: **ignored** by Polza (HTTP 200, no sources)

## Counts

- Search confirmed (annotations>0): **165**
- Qwen status=found: **144** (coverage 0.6429)
- Status breakdown: `{"found": 144, "not_found": 21, "api_error": 59}`
- vs catalog: `{"normalized_match": 65, "exact_match": 42, "both_empty": 10, "conflict": 25, "qwen_only": 12, "catalog_only": 11, "qwen_api_error": 59}`

## Sample rows (up to 15)

| product | catalog_mnn | qwen_mnn | vs | source_url | note |
|---|---|---|---|---|---|
| БИСОМОР 2,5мг N30 таб. покрытые пленочной оболочко | Бисопролол | Бисопролол | exact_match | https://www.vidal.ru/drugs/atc/c07ab07 | Торговое наименование Бисомор (производитель Эдж Фарма Прайвет) соответствует пр |
| ЮНИДОКС СОЛЮТАБ ТАБЛ. ДИСПЕРГ. 100МГ №20 / ЗИО-ЗДО | Доксициклин | Доксициклин | exact_match | https://www.pharmcontrol.ru/registry/drugs/11893/ | Множество авторитетных источников (ГРЛС, Видаль, Medilon, Pharmeconom) подтвержд |
| АСКОРУТИН 50мг+50мг N50 таб. Фармцентр вилар АО /  | Аскорбиновая кислота, Рутозид | Аскорбиновая кислота + Рутозид | normalized_match | https://apteka-info.ru/catalog/product/819551/ | Многочисленные источники (apteka-info.ru, uteka.ru, medvestnik) подтверждают, чт |
| БИФРАДУАЛ 0,25мг/мл + 0,5мг/мл 20мл р-р д/ингаляци | Фенотерол, Ипратропия бромид | Ипратропия бромид + Фенотерол | normalized_match | https://yuzhpharm.ru/catalog/preparaty_dlya_lecheniya_obstru | На основе результатов поиска подтверждено, что торговое наименование Бифрадуал ( |
| ХЛОРОФИЛЛИПТ ТАБЛ. Д/РАССАС. 25МГ №20 ВИФИТЕХ / ВИ | Эвкалипта листьев экстракт | хлорофиллипт | conflict | https://www.asna.ru/cards/khlorofillipt_25mg_n20_tab_drassas | В найденных источниках (РЛС, Видаль) для препарата Хлорофиллипт в форме таблеток |
| ФЛИКСОТИД АЭРОЗ. Д/ИНГАЛ. ДОЗИР. 250МКГ/ДОЗА ФЛ. 6 | Флутиказон | флутиказона пропионат | conflict | https://www.vidal.ru/drugs/flixotide__898 | В найденных источниках (Видаль, Аптека.су, DifMed) для препарата Фликсотид в фор |
| ФУРАЦИЛИН ТАБЛ. Д/Р-РА Д/МЕСТН. И НАРУЖ. ПРИМ. 20М | ∅ | нитрофурал | qwen_only | https://www.vidal.ru/drugs/furacilin-1 | В найденных источниках (Liki.uz, gosapteka18.ru) для препарата Фурацилин 20 мг п |
| ФУРАЦИЛИН ПОР. Д/Р-РА Д/МЕСТН. И НАРУЖ. ПРИМ. 20МГ | ∅ | Нитрофурал | qwen_only | https://www.meligen.com/products/lekarstvennyie-sredstva/fur | Многочисленные источники (ГРЛС, сайт производителя, аптечные каталоги) подтвержд |
| СУПРИМА-БРОНХО СИРОП ФЛ. 100МЛ / ШРЕЯ ЛАЙФ САЕНСИЗ | Дихлорбензиловый спирт, Амилметакрезол | ∅ | catalog_only | https://www.vidal.ru/drugs/suprima-broncho__3461 | В предоставленных результатах поиска (ГРЛС, Аптека.ру, Фармконтроль) для препара |
| РИНГЕР-СОЛОФАРМ Р-Р Д/ИНФ. ФЛ. ПОЛИПРОП. 500МЛ №20 | Натрия хлорид, Калия хлорид, Кальция хло | ∅ | catalog_only | https://grls.minzdrav.gov.ru/default.aspx | В предоставленных результатах поиска указано торговое наименование «Рингер-Солоф |
| ДИМЕКСИД Р-Р Д/НАРУЖ. ПРИМ. 25% ФЛ. ПОЛИМЕР. 200Г  | Диметилсульфоксид | ∅ | qwen_api_error |  | ошибка API Polza/Qwen |
| ДИВАЗА ТАБЛ. Д/РАССАС. №100 / МАТЕРИА МЕДИКА ХОЛДИ | ∅ | ∅ | qwen_api_error |  | ошибка API Polza/Qwen |
| ШПРИЦ ОДНОРАЗ. 3-Х КОМП. 20МЛ LUER-SLIP ИГЛА ПРИЛО | ∅ | ∅ | both_empty | https://medmedical.ru/catalog/igly_shpritsy_/shpritsy_vogt_m | Товар является медицинским изделием (шприц одноразовый), а не лекарственным преп |
| ШПРИЦ ИНСУЛИН. U-40 ОДНОРАЗ. 3-Х КОМП. 1МЛ ИГЛА 26 | ∅ | ∅ | both_empty | https://garant1.ru/catalog/kolyucshie/shpricy-sfm/insulinovy | Товар является медицинским изделием (инсулиновый шприц), а не лекарственным преп |
| КОЛИСТИН 80мг (1000000 ЕД) N28 порошок д/приготовл | Колистиметат натрия | колистиметат натрия | normalized_match | https://www.eapteka.ru/goods/id492244/ | На основе результатов поиска установлено, что препарат «Колистин» (производитель |

