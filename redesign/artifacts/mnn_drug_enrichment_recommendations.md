# Рекомендации: workflow `mnn-drug-enrichment`

**Дата:** 2026-08-11 (обновлено после P0+P1 + hard-20)  
**Workflow:** `mnn-drug-enrichment` (`bEyKA1JJr0swuLql`) на `n8n.sychovtest.ru`  
**Статус:** active · защита **P0+P1 внедрена**  
**Эндпоинт:** `POST /webhook/mnn-drug-enrichment` с телом `{"product":"..."}` (также public chat)  
**Связанные артефакты:**
- error-handling plan: `mnn_drug_enrichment_error_handling_recommendations.md`
- hard-20 results: `mnn_drug_enrichment_hard20_results.csv` / `.json`
- агентный SearXNG hard-20: `searxng_mnn_hard20_analysis.md`
- snapshot WF: `mnn_drug_enrichment_workflow_p0p1.json`

Не путать с `drug-mnn-enrichment` / `…-autoresume`: это **batch CSV + DeepSeek без web search**. Ниже — только `mnn-drug-enrichment` (search-grounded).

---

## 1. Как устроен workflow (после P0+P1)

Детерминированный конвейер (не AI Agent):

```
Chat | Webhook
  → Prepare Input
  → DeepSeek preprocess          [retryOnFail ×3, onError → Error Normalizer]
      → 3 query: МНН/ГРЛС, RX/OTC, возраст
  → SearXNG HTTP GET ×3          [retryOnFail ×3, neverError]
  → Aggregate Search
      · приоритет official hosts, clip ≤16×300
      · если hits < 3 → до +2 fallback-запросов
      · 0 hits → skip_llm + status=search_empty (без догадок модели)
  → IF skip_llm → Finalize
  → DeepSeek postprocess         [retry ×3, onError → Error Normalizer]
  → Validate JSON (+ status / warnings / needs_parse_retry)
  → IF parse retry → DeepSeek postprocess retry → Validate After Retry
  → Finalize (единый контракт)
  → Respond webhook | Chat output
```

**Контракт ответа:**

```json
{
  "status": "ok | ok_partial | error",
  "error_code": null,
  "error_message": null,
  "retryable": false,
  "Category": "Drug|BAS|Other",
  "mnn": "строка" | ["компонент1", "компонент2"] | null,
  "RX_OTC": "RX|OTC|not applicable",
  "Age": "Взрослый|Детский|Универсальный",
  "Text": "…",
  "search_count": 16,
  "search_queries": [],
  "fallback_queries": [],
  "evidence": [{"url":"…","title":"…","query":"…"}],
  "ok_json": true,
  "warnings": []
}
```

Grounded-контракт сохранён: без сниппетов МНН не выдумывается. Multi-INN — JSON-массив.

### Hard-20 (те же проблемные позиции, что для агентного SearXNG)

| метрика | `mnn-drug-enrichment` P0+P1 | агент `SearXNG` |
|---|---:|---:|
| n | 20 | 20 |
| HTTP/exec error | **0** | 7–8 abort (maxIterations) |
| `status=ok` | **17** | — |
| `ok_partial` | 3 | — |
| MNN filled | **16 / 20 (80%)** | 13 / 20 (65%) |
| avg latency | **~6.4 s** | ~5–7 s success / 20–32 s fail |

Закрыты кейсы, где агент падал: **Тиоцетам**, **Панавир**, **Туджео**, **Новема Найт**.  
`ok_partial` / null MNN: Пиносол, Сандра (помечена Drug без МНН), Подорожника сироп. Циннабсин → `Category=Other`, `mnn=null` (ожидаемо). Мальвацид по-прежнему без бензокаина (неполнота combo).

---

## 2. Место в нашем проекте

### Что уже есть рядом

| источник | роль | слабость |
|---|---|---|
| Catalog vote (`win_mnn`) | быстрый baseline | garbage / конфликт источников |
| Offline Polza enrich (`mnn_enriched`, без search) | дешёвый LLM | галлюцинации, низкий fill |
| Polza+Exa / tool-search bakeoff | web MNN | лимиты $, нестабильный контракт |
| Агентный WF `SearXNG` | brand→INN sandbox | loops, кривой JSON, только mnn |
| **`mnn-drug-enrichment`** | grounded MNN+RX+Age+Category+Text + retries | single-item webhook; herbal/homeopathy хвост |

### Рекомендуемая роль

**Основной web-enrichment** для хвоста (пустой / конфликтный catalog), вместо агентного `SearXNG` и Polza-only enrich.

```
Sem0/1 + Norm
  → catalog win_mnn / win_rx_otc
  → IF need_enrich (drug + empty/conflict vote)
     → POST mnn-drug-enrichment { product: normalized_text }
  → map → mnn_enriched / rx_otc_enriched / age_enriched (+ evidence/Text audit)
  → merge-policy; не писать в attr_* без gate
```

Не в hot-path каждого Stage2 item — offline / batch / Dir–Need–Mnn slice. Caller ретраит только `retryable=true` (`llm_unavailable`, `search_empty`, …).

---

## 3. Mapping в наши поля

| ответ WF | наше поле | правило |
|---|---|---|
| `mnn` string | `mnn_enriched` | trim; RU; Norm/соли |
| `mnn` array | то же | join `", "` (как в hard-20 CSV) — **зафиксировать** |
| `RX_OTC` | `rx_otc_enriched` | `RX→rx`, `OTC→otc`, `not applicable→unknown` |
| `Age` | age enrich | через `sem_normalize_attrs` |
| `Category` | мягкий kind | не override Sem0 без rubric; `Other`+null → skip drug attrs |
| `evidence` / `Text` | audit | log/snapshot |
| `status=ok_partial` | | принимать RX/Age осторожно; `mnn` не писать |
| `status=error` | | не мержить; внешний retry если `retryable` |

Merge-policy:

1. `win_mnn` пуст и `status=ok` + `mnn` → принять.  
2. Конфликт каталогов и `mnn` согласуется с ≥1 чистым источником → принять.  
3. Расхождение со всеми каталогами → conflict / human.  
4. `Category=Other` или `ok_partial` с null mnn → не заполнять `attr_mnn`.

---

## 4. Когда звать / когда не звать

**Звать:** `product_kind=drug` и (пустой win **или** разнобой источников); нужен RX/age.  
**Не звать:** devices; уже согласованный win_mnn+rx; гомеопатию можно гейтить по тексту «гомеоп.» до вызова (экономия). Wave-500 целиком без фильтра — нет.

---

## 5. Сравнение с агентным `SearXNG`

| | агент `SearXNG` | **`mnn-drug-enrichment`** |
|---|---|---|
| Поиск | tool loop | 3 query + fallback |
| Контракт | только mnn, часто битый | status+Category+mnn+RX+Age+Text+evidence |
| Empty search | блуждание | fail-closed `search_empty` |
| Hard-20 MNN | 65% | **80%** |
| Hard-20 errors | maxIterations | **0** |
| Рекомендация | sandbox | **prod enrichment path** |

---

## 6. Что сделано / что осталось

**Сделано (P0+P1)**  
HTTP retries DeepSeek×2 + SearXNG; structured errors; parse retry; fallback queries; snippet prioritize/clip; `evidence`; hard-20 прогон.

**Осталось до встраивания в cascade**

1. Batch-runner script (`product_id` + rate limit → artifacts CSV).  
2. Единая нормализация МНН (регистр, соли, порядок combo) shared с catalog/bakeoff.  
3. Kind gate в caller (гомеопатия / non-drug).  
4. Подкрутка herbal (Пиносол) и ложный `Drug` без МНН (Сандра) — prompt или post-rule: гомеоп. → Other.  
5. Human/rubric spot-check hard-20 перед merge в Sem `attr_mnn`.  
6. Не мержить в prod Stage2 до пункта 5.

---

## 7. Практический next step

1. Script batch-обёртка → прогон большего conflict/empty slice Wave-500.  
2. Зафиксировать mapper + merge-policy в offline cascade / Dir–Need–Mnn.  
3. Prompt tweak: «гомеоп.» → Category Other; для multi-oil herbal не `ok_partial` молча — либо полный список, либо явный `mnn_not_found` + Other/BAS policy.

---

## Bottom line

После P0+P1 `mnn-drug-enrichment` подтверждён на hard-20: **80% MNN, 0 transport/agent abort**, стабильный JSON-контракт с `status`/`evidence`/`retryable`. Это основной кандидат на web-enrichment хвоста; агентный SearXNG для этого слота не нужен. Дальше — batch-runner, нормализация МНН и rubric перед записью в Sem attrs.
