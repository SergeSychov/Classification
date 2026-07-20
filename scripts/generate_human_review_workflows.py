#!/usr/bin/env python3
"""Generate human-review n8n workflows (enqueue / send / callback)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path("/Users/serge/Developer/categories")
WF = ROOT / "workflows"
WF.mkdir(parents=True, exist_ok=True)

PG = {"postgres": {"id": "rcmpgUWgwB2BRYlW", "name": "Postgres account"}}
TG = {"telegramApi": {"id": "T48nEk1GS2E9PTHd", "name": "Telegram — SergeSychFirstTime_bot"}}


def nid() -> str:
    return str(uuid.uuid4())


def node(name, typ, params, pos, creds=None, type_version=1, **extra):
    n = {
        "parameters": params,
        "id": nid(),
        "name": name,
        "type": typ,
        "typeVersion": type_version,
        "position": pos,
    }
    if creds:
        n["credentials"] = creds
    n.update(extra)
    return n


ENQUEUE_SQL = r"""
WITH settings AS (
  SELECT NULLIF(TRIM(COALESCE(value->>'chat_id', '')), '') AS chat_id
  FROM pipeline_settings
  WHERE key = 'telegram_review_chat_id'
),
candidates AS (
  SELECT
    pc.product_id,
    pc.product_raw_id,
    pc.latest_run_id AS run_id,
    pc.workflow_version,
    pc.prompt_version,
    pc.llm_category_id,
    pc.llm_confidence,
    pc.llm_explanation,
    pc.fallback_2a_direction,
    pc.fallback_2a_block_family,
    pc.fallback_2a_confidence,
    pc.fallback_2a_explanation,
    pc.fallback_2b_category_id,
    pc.fallback_2b_confidence,
    pc.fallback_2b_explanation,
    pc.judge_category_id,
    pc.judge_confidence,
    pc.judge_explanation,
    pc.judge_raw_json,
    pc.final_category_id,
    pc.next_action,
    pp.combined_text,
    pp.product_name_effective AS product_name,
    cs.shortlist_json,
    COALESCE(
      pc.judge_category_id,
      pc.fallback_2b_category_id,
      pc.llm_category_id,
      pc.final_category_id,
      CASE
        WHEN jsonb_typeof(cs.shortlist_json) = 'array'
          THEN NULLIF(cs.shortlist_json->0->>'category_id', '')::bigint
        ELSE NULL
      END
    ) AS suggested_category_id
  FROM product_classification pc
  JOIN products_prepared pp ON pp.id = pc.product_id
  LEFT JOIN classification_shortlist cs
    ON cs.product_id = pc.product_id
   AND cs.stage = 'primary_rules'
  WHERE pc.decision_status = 'needs_human_review'
    AND NOT EXISTS (
      SELECT 1
      FROM classification_review_queue q
      WHERE q.product_id = pc.product_id
        AND q.status IN ('pending', 'sent_to_telegram', 'in_review')
    )
  ORDER BY pc.updated_at DESC
  LIMIT 50
)
INSERT INTO classification_review_queue (
  product_id,
  status,
  priority,
  review_reason,
  telegram_chat_id,
  run_id,
  payload
)
SELECT
  c.product_id,
  'pending',
  100,
  'needs_human_review',
  s.chat_id,
  c.run_id,
  jsonb_build_object(
    'product_id', c.product_id,
    'product_raw_id', c.product_raw_id,
    'run_id', c.run_id,
    'combined_text', COALESCE(c.combined_text, ''),
    'product_name', COALESCE(c.product_name, ''),
    'shortlist_top', COALESCE(
      (
        SELECT jsonb_agg(x)
        FROM (
          SELECT elem
          FROM jsonb_array_elements(COALESCE(c.shortlist_json, '[]'::jsonb)) WITH ORDINALITY AS t(elem, ord)
          ORDER BY ord
          LIMIT 5
        ) s(x)
      ),
      '[]'::jsonb
    ),
    'proposals', jsonb_build_object(
      'primary_llm', jsonb_strip_nulls(jsonb_build_object(
        'category_id', c.llm_category_id,
        'confidence', c.llm_confidence,
        'explanation', c.llm_explanation
      )),
      'fallback_2a', jsonb_strip_nulls(jsonb_build_object(
        'direction', c.fallback_2a_direction,
        'block_family', c.fallback_2a_block_family,
        'confidence', c.fallback_2a_confidence,
        'explanation', c.fallback_2a_explanation
      )),
      'fallback_2b', jsonb_strip_nulls(jsonb_build_object(
        'category_id', c.fallback_2b_category_id,
        'confidence', c.fallback_2b_confidence,
        'explanation', c.fallback_2b_explanation
      )),
      'judge', jsonb_strip_nulls(jsonb_build_object(
        'category_id', c.judge_category_id,
        'confidence', c.judge_confidence,
        'explanation', c.judge_explanation,
        'winner_source', c.judge_raw_json->>'winner_source'
      ))
    ),
    'suggested_category_id', c.suggested_category_id,
    'workflow_version', c.workflow_version,
    'prompt_version', c.prompt_version,
    'review_reason', 'needs_human_review'
  )
FROM candidates c
CROSS JOIN settings s
RETURNING id, product_id, status, run_id, telegram_chat_id, payload;
"""


SEND_FORMAT_JS = r"""
function clip(s, n) {
  const t = String(s || '').replace(/\s+/g, ' ').trim();
  if (t.length <= n) return t;
  return t.slice(0, n - 1) + '…';
}

function fmtProp(label, p) {
  if (!p || typeof p !== 'object') return null;
  const parts = [];
  if (p.category_id != null) parts.push(`cat=${p.category_id}`);
  if (p.direction) parts.push(`dir=${p.direction}`);
  if (p.block_family) parts.push(`block=${p.block_family}`);
  if (p.confidence != null) parts.push(`conf=${p.confidence}`);
  if (p.winner_source) parts.push(`winner=${p.winner_source}`);
  if (p.explanation) parts.push(clip(p.explanation, 120));
  if (!parts.length) return null;
  return `• ${label}: ${parts.join(' | ')}`;
}

const settingsChat = String($('HR — Load Settings').first().json.chat_id || '').trim();

return items.map((item) => {
  const row = item.json;
  const payload = typeof row.payload === 'string' ? JSON.parse(row.payload) : (row.payload || {});
  const qid = Number(row.id);
  const chatId = String(row.telegram_chat_id || settingsChat || '').trim();
  const shortlist = Array.isArray(payload.shortlist_top) ? payload.shortlist_top : [];
  const proposals = payload.proposals || {};
  const suggested = payload.suggested_category_id;

  const lines = [
    `🧾 Review #${qid} · product ${payload.product_id}`,
    `run_id=${payload.run_id || row.run_id || '—'}`,
    '',
    clip(payload.product_name || payload.combined_text || '—', 280),
    '',
  ];

  for (const label of ['judge', 'fallback_2b', 'primary_llm', 'fallback_2a']) {
    const line = fmtProp(label, proposals[label]);
    if (line) lines.push(line);
  }

  if (shortlist.length) {
    lines.push('', 'Shortlist:');
    shortlist.slice(0, 5).forEach((c, i) => {
      lines.push(`${i + 1}. ${c.category_id}: ${clip(c.category_name || c.category_code || '', 60)}`);
    });
  }

  lines.push('', `Suggested: ${suggested ?? '—'}`);

  const keyboard = {
    inline_keyboard: [
      [
        { text: '✅ Approve', callback_data: `hr|${qid}|a` },
        { text: '❓ Unresolved', callback_data: `hr|${qid}|u` },
      ],
    ],
  };

  const changeRow = [];
  for (const c of shortlist.slice(0, 4)) {
    const cid = Number(c.category_id);
    if (!Number.isFinite(cid)) continue;
    changeRow.push({
      text: `→ ${cid}`,
      callback_data: `hr|${qid}|c|${cid}`,
    });
  }
  changeRow.push({ text: '✏️ Other', callback_data: `hr|${qid}|o` });
  keyboard.inline_keyboard.push(changeRow);

  return {
    json: {
      queue_id: qid,
      product_id: payload.product_id,
      telegram_chat_id: chatId,
      message_text: lines.join('\n'),
      reply_markup: keyboard,
      skip: !chatId,
      skip_reason: chatId ? null : 'missing_telegram_chat_id',
    },
  };
});
"""


SEND_PREPARE_HTTP_JS = r"""
async function getBotToken() {
  try {
    const creds = await this.getCredentials('telegramApi');
    return creds?.accessToken || creds?.apiKey || creds?.token || null;
  } catch (_) {
    return null;
  }
}

const token = await getBotToken.call(this);
if (!token) {
  return [{ json: { ok: false, error: 'missing_telegram_credential', skip: true } }];
}

const out = [];
for (const item of items) {
  const j = item.json;
  if (j.skip) {
    out.push({ json: { ...j, ok: false, error: j.skip_reason || 'skipped' } });
    continue;
  }
  out.push({
    json: {
      queue_id: j.queue_id,
      product_id: j.product_id,
      telegram_chat_id: j.telegram_chat_id,
      method: 'POST',
      url: `https://api.telegram.org/bot${token}/sendMessage`,
      body: {
        chat_id: j.telegram_chat_id,
        text: j.message_text,
        reply_markup: j.reply_markup,
        disable_web_page_preview: true,
      },
    },
  });
}
return out;
"""


CALLBACK_PARSE_JS = r"""
const update = items[0].json;
const cb = update.callback_query;
const msg = update.message || update.edited_message;

if (cb) {
  const data = String(cb.data || '');
  const parts = data.split('|');
  if (parts[0] !== 'hr' || parts.length < 3) {
    return [{ json: { ok: false, error: 'unknown_callback', raw: data } }];
  }
  const queue_id = Number(parts[1]);
  const action = parts[2];
  const category_id = parts[3] != null ? Number(parts[3]) : null;
  const from = cb.from || {};
  const chat = cb.message?.chat || {};
  return [{
    json: {
      ok: true,
      kind: 'callback',
      queue_id,
      action,
      category_id: Number.isFinite(category_id) ? category_id : null,
      callback_query_id: cb.id,
      telegram_user_id: String(from.id || ''),
      telegram_username: from.username || from.first_name || String(from.id || ''),
      telegram_chat_id: String(chat.id || ''),
      telegram_message_id: cb.message?.message_id != null ? String(cb.message.message_id) : null,
    },
  }];
}

if (msg && msg.text) {
  const text = String(msg.text).trim();
  const from = msg.from || {};
  const chat = msg.chat || {};
  // follow-up: plain category_id while queue is in_review for this chat
  const cat = Number(text);
  return [{
    json: {
      ok: true,
      kind: 'text',
      action: 'other_text',
      category_id: Number.isFinite(cat) ? Math.trunc(cat) : null,
      raw_text: text,
      telegram_user_id: String(from.id || ''),
      telegram_username: from.username || from.first_name || String(from.id || ''),
      telegram_chat_id: String(chat.id || ''),
      telegram_message_id: msg.message_id != null ? String(msg.message_id) : null,
    },
  }];
}

return [{ json: { ok: false, error: 'unsupported_update' } }];
"""


CALLBACK_RESOLVE_JS = r"""
const ev = items[0].json;
if (!ev.ok) return [{ json: ev }];

const queue = $('HR — Load Queue Row').first()?.json || {};
const payload = typeof queue.payload === 'string' ? JSON.parse(queue.payload || '{}') : (queue.payload || {});

let action = ev.action;
let categoryId = ev.category_id;
let decision = 'needs_human_review';
let queueStatus = 'unresolved';
let resolution = action;
let explanation = '';

if (ev.kind === 'text') {
  if (!queue.id) {
    return [{ json: { ok: false, error: 'no_open_in_review_for_chat' } }];
  }
  if (categoryId == null) {
    return [{
      json: {
        ok: false,
        error: 'expected_category_id_number',
        telegram_chat_id: ev.telegram_chat_id,
        reply_text: 'Пришлите число category_id или нажмите кнопку на карточке.',
      },
    }];
  }
  action = 'change';
  resolution = 'change';
}

if (action === 'a' || action === 'approve') {
  categoryId = categoryId ?? (payload.suggested_category_id != null ? Number(payload.suggested_category_id) : null);
  if (categoryId == null) {
    return [{ json: { ok: false, error: 'no_suggested_category', queue_id: queue.id } }];
  }
  decision = 'classified';
  queueStatus = 'resolved';
  resolution = 'approve';
  explanation = `Approved suggested category_id=${categoryId}`;
} else if (action === 'c' || action === 'change') {
  if (categoryId == null) {
    return [{ json: { ok: false, error: 'missing_category_id', queue_id: queue.id } }];
  }
  decision = 'classified';
  queueStatus = 'resolved';
  resolution = 'change';
  explanation = `Changed to category_id=${categoryId}`;
} else if (action === 'u' || action === 'unresolved') {
  categoryId = null;
  decision = 'needs_human_review';
  queueStatus = 'unresolved';
  resolution = 'unresolved';
  explanation = 'Marked unresolved by reviewer';
} else if (action === 'o' || action === 'other') {
  return [{
    json: {
      ok: true,
      mode: 'await_other',
      queue_id: Number(queue.id),
      product_id: Number(queue.product_id),
      telegram_chat_id: ev.telegram_chat_id,
      callback_query_id: ev.callback_query_id,
      telegram_username: ev.telegram_username,
      reply_text: `Ок. Пришлите category_id числом для product ${queue.product_id} (queue #${queue.id}).`,
    },
  }];
} else {
  return [{ json: { ok: false, error: 'unknown_action', action } }];
}

const productId = Number(queue.product_id || payload.product_id);
const runId = queue.run_id != null ? Number(queue.run_id) : (payload.run_id != null ? Number(payload.run_id) : null);

return [{
  json: {
    ok: true,
    mode: 'resolve',
    queue_id: Number(queue.id),
    product_id: productId,
    product_raw_id: payload.product_raw_id != null ? Number(payload.product_raw_id) : null,
    run_id: runId,
    category_id: categoryId,
    decision_status: decision,
    queue_status: queueStatus,
    resolution,
    explanation,
    human_reviewer: ev.telegram_username,
    human_comment: explanation,
    callback_query_id: ev.callback_query_id || null,
    telegram_chat_id: ev.telegram_chat_id,
    telegram_message_id: ev.telegram_message_id,
    workflow_version: payload.workflow_version || 'stage2_human_review_v1',
    prompt_version: payload.prompt_version || 'prompt_human_review_v1',
    input_payload: ev,
  },
}];
"""


def conn(src, dst, src_out="main", dst_in=0):
    return src, {src_out: [[{"node": dst, "type": "main", "index": dst_in}]]}


def build_connections(pairs):
    out = {}
    for src, dst, *rest in pairs:
        src_out = rest[0] if rest else "main"
        dst_in = rest[1] if len(rest) > 1 else 0
        out.setdefault(src, {}).setdefault(src_out, []).append(
            [{"node": dst, "type": "main", "index": dst_in}]
        )
    # n8n format: each output index is a list of lists of links
    # Fix: multiple links from same output should be in same branch array or separate?
    # Standard: connections[src][main] = [ [link1, link2] ] for parallel, or [[link1],[link2]] for split
    # For sequential chain we use [[ {node} ]]
    fixed = {}
    for src, ports in out.items():
        fixed[src] = {}
        for port, batches in ports.items():
            # each append created a separate batch; merge into one sequential? 
            # For linear: each source has one target → one batch with one link
            # If multiple targets from same output (parallel), one batch with multiple links
            links = [link for batch in batches for link in batch]
            fixed[src][port] = [links] if len(links) > 1 and False else [[l] for l in links]
            # Actually for 1:1 chain, [[link]] is correct (one item path)
            # For fan-out parallel same data: [ [link1, link2] ]
            if len(links) == 1:
                fixed[src][port] = [[links[0]]]
            else:
                # assume sequential wrong - for our chains all 1:1
                # If we registered multiple destinations from same node as separate pairs, treat as parallel fan-out
                fixed[src][port] = [[l for l in links]]
    return fixed


def linear_connections(names):
    c = {}
    for a, b in zip(names, names[1:]):
        c[a] = {"main": [[{"node": b, "type": "main", "index": 0}]]}
    return c


def write_wf(slug, name, nodes, connections, active=False):
    path = WF / f"{slug}.json"
    doc = {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "active": active,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)


# --- ENQUEUE ---
enq_nodes = [
    node("HR — Manual Trigger", "n8n-nodes-base.manualTrigger", {}, [0, 0], type_version=1),
    node(
        "HR — Schedule",
        "n8n-nodes-base.scheduleTrigger",
        {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}},
        [0, 160],
        type_version=1.2,
    ),
    node(
        "HR — Enqueue Pending",
        "n8n-nodes-base.postgres",
        {"operation": "executeQuery", "query": ENQUEUE_SQL, "options": {}},
        [280, 80],
        creds=PG,
        type_version=2.5,
    ),
]
write_wf(
    "classification-human-review-enqueue",
    "classification-human-review-enqueue",
    enq_nodes,
    {
        "HR — Manual Trigger": {"main": [[{"node": "HR — Enqueue Pending", "type": "main", "index": 0}]]},
        "HR — Schedule": {"main": [[{"node": "HR — Enqueue Pending", "type": "main", "index": 0}]]},
    },
)

# --- SEND ---
send_nodes = [
    node("HR — Manual Trigger", "n8n-nodes-base.manualTrigger", {}, [0, 0]),
    node(
        "HR — Schedule",
        "n8n-nodes-base.scheduleTrigger",
        {"rule": {"interval": [{"field": "minutes", "minutesInterval": 2}]}},
        [0, 160],
        type_version=1.2,
    ),
    node(
        "HR — Load Settings",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": "SELECT COALESCE(value->>'chat_id','') AS chat_id FROM pipeline_settings WHERE key = 'telegram_review_chat_id';",
            "options": {},
        },
        [220, 80],
        creds=PG,
        type_version=2.5,
    ),
    node(
        "HR — Select Pending",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": """SELECT id, product_id, run_id, telegram_chat_id, payload, status, priority, created_at
FROM classification_review_queue
WHERE status = 'pending'
ORDER BY priority ASC, created_at ASC
LIMIT 10;""",
            "options": {},
        },
        [440, 80],
        creds=PG,
        type_version=2.5,
    ),
    node("HR — Format Card", "n8n-nodes-base.code", {"jsCode": SEND_FORMAT_JS}, [660, 80], type_version=2),
    node(
        "HR — Prepare Telegram HTTP",
        "n8n-nodes-base.code",
        {"jsCode": SEND_PREPARE_HTTP_JS},
        [880, 80],
        creds=TG,
        type_version=2,
    ),
    node(
        "HR — Skip Empty?",
        "n8n-nodes-base.if",
        {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [
                    {
                        "id": "c1",
                        "leftValue": "={{ $json.skip }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        [1080, 80],
        type_version=2.2,
    ),
    node(
        "HR — Send Telegram",
        "n8n-nodes-base.httpRequest",
        {
            "method": "={{ $json.method }}",
            "url": "={{ $json.url }}",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {},
        },
        [1300, 200],
        type_version=4.2,
    ),
    node(
        "HR — Mark Sent",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": """UPDATE classification_review_queue
SET
  status = 'sent_to_telegram',
  sent_at = NOW(),
  telegram_chat_id = COALESCE(telegram_chat_id, '{{ $json.result?.chat?.id || $('HR — Prepare Telegram HTTP').item.json.telegram_chat_id }}'),
  telegram_message_id = COALESCE('{{ $json.result?.message_id || $json.message_id }}', telegram_message_id)
WHERE id = {{ Number($('HR — Prepare Telegram HTTP').item.json.queue_id) }}
  AND status = 'pending'
RETURNING id, product_id, status, telegram_message_id;""",
            "options": {},
        },
        [1520, 200],
        creds=PG,
        type_version=2.5,
    ),
]
write_wf(
    "classification-human-review-send",
    "classification-human-review-send",
    send_nodes,
    {
        "HR — Manual Trigger": {"main": [[{"node": "HR — Load Settings", "type": "main", "index": 0}]]},
        "HR — Schedule": {"main": [[{"node": "HR — Load Settings", "type": "main", "index": 0}]]},
        "HR — Load Settings": {"main": [[{"node": "HR — Select Pending", "type": "main", "index": 0}]]},
        "HR — Select Pending": {"main": [[{"node": "HR — Format Card", "type": "main", "index": 0}]]},
        "HR — Format Card": {"main": [[{"node": "HR — Prepare Telegram HTTP", "type": "main", "index": 0}]]},
        "HR — Prepare Telegram HTTP": {"main": [[{"node": "HR — Skip Empty?", "type": "main", "index": 0}]]},
        # IF true (skip) → nowhere; false → send
        "HR — Skip Empty?": {
            "main": [
                [],  # true: skip
                [{"node": "HR — Send Telegram", "type": "main", "index": 0}],  # false
            ]
        },
        "HR — Send Telegram": {"main": [[{"node": "HR — Mark Sent", "type": "main", "index": 0}]]},
    },
)

# --- CALLBACK ---
# Load queue: for callback by queue_id; for text by chat + in_review
LOAD_QUEUE_SQL = r"""
{% if $json.kind === 'callback' %}
SELECT *
FROM classification_review_queue
WHERE id = {{ Number($json.queue_id) }}
LIMIT 1;
{% else %}
SELECT *
FROM classification_review_queue
WHERE telegram_chat_id = '{{ $json.telegram_chat_id }}'
  AND status = 'in_review'
ORDER BY updated_at DESC NULLS LAST, created_at DESC
LIMIT 1;
{% endif %}
"""

# n8n postgres may not support that templating - use Code to pick query or two IF branches.
# Simpler: always pass queue_id from parse for callback; for text use separate SQL node after IF.

cb_nodes = [
    node(
        "HR — Telegram Trigger",
        "n8n-nodes-base.telegramTrigger",
        {"updates": ["callback_query", "message"], "additionalFields": {}},
        [0, 0],
        creds=TG,
        type_version=1.1,
        webhookId=str(uuid.uuid4()),
    ),
    node("HR — Parse Update", "n8n-nodes-base.code", {"jsCode": CALLBACK_PARSE_JS}, [220, 0], type_version=2),
    node(
        "HR — Is Callback?",
        "n8n-nodes-base.if",
        {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [
                    {
                        "id": "c1",
                        "leftValue": "={{ $json.kind }}",
                        "rightValue": "callback",
                        "operator": {"type": "string", "operation": "equals"},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        [440, 0],
        type_version=2.2,
    ),
    node(
        "HR — Load Queue By Id",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": "SELECT * FROM classification_review_queue WHERE id = {{ Number($json.queue_id) }} LIMIT 1;",
            "options": {},
        },
        [680, -120],
        creds=PG,
        type_version=2.5,
    ),
    node(
        "HR — Load Queue By Chat",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": """SELECT * FROM classification_review_queue
WHERE telegram_chat_id = '{{ $json.telegram_chat_id }}'
  AND status = 'in_review'
ORDER BY created_at DESC
LIMIT 1;""",
            "options": {},
        },
        [680, 120],
        creds=PG,
        type_version=2.5,
    ),
    node(
        "HR — Merge Event Context",
        "n8n-nodes-base.code",
        {
            "jsCode": """
const ev = $('HR — Parse Update').first().json;
const queueItem = items[0]?.json || {};
// postgres may return the row directly
const queue = queueItem.id ? queueItem : {};
return [{ json: { event: ev, queue } }];
"""
        },
        [900, 0],
        type_version=2,
    ),
    node(
        "HR — Resolve Decision",
        "n8n-nodes-base.code",
        {
            "jsCode": """
const wrapped = items[0].json;
const ev = wrapped.event || $('HR — Parse Update').first().json;
const queue = wrapped.queue || {};
if (!ev.ok) return [{ json: ev }];

const payload = typeof queue.payload === 'string' ? JSON.parse(queue.payload || '{}') : (queue.payload || {});

let action = ev.action;
let categoryId = ev.category_id;
let decision = 'needs_human_review';
let queueStatus = 'unresolved';
let resolution = action;
let explanation = '';

if (ev.kind === 'text') {
  if (!queue.id) {
    return [{ json: { ok: false, error: 'no_open_in_review_for_chat', telegram_chat_id: ev.telegram_chat_id } }];
  }
  if (categoryId == null) {
    return [{
      json: {
        ok: false,
        error: 'expected_category_id_number',
        telegram_chat_id: ev.telegram_chat_id,
        reply_text: 'Пришлите число category_id или нажмите кнопку на карточке.',
        mode: 'reply_only',
      },
    }];
  }
  action = 'change';
  resolution = 'change';
}

if (action === 'a') {
  categoryId = payload.suggested_category_id != null ? Number(payload.suggested_category_id) : null;
  if (categoryId == null) return [{ json: { ok: false, error: 'no_suggested_category', queue_id: queue.id } }];
  decision = 'classified';
  queueStatus = 'resolved';
  resolution = 'approve';
  explanation = `Approved suggested category_id=${categoryId}`;
} else if (action === 'c' || action === 'change') {
  if (categoryId == null) return [{ json: { ok: false, error: 'missing_category_id', queue_id: queue.id } }];
  decision = 'classified';
  queueStatus = 'resolved';
  resolution = 'change';
  explanation = `Changed to category_id=${categoryId}`;
} else if (action === 'u') {
  categoryId = null;
  decision = 'needs_human_review';
  queueStatus = 'unresolved';
  resolution = 'unresolved';
  explanation = 'Marked unresolved by reviewer';
} else if (action === 'o') {
  return [{
    json: {
      ok: true,
      mode: 'await_other',
      queue_id: Number(queue.id),
      product_id: Number(queue.product_id),
      telegram_chat_id: ev.telegram_chat_id,
      callback_query_id: ev.callback_query_id,
      telegram_username: ev.telegram_username,
      reply_text: `Ок. Пришлите category_id числом для product ${queue.product_id} (queue #${queue.id}).`,
    },
  }];
} else {
  return [{ json: { ok: false, error: 'unknown_action', action } }];
}

return [{
  json: {
    ok: true,
    mode: 'resolve',
    queue_id: Number(queue.id),
    product_id: Number(queue.product_id || payload.product_id),
    product_raw_id: payload.product_raw_id != null ? Number(payload.product_raw_id) : null,
    run_id: queue.run_id != null ? Number(queue.run_id) : (payload.run_id != null ? Number(payload.run_id) : null),
    category_id: categoryId,
    decision_status: decision,
    queue_status: queueStatus,
    resolution,
    explanation,
    human_reviewer: ev.telegram_username,
    human_comment: explanation,
    callback_query_id: ev.callback_query_id || null,
    telegram_chat_id: ev.telegram_chat_id,
    telegram_message_id: ev.telegram_message_id,
    workflow_version: payload.workflow_version || 'stage2_human_review_v1',
    prompt_version: payload.prompt_version || 'prompt_human_review_v1',
    input_payload_json: JSON.stringify(ev),
  },
}];
"""
        },
        [1120, 0],
        type_version=2,
    ),
    node(
        "HR — Mode Switch",
        "n8n-nodes-base.switch",
        {
            "rules": {
                "values": [
                    {
                        "conditions": {
                            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [
                                {
                                    "leftValue": "={{ $json.mode }}",
                                    "rightValue": "resolve",
                                    "operator": {"type": "string", "operation": "equals"},
                                }
                            ],
                            "combinator": "and",
                        },
                        "renameOutput": True,
                        "outputKey": "resolve",
                    },
                    {
                        "conditions": {
                            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [
                                {
                                    "leftValue": "={{ $json.mode }}",
                                    "rightValue": "await_other",
                                    "operator": {"type": "string", "operation": "equals"},
                                }
                            ],
                            "combinator": "and",
                        },
                        "renameOutput": True,
                        "outputKey": "await_other",
                    },
                    {
                        "conditions": {
                            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                            "conditions": [
                                {
                                    "leftValue": "={{ $json.mode }}",
                                    "rightValue": "reply_only",
                                    "operator": {"type": "string", "operation": "equals"},
                                }
                            ],
                            "combinator": "and",
                        },
                        "renameOutput": True,
                        "outputKey": "reply_only",
                    },
                ]
            },
            "options": {},
        },
        [1340, 0],
        type_version=3.2,
    ),
    node(
        "HR — Mark In Review",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": """UPDATE classification_review_queue
SET status = 'in_review', telegram_chat_id = COALESCE(telegram_chat_id, '{{ $json.telegram_chat_id }}')
WHERE id = {{ Number($json.queue_id) }}
RETURNING id, status;""",
            "options": {},
        },
        [1580, 80],
        creds=PG,
        type_version=2.5,
    ),
    node(
        "HR — Upsert Snapshot",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": """INSERT INTO product_classification AS pc (
  product_id,
  product_raw_id,
  latest_run_id,
  final_category_id,
  final_confidence,
  final_explanation,
  final_source,
  decision_status,
  human_reviewer,
  human_comment,
  reviewed_at,
  next_action,
  workflow_version,
  prompt_version,
  updated_at
) VALUES (
  {{ Number($json.product_id) }},
  {{ $json.product_raw_id != null ? Number($json.product_raw_id) : 'NULL' }},
  {{ $json.run_id != null ? Number($json.run_id) : 'NULL' }},
  {{ $json.category_id != null ? Number($json.category_id) : 'NULL' }},
  {{ $json.decision_status === 'classified' ? 1.0 : 'NULL' }},
  '{{ ($json.explanation || '').replace(/'/g, "''") }}',
  'human',
  '{{ $json.decision_status }}',
  '{{ ($json.human_reviewer || '').replace(/'/g, "''") }}',
  '{{ ($json.human_comment || '').replace(/'/g, "''") }}',
  NOW(),
  'none',
  '{{ ($json.workflow_version || '').replace(/'/g, "''") }}',
  '{{ ($json.prompt_version || '').replace(/'/g, "''") }}',
  NOW()
)
ON CONFLICT (product_id) DO UPDATE SET
  product_raw_id = COALESCE(EXCLUDED.product_raw_id, pc.product_raw_id),
  latest_run_id = COALESCE(EXCLUDED.latest_run_id, pc.latest_run_id),
  final_category_id = EXCLUDED.final_category_id,
  final_confidence = EXCLUDED.final_confidence,
  final_explanation = EXCLUDED.final_explanation,
  final_source = EXCLUDED.final_source,
  decision_status = EXCLUDED.decision_status,
  human_reviewer = EXCLUDED.human_reviewer,
  human_comment = EXCLUDED.human_comment,
  reviewed_at = EXCLUDED.reviewed_at,
  next_action = EXCLUDED.next_action,
  workflow_version = COALESCE(EXCLUDED.workflow_version, pc.workflow_version),
  prompt_version = COALESCE(EXCLUDED.prompt_version, pc.prompt_version),
  updated_at = NOW()
RETURNING product_id, decision_status, final_source, final_category_id;""",
            "options": {},
        },
        [1580, -160],
        creds=PG,
        type_version=2.5,
    ),
    node(
        "HR — Insert Log",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": """INSERT INTO product_classification_log (
  run_id,
  product_id,
  product_raw_id,
  stage,
  actor_type,
  actor_name,
  status,
  input_payload,
  output_payload,
  selected_category_id,
  confidence,
  explanation,
  validation_passed,
  decision_status,
  next_action,
  workflow_version,
  prompt_version
) VALUES (
  {{ $json.run_id != null ? Number($json.run_id) : 'NULL' }},
  {{ Number($json.product_id) }},
  {{ $json.product_raw_id != null ? Number($json.product_raw_id) : 'NULL' }},
  'human_review',
  'human',
  '{{ ($json.human_reviewer || '').replace(/'/g, "''") }}',
  '{{ $json.queue_status === 'unresolved' ? 'unresolved' : 'success' }}',
  '{{ ($json.input_payload_json || '{}').replace(/'/g, "''") }}'::jsonb,
  jsonb_build_object(
    'resolution', '{{ $json.resolution }}',
    'queue_id', {{ Number($json.queue_id) }},
    'category_id', {{ $json.category_id != null ? Number($json.category_id) : 'null' }}
  ),
  {{ $json.category_id != null ? Number($json.category_id) : 'NULL' }},
  {{ $json.decision_status === 'classified' ? 1.0 : 'NULL' }},
  '{{ ($json.explanation || '').replace(/'/g, "''") }}',
  true,
  '{{ $json.decision_status }}',
  'none',
  '{{ ($json.workflow_version || '').replace(/'/g, "''") }}',
  '{{ ($json.prompt_version || '').replace(/'/g, "''") }}'
)
RETURNING id, product_id, stage;""",
            "options": {},
        },
        [1800, -160],
        creds=PG,
        type_version=2.5,
    ),
    node(
        "HR — Close Queue",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": """UPDATE classification_review_queue
SET
  status = '{{ $json.queue_status }}',
  resolution = '{{ $json.resolution }}',
  resolved_category_id = {{ $json.category_id != null ? Number($json.category_id) : 'NULL' }},
  resolved_at = NOW(),
  classification_log_id = {{ $('HR — Insert Log').first().json.id ? Number($('HR — Insert Log').first().json.id) : 'NULL' }}
WHERE id = {{ Number($json.queue_id) }}
RETURNING id, status, resolution, resolved_category_id;""",
            "options": {},
        },
        [2020, -160],
        creds=PG,
        type_version=2.5,
    ),
    node(
        "HR — Prepare TG Reply",
        "n8n-nodes-base.code",
        {
            "jsCode": """
async function getBotToken() {
  try {
    const creds = await this.getCredentials('telegramApi');
    return creds?.accessToken || creds?.apiKey || creds?.token || null;
  } catch (_) {
    return null;
  }
}
const token = await getBotToken.call(this);
const j = items[0].json;
const chatId = j.telegram_chat_id;
const text = j.reply_text || (
  j.mode === 'resolve'
    ? `Готово: ${j.resolution} · product ${j.product_id} · cat=${j.category_id ?? '—'} · ${j.decision_status}`
    : (j.error || 'ok')
);
const reqs = [];
if (token && j.callback_query_id) {
  reqs.push({
    method: 'POST',
    url: `https://api.telegram.org/bot${token}/answerCallbackQuery`,
    body: { callback_query_id: j.callback_query_id, text: String(text).slice(0, 180) },
  });
}
if (token && chatId) {
  reqs.push({
    method: 'POST',
    url: `https://api.telegram.org/bot${token}/sendMessage`,
    body: { chat_id: chatId, text: String(text).slice(0, 3500) },
  });
}
if (!reqs.length) return [{ json: { ok: false, error: 'no_telegram_out', ...j } }];
return reqs.map((r) => ({ json: { ...j, ...r } }));
"""
        },
        [2240, 0],
        creds=TG,
        type_version=2,
    ),
    node(
        "HR — Telegram HTTP",
        "n8n-nodes-base.httpRequest",
        {
            "method": "={{ $json.method }}",
            "url": "={{ $json.url }}",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {},
        },
        [2460, 0],
        type_version=4.2,
    ),
]

# Fix Upsert/Insert/Close to pass through decision fields - postgres RETURNING loses mode fields.
# Need Merge or Code after each SQL to reattach. Simpler: one SQL CTE doing all three.

# Replace Upsert/Insert/Close with single CTE node for reliability
cb_nodes = [n for n in cb_nodes if n["name"] not in (
    "HR — Upsert Snapshot", "HR — Insert Log", "HR — Close Queue"
)]

RESOLVE_SQL = r"""
WITH snap AS (
  INSERT INTO product_classification AS pc (
    product_id, product_raw_id, latest_run_id,
    final_category_id, final_confidence, final_explanation,
    final_source, decision_status, human_reviewer, human_comment, reviewed_at,
    next_action, workflow_version, prompt_version, updated_at
  ) VALUES (
    {{ Number($json.product_id) }},
    {{ $json.product_raw_id != null && $json.product_raw_id !== '' ? Number($json.product_raw_id) : 'NULL' }},
    {{ $json.run_id != null && $json.run_id !== '' ? Number($json.run_id) : 'NULL' }},
    {{ $json.category_id != null && $json.category_id !== '' ? Number($json.category_id) : 'NULL' }},
    {{ $json.decision_status === 'classified' ? '1.0' : 'NULL' }},
    $json.explanation,
    'human',
    '{{ $json.decision_status }}',
    $json.human_reviewer,
    $json.human_comment,
    NOW(),
    'none',
    $json.workflow_version,
    $json.prompt_version,
    NOW()
  )
  ON CONFLICT (product_id) DO UPDATE SET
    product_raw_id = COALESCE(EXCLUDED.product_raw_id, pc.product_raw_id),
    latest_run_id = COALESCE(EXCLUDED.latest_run_id, pc.latest_run_id),
    final_category_id = EXCLUDED.final_category_id,
    final_confidence = EXCLUDED.final_confidence,
    final_explanation = EXCLUDED.final_explanation,
    final_source = 'human',
    decision_status = EXCLUDED.decision_status,
    human_reviewer = EXCLUDED.human_reviewer,
    human_comment = EXCLUDED.human_comment,
    reviewed_at = NOW(),
    next_action = 'none',
    workflow_version = COALESCE(EXCLUDED.workflow_version, pc.workflow_version),
    prompt_version = COALESCE(EXCLUDED.prompt_version, pc.prompt_version),
    updated_at = NOW()
  RETURNING product_id
),
log_ins AS (
  INSERT INTO product_classification_log (
    run_id, product_id, product_raw_id, stage, actor_type, actor_name, status,
    input_payload, output_payload, selected_category_id, confidence, explanation,
    validation_passed, decision_status, next_action, workflow_version, prompt_version
  ) VALUES (
    {{ $json.run_id != null && $json.run_id !== '' ? Number($json.run_id) : 'NULL' }},
    {{ Number($json.product_id) }},
    {{ $json.product_raw_id != null && $json.product_raw_id !== '' ? Number($json.product_raw_id) : 'NULL' }},
    'human_review',
    'human',
    $json.human_reviewer,
    '{{ $json.queue_status === 'unresolved' ? 'unresolved' : 'success' }}',
    COALESCE($json.input_payload_json::jsonb, '{}'::jsonb),
    jsonb_build_object(
      'resolution', '{{ $json.resolution }}',
      'queue_id', {{ Number($json.queue_id) }},
      'category_id', {{ $json.category_id != null && $json.category_id !== '' ? Number($json.category_id) : 'null' }}
    ),
    {{ $json.category_id != null && $json.category_id !== '' ? Number($json.category_id) : 'NULL' }},
    {{ $json.decision_status === 'classified' ? '1.0' : 'NULL' }},
    $json.explanation,
    true,
    '{{ $json.decision_status }}',
    'none',
    $json.workflow_version,
    $json.prompt_version
  )
  RETURNING id
),
q AS (
  UPDATE classification_review_queue
  SET
    status = '{{ $json.queue_status }}',
    resolution = '{{ $json.resolution }}',
    resolved_category_id = {{ $json.category_id != null && $json.category_id !== '' ? Number($json.category_id) : 'NULL' }},
    resolved_at = NOW(),
    classification_log_id = (SELECT id FROM log_ins)
  WHERE id = {{ Number($json.queue_id) }}
  RETURNING id, status, resolution, resolved_category_id
)
SELECT q.*, (SELECT id FROM log_ins) AS log_id, (SELECT product_id FROM snap) AS product_id
FROM q;
"""

# n8n postgres query expressions for strings are painful with $json.field.
# Use a Code node that builds a safe parameterized-like query string instead.

cb_nodes.append(
    node(
        "HR — Apply Resolve SQL",
        "n8n-nodes-base.code",
        {
            "jsCode": r"""
function sqlStr(v) {
  if (v === null || v === undefined) return 'NULL';
  return "'" + String(v).replace(/'/g, "''") + "'";
}
function sqlNum(v) {
  if (v === null || v === undefined || v === '') return 'NULL';
  const n = Number(v);
  return Number.isFinite(n) ? String(n) : 'NULL';
}

const j = items[0].json;
if (!j.ok || j.mode !== 'resolve') return [{ json: j }];

const classified = j.decision_status === 'classified';
const logStatus = j.queue_status === 'unresolved' ? 'unresolved' : 'success';
const inputJson = j.input_payload_json || '{}';

const query = `
WITH snap AS (
  INSERT INTO product_classification AS pc (
    product_id, product_raw_id, latest_run_id,
    final_category_id, final_confidence, final_explanation,
    final_source, decision_status, human_reviewer, human_comment, reviewed_at,
    next_action, workflow_version, prompt_version, updated_at
  ) VALUES (
    ${sqlNum(j.product_id)},
    ${sqlNum(j.product_raw_id)},
    ${sqlNum(j.run_id)},
    ${sqlNum(j.category_id)},
    ${classified ? '1.0' : 'NULL'},
    ${sqlStr(j.explanation)},
    'human',
    ${sqlStr(j.decision_status)},
    ${sqlStr(j.human_reviewer)},
    ${sqlStr(j.human_comment)},
    NOW(),
    'none',
    ${sqlStr(j.workflow_version)},
    ${sqlStr(j.prompt_version)},
    NOW()
  )
  ON CONFLICT (product_id) DO UPDATE SET
    product_raw_id = COALESCE(EXCLUDED.product_raw_id, pc.product_raw_id),
    latest_run_id = COALESCE(EXCLUDED.latest_run_id, pc.latest_run_id),
    final_category_id = EXCLUDED.final_category_id,
    final_confidence = EXCLUDED.final_confidence,
    final_explanation = EXCLUDED.final_explanation,
    final_source = 'human',
    decision_status = EXCLUDED.decision_status,
    human_reviewer = EXCLUDED.human_reviewer,
    human_comment = EXCLUDED.human_comment,
    reviewed_at = NOW(),
    next_action = 'none',
    workflow_version = COALESCE(EXCLUDED.workflow_version, pc.workflow_version),
    prompt_version = COALESCE(EXCLUDED.prompt_version, pc.prompt_version),
    updated_at = NOW()
  RETURNING product_id
),
log_ins AS (
  INSERT INTO product_classification_log (
    run_id, product_id, product_raw_id, stage, actor_type, actor_name, status,
    input_payload, output_payload, selected_category_id, confidence, explanation,
    validation_passed, decision_status, next_action, workflow_version, prompt_version
  ) VALUES (
    ${sqlNum(j.run_id)},
    ${sqlNum(j.product_id)},
    ${sqlNum(j.product_raw_id)},
    'human_review',
    'human',
    ${sqlStr(j.human_reviewer)},
    ${sqlStr(logStatus)},
    ${sqlStr(inputJson)}::jsonb,
    jsonb_build_object(
      'resolution', ${sqlStr(j.resolution)},
      'queue_id', ${sqlNum(j.queue_id)},
      'category_id', ${j.category_id == null ? 'null' : sqlNum(j.category_id)}
    ),
    ${sqlNum(j.category_id)},
    ${classified ? '1.0' : 'NULL'},
    ${sqlStr(j.explanation)},
    true,
    ${sqlStr(j.decision_status)},
    'none',
    ${sqlStr(j.workflow_version)},
    ${sqlStr(j.prompt_version)}
  )
  RETURNING id
),
q AS (
  UPDATE classification_review_queue
  SET
    status = ${sqlStr(j.queue_status)},
    resolution = ${sqlStr(j.resolution)},
    resolved_category_id = ${sqlNum(j.category_id)},
    resolved_at = NOW(),
    classification_log_id = (SELECT id FROM log_ins)
  WHERE id = ${sqlNum(j.queue_id)}
  RETURNING id, status, resolution, resolved_category_id
)
SELECT q.*, (SELECT id FROM log_ins) AS log_id
FROM q;
`;

return [{ json: { ...j, query } }];
"""
        },
        [1580, -160],
        type_version=2,
    )
)

cb_nodes.append(
    node(
        "HR — Execute Resolve",
        "n8n-nodes-base.postgres",
        {
            "operation": "executeQuery",
            "query": "={{ $json.query }}",
            "options": {},
        },
        [1800, -160],
        creds=PG,
        type_version=2.5,
    )
)

cb_nodes.append(
    node(
        "HR — Attach Resolve Meta",
        "n8n-nodes-base.code",
        {
            "jsCode": """
const prev = $('HR — Apply Resolve SQL').first().json;
const row = items[0].json;
return [{
  json: {
    ...prev,
    db: row,
    reply_text: `Готово: ${prev.resolution} · product ${prev.product_id} · cat=${prev.category_id ?? '—'} · ${prev.decision_status}`,
  },
}];
"""
        },
        [2020, -160],
        type_version=2,
    )
)

# Prepare TG reply already in list - ensure names unique
write_wf(
    "classification-human-review-callback",
    "classification-human-review-callback",
    cb_nodes,
    {
        "HR — Telegram Trigger": {"main": [[{"node": "HR — Parse Update", "type": "main", "index": 0}]]},
        "HR — Parse Update": {"main": [[{"node": "HR — Is Callback?", "type": "main", "index": 0}]]},
        "HR — Is Callback?": {
            "main": [
                [{"node": "HR — Load Queue By Id", "type": "main", "index": 0}],
                [{"node": "HR — Load Queue By Chat", "type": "main", "index": 0}],
            ]
        },
        "HR — Load Queue By Id": {"main": [[{"node": "HR — Merge Event Context", "type": "main", "index": 0}]]},
        "HR — Load Queue By Chat": {"main": [[{"node": "HR — Merge Event Context", "type": "main", "index": 0}]]},
        "HR — Merge Event Context": {"main": [[{"node": "HR — Resolve Decision", "type": "main", "index": 0}]]},
        "HR — Resolve Decision": {"main": [[{"node": "HR — Mode Switch", "type": "main", "index": 0}]]},
        "HR — Mode Switch": {
            "main": [
                [{"node": "HR — Apply Resolve SQL", "type": "main", "index": 0}],
                [{"node": "HR — Mark In Review", "type": "main", "index": 0}],
                [{"node": "HR — Prepare TG Reply", "type": "main", "index": 0}],
            ]
        },
        "HR — Apply Resolve SQL": {"main": [[{"node": "HR — Execute Resolve", "type": "main", "index": 0}]]},
        "HR — Execute Resolve": {"main": [[{"node": "HR — Attach Resolve Meta", "type": "main", "index": 0}]]},
        "HR — Attach Resolve Meta": {"main": [[{"node": "HR — Prepare TG Reply", "type": "main", "index": 0}]]},
        "HR — Mark In Review": {"main": [[{"node": "HR — Prepare TG Reply", "type": "main", "index": 0}]]},
        "HR — Prepare TG Reply": {"main": [[{"node": "HR — Telegram HTTP", "type": "main", "index": 0}]]},
    },
)

print("done")
