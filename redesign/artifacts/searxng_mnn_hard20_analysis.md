# SearXNG workflow — hard-20 MNN probe

**Date:** 2026-08-10  
**Workflow:** `SearXNG` (`2AlEQYb1fQB7X602`) on `n8n.sychovtest.ru`  
**Stack:** Chat/Webhook → AI Agent → DeepSeek V4 Chat Model + tool `SearXNG`  
**Batch endpoint added for probe:** `POST /webhook/test/searxng-mnn`  
**Input slice:** 20 hardest drug rows from Wave-500 MNN conflict / catalog-garbage / both_empty set  
**Artifacts:** `searxng_mnn_hard20_results.csv`, `searxng_mnn_hard20_results.json`

## Workflow (as deployed)

- Prompt: «Найди МНН…» + system: only search results, RU names, JSON `{"mnn": ...}` (multi as pseudo-set).
- Search: n8n Langchain `toolSearXng` (credential `SearXNG account`).
- Originally chat-only (editor chat). For batch, temporary nodes `Webhook Batch` + `Map Batch Input` were added; workflow activated.

## Selection (why these 20)

Not spelling-only conflicts. Focus on:

| class | examples |
|---|---|
| catalog garbage / wrong match | бриллиантовый зелёный→йод; Реневал/Вертекс с чужими МНН |
| catalog internal conflict | Фурацилин Нитрофурал vs Прокаин |
| incomplete multi-INN | Тиоцетам, Мальвацид, Камистад, Дорзопт |
| herbal / exotic | Пиносол, Панавир, Хлорофиллипт |
| empty / homeopathy | Туджео, Циннабсин, Сандра, Подорожник |

## Results (after 1 retry on empties)

| metric | value |
|---|---:|
| n | 20 |
| MNN extracted | **13 / 20** (65%) |
| hard fail HTTP 500 | mostly **Max iterations (10)** |
| p50 latency (success ~5–7s) | ~5.5–6.5s |
| fail latency | ~20–32s (agent loop then abort) |

### Where it helps (vs broken catalogs)

| product | catalog / problem | SearXNG | verdict |
|---|---|---|---|
| Бриллиантовый зелёный | Йод… | Бриллиантовый зеленый | **fixes catalog** |
| Триметазидин МВ Реневал | мусор источников | Триметазидин | **OK** |
| Нимесулид-Вертекс | мусор | нимесулид | **OK** |
| Левофлоксацин Реневал | мусор | левофлоксацин | **OK** |
| Фурацилин (2) | конфликт источников | Нитрофурал | **OK** |
| Толперизон+Лидокаин | чужие МНН | Толперизон + Лидокаин | **OK** |
| Хлорофиллипт | vs qwen «хлорофиллипт» | Эвкалипта листьев экстракт | **aligns with catalog/INN style** |
| Дорзопт 2% | catalog «+Тимолол» | Дорзоламид | **likely correct** (Plus = combo) |
| Камистад | catalog только Лидокаин | Лидокаин + ромашка | **richer / better** |
| Ринза Кидс | EN у Qwen | RU multi-INN | **OK format** |
| Пиносол (retry) | сложный herbal | multi oils | **partial** (noisy naming) |

### Where it fails / weak

| product | issue |
|---|---|
| Тиоцетам, Панавир, Туджео, Новема, гомеопатия | Agent hits **maxIterations=10**, HTTP 500 |
| Подорожника сироп / Циннабсин (retry) | Tool-call text leaks into `output`, no final JSON |
| Мальвацид | same gap as Qwen: **missing Бензокаин** |
| Multi-INN JSON | schema broken: `{"mnn": {"a", "b"}}` (invalid JSON) |
| No evidence | no URL / confidence / status enum for cascade |

## Applicability to our MNN task

### Fit

- **Strong as catalog-conflict resolver** when trade name is clear and web has Vidal/ASNA-like hits: recovers МНН where scraper vote is garbage.
- **Latency OK for offline enrichment** (~5–7s) when it converges; competitive with DeepSeek tool-search bakeoff p50.
- **Self-hosted search** (SearXNG) avoids Serper/Exa/Polza spend and daily limits that blocked Qwen web-search resume.

### Not sufficient alone for cascade

1. **Reliability on hard tail:** ~35% of hard set aborts or returns non-JSON (loops / homeopathy / exotic INN).
2. **Contract too weak for Sem `attr_mnn`:** invalid multi format, reasoning leaks, no `status`/`evidence`/`source_url`.
3. **Completeness of combos** still shaky (Мальвацид; herbal lists differ from ГРЛС wording).
4. **Homeopathy / plant syrups / devices** — same dead zone as other web-MNN paths; need kind gate (`product_kind`) before calling.

### Recommended role in architecture

```
catalog win_mnn
  → if empty OR source-disagreement OR low-confidence vote
      → SearXNG Agent (or bakeoff DeepSeek+search) as enrichment
  → normalize RU INN + multi join
  → only merge when parse OK + (optional) source domain allowlist
```

Do **not** replace catalog competition for the easy majority; use SearXNG on the **conflict / empty / garbage-vote** slice (~каталог-only + conflict + both_empty from Wave-500 drugs).

### If we keep iterating this WF

1. Raise/tune `maxIterations`; add explicit stop: `not_found` after 2 empty searches.
2. Fix output contract: `{"mnn": string|null, "components":[...], "status":"found|not_found|conflict"}`.
3. Constrain SearXNG query: `site:vidal.ru OR site:rlsnet.ru OR site:grls.rosminzdrav.ru` (+ `kl=ru-ru`).
4. Post-process: strip tool-call prose; normalize salts (`гидрохлорид` → base INN policy).
5. Skip non-drug kinds before invoke.

## Bottom line

На проблемном хвосте из 20 позиций подход **рабочий как enrichment против битых каталогов** (чёткий brand→INN, ~2/3 успеха, быстрые hits), но **не готов как единственный источник МНН** в Sem-каскад: iteration aborts, кривой JSON, нет evidence, слабость на combo/herbal/homeopathy. Имеет смысл рядом с catalog vote и bakeoff — не вместо них.
