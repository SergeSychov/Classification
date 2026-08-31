/**
 * MNN Qwen Web Search — Build Prompt (n8n Code node / offline mirror).
 * Independent of catalog MNN fields. Spreads ...item.json.
 */
const PROMPT_VERSION = 'mnn_qwen_web_search_v1';

const SYSTEM_PROMPT = `Ты являешься верификатором MNN для российских аптечных товаров.

Твоя задача — использовать web search и определить международное непатентованное наименование
или основные действующие вещества только для конкретного лекарственного препарата.

Правила:

1. Используй результаты веб-поиска, а не только внутренние знания.
2. Сначала проверь идентичность товара:
   - торговое наименование / бренд;
   - лекарственную форму;
   - дозировку или концентрацию;
   - при необходимости путь введения.
3. Возвращай MNN только если найденный источник относится именно к этому товару
   или к той же лекарственной форме и дозировке.
4. Не подменяй MNN терапевтическим классом, нозологией, показанием,
   торговым наименованием или словом «комплекс».
5. Не угадывай MNN по памяти.
6. Если источники противоречат друг другу или не позволяют уверенно сопоставить товар,
   верни mnn=null и status="conflict" или status="not_found".
7. Для комбинированного лекарственного препарата можно вернуть главные вещества
   через " + ", только если они прямо указаны в найденном источнике.
8. Ответ должен быть только валидным JSON, без Markdown и без пояснений за пределами JSON.`;

function buildUserPrompt(row) {
  const v = (k) => {
    const x = row[k];
    if (x === null || x === undefined || String(x).trim() === '') return '—';
    return String(x).trim();
  };
  return `Определи MNN для следующего товара через web search.

Исходный товар:
- product_id: ${v('product_id')}
- normalized_text: ${v('normalized_text')}
- бренд / торговое наименование: ${v('attr_brand')}
- лекарственная форма: ${v('attr_dosage_form')}
- дозировка / концентрация: ${v('attr_dosage')}
- путь введения: ${v('attr_administration_route')}
- дополнительный семантический контекст: ${v('semantic_explanation')}

Приоритетно ищи в русскоязычных источниках, в том числе в каталогах:
Ютека, Еаптека, Apteka.ru, Здравсити, а также на сайтах производителей,
если они доступны в поиске.

Верни строго такой JSON:

{
  "mnn": "строка или null",
  "status": "found | not_found | conflict",
  "model_confidence": 0.0,
  "short_explanation": "краткое объяснение на русском",
  "identity_match": {
    "brand_match": true,
    "dosage_form_match": true,
    "dosage_match": true
  },
  "used_source_indexes": [1, 2],
  "evidence": "краткая формулировка, что именно источник сообщает о MNN"
}

Важно:
- mnn должен быть null, если нет достаточного подтверждения.
- model_confidence не является доказательством и не заменяет источник.
- used_source_indexes должны ссылаться только на реальные результаты поиска,
  возвращённые API.`;
}

function buildQueryHint(row) {
  const parts = [
    row.attr_brand,
    row.attr_dosage_form,
    row.attr_dosage,
    (row.normalized_text || '').split('|')[0],
  ]
    .map((x) => String(x || '').trim())
    .filter(Boolean);
  const q = parts.join(' ').replace(/\s+/g, ' ').trim();
  return q.slice(0, 160);
}

return items.map((item, index) => {
  const j = item.json || {};
  const user = buildUserPrompt(j);
  const searchPrompt = buildQueryHint(j);
  return {
    json: {
      ...j,
      qwen_search_prompt_version: PROMPT_VERSION,
      qwen_search_prompt_system: SYSTEM_PROMPT,
      qwen_search_prompt_user: user,
      qwen_search_query: searchPrompt,
      qwen_search_model: j.qwen_search_model || 'qwen/qwen3.5-flash-02-23@reasoning_effort=none',
      qwen_search_provider: 'polza',
      qwen_search_enabled: true,
    },
    pairedItem: item.pairedItem ?? { item: index },
  };
});
