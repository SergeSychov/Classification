# Human review — контракт очереди и Telegram

Связанные workflow (отдельно от `classification-stage2-dev`):

| Slug | Роль |
|------|------|
| `classification-human-review-enqueue` | Poller: `needs_human_review` → `classification_review_queue` |
| `classification-human-review-send` | Выдача карточек в Telegram |
| `classification-human-review-callback` | Inline callback → snapshot + log |

Настройки: таблица `pipeline_settings` (`telegram_review_chat_id`).

---

## 1. Статусы очереди `classification_review_queue.status`

| Статус | Значение |
|--------|----------|
| `pending` | В очереди, ещё не отправлено |
| `sending` | Захвачено send-workflow (claim), чтобы не слать дубли |
| `sent_to_telegram` | Сообщение отправлено (`telegram_message_id` заполнен) |
| `in_review` | Оператор нажал кнопку / идёт follow-up (например, «другая категория») |
| `resolved` | Approve или change с выбранной категорией |
| `unresolved` | Явно помечено как нерешённое |

Переходы: `pending` → `sent_to_telegram` → (`in_review`) → `resolved` | `unresolved`.

---

## 2. Payload карточки (`payload` jsonb)

Минимальный контракт при enqueue:

```json
{
  "product_id": 62,
  "product_raw_id": 100,
  "run_id": 42,
  "combined_text": "...",
  "product_name": "...",
  "shortlist_top": [
    {
      "category_id": 10,
      "category_code": "...",
      "category_name": "...",
      "score": 1.2,
      "direction": "...",
      "hierarchy_level": "...",
      "product_type": "...",
      "administration_route": "...",
      "age_segment": "...",
      "mnn_cluster": "...",
      "need_nosology": "...",
      "inclusion_comment": "...",
      "notes": "...",
      "include_keywords": ["..."],
      "exclude_keywords": ["..."]
    }
  ],
  "suggested_category": { "...": "тот же полный профиль категории" },
  "proposals": {
    "primary_llm": {"category_id": 10, "confidence": 0.55, "explanation": "..."},
    "fallback_2a": {"direction": "...", "block_family": "...", "confidence": 0.5},
    "fallback_2b": {"category_id": 12, "confidence": 0.6, "explanation": "..."},
    "judge": {"category_id": 12, "confidence": 0.65, "winner_source": "fallback_2b", "explanation": "..."}
  },
  "suggested_category_id": 12,
  "workflow_version": "stage2_judge_v1",
  "prompt_version": "prompt_judge_v1",
  "review_reason": "needs_human_review"
}
```

`suggested_category_id` — лучший кандидат для кнопки Approve (judge → 2B → P1 → top shortlist).

---

## 3. Кнопки Telegram (callback_data)

Лимит Telegram: 64 байта. Формат: `hr|<queue_id>|<action>[|<category_id>]`

| Action | callback_data | Эффект |
|--------|---------------|--------|
| approve | `hr\|{id}\|a` | `final_source=human`, `decision_status=classified`, category = suggested |
| change | `hr\|{id}\|c\|{category_id}` | то же с выбранным `category_id` из shortlist |
| other | `hr\|{id}\|o` | `in_review`; ждём текстовое сообщение с `category_id` |
| unresolved | `hr\|{id}\|u` | очередь `unresolved`, snapshot остаётся `needs_human_review` |

Текст follow-up для `other`: одно целое число — `category_id`.

---

## 4. Запись в БД при resolve

**Snapshot** (`product_classification`):

- `final_category_id`, `final_confidence` (1.0 при approve/change), `final_explanation`
- `final_source = 'human'`
- `decision_status = 'classified'` (approve/change) или `'needs_human_review'` (unresolved)
- `human_reviewer`, `human_comment`, `reviewed_at = now()`
- `next_action = 'none'`

**Log** (`product_classification_log`):

- `stage = 'human_review'`
- `actor_type = 'human'`
- `actor_name` = Telegram username / user id
- `status = 'success'` | `'unresolved'`
- `selected_category_id`, `confidence`, `explanation`
- `input_payload` / `output_payload` — callback + решение

**Очередь:** `status`, `resolved_at`, поля `resolution` / `resolved_category_id` (если есть в схеме).

---

## 5. Enqueue (poller)

`SELECT` из `product_classification` где `decision_status = 'needs_human_review'` и нет открытой строки в очереди (`pending` / `sent_to_telegram` / `in_review`).  
Не вшивать в `Fin — Close Run` / barrier Stage 2.

---

## 6. Settings

```sql
SELECT value->>'chat_id' FROM pipeline_settings WHERE key = 'telegram_review_chat_id';
```

Значение задаётся вручную (chat id оператора / группы).
