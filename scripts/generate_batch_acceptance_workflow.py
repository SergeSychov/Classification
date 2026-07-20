#!/usr/bin/env python3
"""Generate classification-batch-acceptance n8n workflow."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / "workflows"
WF.mkdir(parents=True, exist_ok=True)

PG = {"postgres": {"id": "rcmpgUWgwB2BRYlW", "name": "Postgres account"}}
TG = {"telegramApi": {"id": "T48nEk1GS2E9PTHd", "name": "Telegram — SergeSychFirstTime_bot"}}
GS = {"googleSheetsOAuth2Api": {"id": "v2NiEo8MpFLub2Fq", "name": "Google Sheets account 2"}}
GD = {"googleDriveOAuth2Api": {"id": "S7mhg7CBYGpInlHx", "name": "Google Drive account"}}
DS_AUTH = {"httpHeaderAuth": {"id": "Gmg28IgPyPk5vSBf", "name": "DeepSeek Balance Auth"}}
PZ_AUTH = {"httpHeaderAuth": {"id": "XBSW3qpVBUfoEMXK", "name": "Polza Balance Auth"}}


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


def conn(src, dst, src_out=0):
    return {
        src: {
            "main": [[{"node": dst, "type": "main", "index": 0}] if src_out == 0 else []]
        }
    }


NORMALIZE_JS = r"""
const j = items[0].json || {};
const body = j.body || {};
const runRaw = j.run_id ?? j.id ?? body.run_id ?? body.id;
const runId = Number(runRaw);
if (!Number.isFinite(runId) || runId <= 0) {
  throw new Error('batch_acceptance requires run_id (got: ' + JSON.stringify(runRaw) + ')');
}
const forceRaw = j.force ?? body.force ?? false;
const force = forceRaw === true || forceRaw === 'true' || forceRaw === 1 || forceRaw === '1';
return [{ json: { run_id: Math.trunc(runId), force } }];
"""

CLAIM_SQL = r"""
INSERT INTO batch_acceptance (run_id, status, updated_at)
VALUES ({{ Number($json.run_id) }}, 'exporting', NOW())
ON CONFLICT (run_id) DO UPDATE
SET
  status = 'exporting',
  error_message = NULL,
  spreadsheet_id = NULL,
  spreadsheet_url = NULL,
  sheet_a_url = NULL,
  sheet_b_url = NULL,
  classified_count = NULL,
  open_count = NULL,
  balances_json = NULL,
  notified_at = NULL,
  updated_at = NOW()
WHERE batch_acceptance.status IN ('pending', 'error', 'exporting')
   OR {{ $json.force ? 'TRUE' : 'FALSE' }}
RETURNING
  run_id,
  status,
  spreadsheet_id,
  spreadsheet_url,
  sheet_a_url,
  sheet_b_url,
  classified_count,
  open_count;
"""

LOAD_BUNDLE_SQL = r"""
WITH settings AS (
  SELECT
    (
      SELECT NULLIF(TRIM(COALESCE(value->>'chat_id', '')), '')
      FROM pipeline_settings WHERE key = 'telegram_ops_chat_id'
    ) AS ops_chat_id,
    (
      SELECT COALESCE(NULLIF(TRIM(value->>'value'), '')::numeric, 1)
      FROM pipeline_settings WHERE key = 'balance_alert_threshold_usd'
    ) AS threshold_usd,
    (
      SELECT COALESCE(NULLIF(TRIM(value->>'value'), '')::numeric, 80)
      FROM pipeline_settings WHERE key = 'usd_rub_rate'
    ) AS usd_rub_rate,
    (
      SELECT NULLIF(TRIM(COALESCE(value->>'folder_id', '')), '')
      FROM pipeline_settings WHERE key = 'google_sheets_folder_id'
    ) AS sheets_folder_id
),
run_ref AS (
  SELECT {{ Number($('BA — Normalize').first().json.run_id) }}::bigint AS run_id
),
classified AS (
  SELECT COALESCE(jsonb_agg(row_to_json(x) ORDER BY x.product_name), '[]'::jsonb) AS rows_a
  FROM (
    SELECT
      COALESCE(pp.product_name_effective, '') AS product_name,
      COALESCE(cd.category_code, '') AS category_code,
      COALESCE(cd.category_name, '') AS category_name,
      pc.final_confidence AS confidence,
      COALESCE(pc.final_explanation, '') AS explanation
    FROM run_ref r
    CROSS JOIN product_classification pc
    LEFT JOIN products_prepared pp ON pp.id = pc.product_id
    LEFT JOIN categories_dict cd ON cd.id = pc.final_category_id
    WHERE pc.decision_status = 'classified'
    ORDER BY pc.product_id
  ) x
),
open_rows AS (
  SELECT COALESCE(jsonb_agg(row_to_json(x) ORDER BY x.product_name), '[]'::jsonb) AS rows_b
  FROM (
    SELECT
      COALESCE(pp.product_name_effective, '') AS product_name,
      COALESCE((
        SELECT string_agg(
          COALESCE(e->>'category_id', '') || ':' || COALESCE(e->>'category_name', e->>'category_code', ''),
          '; '
          ORDER BY ordinality
        )
        FROM jsonb_array_elements(
          CASE WHEN jsonb_typeof(cs.shortlist_json) = 'array' THEN cs.shortlist_json ELSE '[]'::jsonb END
        ) WITH ORDINALITY AS t(e, ordinality)
        WHERE ordinality <= 8
      ), '') AS shortlist
    FROM run_ref r
    CROSS JOIN product_classification pc
    LEFT JOIN products_prepared pp ON pp.id = pc.product_id
    LEFT JOIN classification_shortlist cs
      ON cs.product_id = pc.product_id
     AND (cs.stage IS NULL OR cs.stage = 'primary_rules')
    WHERE pc.decision_status IN ('needs_human_review', 'error')
    ORDER BY pc.product_id
  ) x
)
SELECT
  r.run_id,
  s.ops_chat_id,
  s.threshold_usd,
  s.usd_rub_rate,
  s.sheets_folder_id,
  c.rows_a,
  o.rows_b,
  jsonb_array_length(c.rows_a) AS classified_count,
  jsonb_array_length(o.rows_b) AS open_count,
  COALESCE(cr.status, '') AS run_status
FROM run_ref r
CROSS JOIN settings s
CROSS JOIN classified c
CROSS JOIN open_rows o
LEFT JOIN classification_runs cr ON cr.id = r.run_id;
"""

PREPARE_CREATE_JS = r"""
const j = items[0].json || {};
const runId = Number(j.run_id);
const d = new Date();
const y = d.getUTCFullYear();
const m = String(d.getUTCMonth() + 1).padStart(2, '0');
const day = String(d.getUTCDate()).padStart(2, '0');
const title = `batch_${runId}_${y}${m}${day}`;

function asArray(v) {
  if (Array.isArray(v)) return v;
  if (v == null || v === '') return [];
  if (typeof v === 'string') {
    try { return JSON.parse(v); } catch (_) { return []; }
  }
  return [];
}

return [{
  json: {
    run_id: runId,
    title,
    ops_chat_id: j.ops_chat_id || '',
    threshold_usd: Number(j.threshold_usd) || 1,
    usd_rub_rate: Number(j.usd_rub_rate) || 80,
    sheets_folder_id: j.sheets_folder_id || '',
    rows_a: asArray(j.rows_a),
    rows_b: asArray(j.rows_b),
    classified_count: Number(j.classified_count) || 0,
    open_count: Number(j.open_count) || 0,
    run_status: j.run_status || '',
  },
}];
"""

AFTER_CREATE_JS = r"""
const bundle = $('BA — Prepare Create').first().json;
const created = items[0].json || {};
const spreadsheetId = created.spreadsheetId || created.id || '';
const spreadsheetUrl = created.spreadsheetUrl
  || (spreadsheetId ? `https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit` : '');

const sheets = Array.isArray(created.sheets) ? created.sheets : [];
function gidFor(title) {
  const hit = sheets.find((s) => (s.properties && s.properties.title) === title);
  const gid = hit && hit.properties ? hit.properties.sheetId : null;
  return gid == null ? null : Number(gid);
}

const gidA = gidFor('A_classified');
const gidB = gidFor('B_open');
const sheetAUrl = spreadsheetId
  ? `${spreadsheetUrl.split('/edit')[0]}/edit#gid=${gidA == null ? 0 : gidA}`
  : '';
const sheetBUrl = spreadsheetId
  ? `${spreadsheetUrl.split('/edit')[0]}/edit#gid=${gidB == null ? 0 : gidB}`
  : '';

return [{
  json: {
    ...bundle,
    spreadsheet_id: spreadsheetId,
    spreadsheet_url: spreadsheetUrl,
    sheet_a_url: sheetAUrl,
    sheet_b_url: sheetBUrl,
    sheet_a_gid: gidA,
    sheet_b_gid: gidB,
  },
}];
"""

EXPAND_A_JS = r"""
const meta = $('BA — After Create').first().json;
const rows = Array.isArray(meta.rows_a) ? meta.rows_a : [];
const empty = {
  product_name: '',
  category_code: '',
  category_name: '',
  confidence: '',
  explanation: '',
};
if (!rows.length) return [{ json: empty }];
return rows.map((r) => ({
  json: {
    product_name: r.product_name ?? '',
    category_code: r.category_code ?? '',
    category_name: r.category_name ?? '',
    confidence: r.confidence ?? '',
    explanation: r.explanation ?? '',
  },
}));
"""

EXPAND_B_JS = r"""
const meta = $('BA — After Create').first().json;
const rows = Array.isArray(meta.rows_b) ? meta.rows_b : [];
const empty = {
  product_name: '',
  shortlist: '',
};
if (!rows.length) return [{ json: empty }];
return rows.map((r) => ({
  json: {
    product_name: r.product_name ?? '',
    shortlist: r.shortlist ?? '',
  },
}));
"""

FORMAT_MSG_JS = r"""
const meta = $('BA — After Create').first().json;
const deepseek = $('BA — HTTP DeepSeek').first().json;
const polza = $('BA — HTTP Polza').first().json;
const thrUsd = Number(meta.threshold_usd);
const rate = Number(meta.usd_rub_rate);
const thresholdUsd = Number.isFinite(thrUsd) ? thrUsd : 1;
const usdRubRate = Number.isFinite(rate) && rate > 0 ? rate : 80;

function money(amount, currency) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return '?';
  const cur = String(currency || '').toUpperCase();
  if (cur === 'USD') return `$${n.toFixed(2)}`;
  if (cur === 'RUB') return `${n.toFixed(2)} RUB`;
  return `${n.toFixed(2)} ${currency}`;
}

function thrFor(currency) {
  return String(currency).toUpperCase() === 'RUB' ? thresholdUsd * usdRubRate : thresholdUsd;
}

function parseDeepseek(raw) {
  if (!raw || raw.error) return { ok: false, error: (raw && (raw.error || raw.message)) || 'unavailable' };
  const infos = raw.balance_infos || [];
  const chosen = infos.find((i) => String(i.currency || '').toUpperCase() === 'USD') || infos[0];
  if (!chosen) return { ok: false, error: 'no_balance_infos' };
  const amount = Number(chosen.total_balance);
  if (!Number.isFinite(amount)) return { ok: false, error: 'bad_amount' };
  return { ok: true, amount, currency: chosen.currency || 'USD' };
}

function parsePolza(raw) {
  if (!raw || raw.error) return { ok: false, error: (raw && (raw.error || raw.message)) || 'unavailable' };
  const amount = Number(raw.amount);
  if (!Number.isFinite(amount)) return { ok: false, error: 'bad_amount' };
  return { ok: true, amount, currency: 'RUB' };
}

const ds = parseDeepseek(deepseek);
const pz = parsePolza(polza);

const now = new Date();
const parts = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/Moscow',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hour12: false,
}).formatToParts(now);
const get = (t) => (parts.find((p) => p.type === t) || {}).value;
const stamp = `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`;

const agents = [
  { name: 'DeepSeek', ...ds },
  { name: 'Polza (Judge)', ...pz },
];
const balancesJson = agents.map((a) => ({
  name: a.name,
  ok: !!a.ok,
  amount: a.ok ? a.amount : null,
  currency: a.currency || null,
  error: a.ok ? null : (a.error || 'unavailable'),
}));

const balLines = [`Balances · ${stamp} MSK`, ''];
const low = [];
for (const a of agents) {
  if (!a.ok) {
    balLines.push(`• ${a.name}: error (${a.error || 'unavailable'})`);
    continue;
  }
  const thr = thrFor(a.currency);
  const warn = a.amount < thr ? ' !' : '';
  if (a.amount < thr) low.push(a.name);
  balLines.push(`• ${a.name}: ${money(a.amount, a.currency)}${warn}`);
}
balLines.push('');
const usdLabel = Number.isInteger(thresholdUsd) ? String(thresholdUsd) : thresholdUsd.toFixed(2);
const rubThr = thrFor('RUB');
const rubLabel = Number.isInteger(rubThr) ? String(rubThr) : String(Math.round(rubThr));
balLines.push(`Below $${usdLabel} / ${rubLabel} RUB: ${low.length ? low.join(', ') : '— none —'}`);

const lines = [
  `Batch run #${meta.run_id} · ${meta.run_status || 'finished'}`,
  `A classified: ${meta.classified_count} — ${meta.sheet_a_url}`,
  `B open: ${meta.open_count} — ${meta.sheet_b_url}`,
  'Sheets are shared: anyone with the link can edit.',
  'Pipeline stopped — wait for customer review.',
  '',
  ...balLines,
];

const chatId = String(meta.ops_chat_id || '').trim();
if (!chatId) {
  return [{
    json: {
      ok: false,
      error: 'missing_telegram_ops_chat_id',
      run_id: meta.run_id,
      spreadsheet_id: meta.spreadsheet_id,
      spreadsheet_url: meta.spreadsheet_url,
      sheet_a_url: meta.sheet_a_url,
      sheet_b_url: meta.sheet_b_url,
      classified_count: meta.classified_count,
      open_count: meta.open_count,
      balances_json: balancesJson,
      skip_telegram: true,
      message_text: lines.join('\\n'),
    },
  }];
}

return [{
  json: {
    ok: true,
    run_id: meta.run_id,
    telegram_chat_id: chatId,
    message_text: lines.join('\\n'),
    spreadsheet_id: meta.spreadsheet_id,
    spreadsheet_url: meta.spreadsheet_url,
    sheet_a_url: meta.sheet_a_url,
    sheet_b_url: meta.sheet_b_url,
    classified_count: meta.classified_count,
    open_count: meta.open_count,
    balances_json: balancesJson,
    skip_telegram: false,
  },
}];
"""

# Fix accidental double-escaped newlines in FORMAT_MSG_JS
FORMAT_MSG_JS = FORMAT_MSG_JS.replace("lines.join('\\\\n')", "lines.join('\\n')")

MARK_SQL = r"""
UPDATE batch_acceptance
SET
  status = 'notified',
  spreadsheet_id = '{{ String($json.spreadsheet_id || '').replace(/'/g, "''") }}',
  spreadsheet_url = '{{ String($json.spreadsheet_url || '').replace(/'/g, "''") }}',
  sheet_a_url = '{{ String($json.sheet_a_url || '').replace(/'/g, "''") }}',
  sheet_b_url = '{{ String($json.sheet_b_url || '').replace(/'/g, "''") }}',
  classified_count = {{ Number($json.classified_count) || 0 }},
  open_count = {{ Number($json.open_count) || 0 }},
  balances_json = '{{ JSON.stringify($json.balances_json || []).replace(/'/g, "''") }}'::jsonb,
  error_message = NULL,
  notified_at = NOW(),
  updated_at = NOW()
WHERE run_id = {{ Number($json.run_id) }}
RETURNING run_id, status, spreadsheet_url, sheet_a_url, sheet_b_url, classified_count, open_count, notified_at;
"""

MARK_ERROR_SQL = r"""
UPDATE batch_acceptance
SET
  status = 'error',
  error_message = '{{ String($json.error || "export_failed").replace(/'/g, "''").slice(0, 500) }}',
  updated_at = NOW()
WHERE run_id = {{ Number($('BA — Normalize').first().json.run_id) }}
RETURNING run_id, status, error_message;
"""


def sheet_append(name, sheet_title, pos):
    return node(
        name,
        "n8n-nodes-base.googleSheets",
        {
            "resource": "sheet",
            "operation": "append",
            "documentId": {
                "__rl": True,
                "mode": "id",
                "value": "={{ $('BA — After Create').first().json.spreadsheet_id }}",
            },
            "sheetName": {
                "__rl": True,
                "mode": "name",
                "value": sheet_title,
            },
            "columns": {
                "mappingMode": "autoMapInputData",
                "value": None,
            },
            "options": {
                "useAppend": True,
            },
        },
        pos,
        creds=GS,
        type_version=4.5,
    )


def build():
    nodes = [
        node("BA — Manual Trigger", "n8n-nodes-base.manualTrigger", {}, [0, 0]),
        node(
            "BA — Execute Trigger",
            "n8n-nodes-base.executeWorkflowTrigger",
            {},
            [0, 180],
        ),
        node(
            "BA — Webhook",
            "n8n-nodes-base.webhook",
            {
                "httpMethod": "POST",
                "path": "classification-batch-acceptance",
                "responseMode": "onReceived",
                "options": {},
            },
            [0, 360],
            type_version=2,
            webhookId=str(uuid.uuid4()),
            notes="POST /webhook/classification-batch-acceptance {run_id}",
        ),
        node(
            "BA — Normalize",
            "n8n-nodes-base.code",
            {"jsCode": NORMALIZE_JS},
            [220, 80],
            type_version=2,
        ),
        node(
            "BA — Claim",
            "n8n-nodes-base.postgres",
            {"operation": "executeQuery", "query": CLAIM_SQL, "options": {}},
            [440, 80],
            creds=PG,
            type_version=2.6,
            alwaysOutputData=True,
        ),
        node(
            "BA — Claimed?",
            "n8n-nodes-base.if",
            {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "loose",
                    },
                    "conditions": [
                        {
                            "id": nid(),
                            "leftValue": "={{ $json.run_id }}",
                            "rightValue": "",
                            "operator": {
                                "type": "number",
                                "operation": "exists",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            [660, 80],
            type_version=2,
        ),
        node(
            "BA — Load Bundle",
            "n8n-nodes-base.postgres",
            {"operation": "executeQuery", "query": LOAD_BUNDLE_SQL, "options": {}},
            [880, 0],
            creds=PG,
            type_version=2.6,
        ),
        node(
            "BA — Prepare Create",
            "n8n-nodes-base.code",
            {"jsCode": PREPARE_CREATE_JS},
            [1100, 0],
            type_version=2,
        ),
        node(
            "BA — Create Spreadsheet",
            "n8n-nodes-base.googleSheets",
            {
                "resource": "spreadsheet",
                "operation": "create",
                "title": "={{ $json.title }}",
                "sheetsUi": {
                    "sheetValues": [
                        {"title": "A_classified"},
                        {"title": "B_open"},
                    ]
                },
                "options": {},
            },
            [1320, 0],
            creds=GS,
            type_version=4.5,
        ),
        node(
            "BA — After Create",
            "n8n-nodes-base.code",
            {"jsCode": AFTER_CREATE_JS},
            [1540, 0],
            type_version=2,
        ),
        node(
            "BA — Share Anyone Writer",
            "n8n-nodes-base.httpRequest",
            {
                "method": "POST",
                "url": "=https://www.googleapis.com/drive/v3/files/{{ $('BA — After Create').first().json.spreadsheet_id }}/permissions?supportsAllDrives=true",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "googleSheetsOAuth2Api",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ role: 'writer', type: 'anyone', allowFileDiscovery: false }) }}",
                "options": {
                    "timeout": 30000,
                },
            },
            [1650, 0],
            creds=GS,
            type_version=4.2,
            continueOnFail=True,
            notes="Anyone with link can edit (via Sheets OAuth owner)",
        ),
        node(
            "BA — Expand A",
            "n8n-nodes-base.code",
            {"jsCode": EXPAND_A_JS},
            [1760, -100],
            type_version=2,
        ),
        sheet_append("BA — Append A", "A_classified", [1980, -100]),
        node(
            "BA — Expand B",
            "n8n-nodes-base.code",
            {"jsCode": EXPAND_B_JS},
            [2200, -100],
            type_version=2,
        ),
        sheet_append("BA — Append B", "B_open", [2420, -100]),
        node(
            "BA — HTTP DeepSeek",
            "n8n-nodes-base.httpRequest",
            {
                "method": "GET",
                "url": "https://api.deepseek.com/user/balance",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "options": {"timeout": 30000},
            },
            [2640, -160],
            creds=DS_AUTH,
            type_version=4.2,
            continueOnFail=True,
        ),
        node(
            "BA — HTTP Polza",
            "n8n-nodes-base.httpRequest",
            {
                "method": "GET",
                "url": "https://polza.ai/api/v1/balance",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "options": {"timeout": 30000},
            },
            [2640, -20],
            creds=PZ_AUTH,
            type_version=4.2,
            continueOnFail=True,
        ),
        # After Append B we need to fan-out to both HTTP nodes.
        # Use a Code passthrough that emits one item, then connect both HTTP from a Merge trigger.
        node(
            "BA — Start Balances",
            "n8n-nodes-base.code",
            {
                "jsCode": "const meta = $('BA — After Create').first().json;\nreturn [{ json: { run_id: meta.run_id } }];"
            },
            [2420, 80],
            type_version=2,
        ),
        node(
            "BA — Merge Balances",
            "n8n-nodes-base.merge",
            {"mode": "combine", "combineBy": "combineByPosition", "options": {}},
            [2860, -80],
            type_version=3,
        ),
        node(
            "BA — Format Message",
            "n8n-nodes-base.code",
            {"jsCode": FORMAT_MSG_JS},
            [3080, -80],
            type_version=2,
        ),
        node(
            "BA — Has Chat?",
            "n8n-nodes-base.if",
            {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "loose",
                    },
                    "conditions": [
                        {
                            "id": nid(),
                            "leftValue": "={{ $json.ok }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "equals",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            [3300, -80],
            type_version=2,
        ),
        node(
            "BA — Send Telegram",
            "n8n-nodes-base.telegram",
            {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": "={{ $json.telegram_chat_id }}",
                "text": "={{ $json.message_text }}",
                "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"},
            },
            [3520, -160],
            creds=TG,
            type_version=1.2,
        ),
        node(
            "BA — Mark Notified",
            "n8n-nodes-base.postgres",
            {"operation": "executeQuery", "query": MARK_SQL, "options": {}},
            [3740, -80],
            creds=PG,
            type_version=2.6,
        ),
        node(
            "BA — Mark Skip Error",
            "n8n-nodes-base.postgres",
            {"operation": "executeQuery", "query": MARK_ERROR_SQL, "options": {}},
            [3520, 40],
            creds=PG,
            type_version=2.6,
        ),
        node(
            "BA — Already Done",
            "n8n-nodes-base.noOp",
            {},
            [880, 200],
        ),
    ]

    # Rewire: Append B → Start Balances → both HTTP; fix positions in connections
    # Remove duplicate Start Balances position conflict - Append B connects to Start Balances

    connections = {
        "BA — Manual Trigger": {
            "main": [[{"node": "BA — Normalize", "type": "main", "index": 0}]]
        },
        "BA — Execute Trigger": {
            "main": [[{"node": "BA — Normalize", "type": "main", "index": 0}]]
        },
        "BA — Webhook": {
            "main": [[{"node": "BA — Normalize", "type": "main", "index": 0}]]
        },
        "BA — Normalize": {
            "main": [[{"node": "BA — Claim", "type": "main", "index": 0}]]
        },
        "BA — Claim": {
            "main": [[{"node": "BA — Claimed?", "type": "main", "index": 0}]]
        },
        "BA — Claimed?": {
            "main": [
                [{"node": "BA — Load Bundle", "type": "main", "index": 0}],
                [{"node": "BA — Already Done", "type": "main", "index": 0}],
            ]
        },
        "BA — Load Bundle": {
            "main": [[{"node": "BA — Prepare Create", "type": "main", "index": 0}]]
        },
        "BA — Prepare Create": {
            "main": [[{"node": "BA — Create Spreadsheet", "type": "main", "index": 0}]]
        },
        "BA — Create Spreadsheet": {
            "main": [[{"node": "BA — After Create", "type": "main", "index": 0}]]
        },
        "BA — After Create": {
            "main": [[{"node": "BA — Share Anyone Writer", "type": "main", "index": 0}]]
        },
        "BA — Share Anyone Writer": {
            "main": [[{"node": "BA — Expand A", "type": "main", "index": 0}]]
        },
        "BA — Expand A": {
            "main": [[{"node": "BA — Append A", "type": "main", "index": 0}]]
        },
        "BA — Append A": {
            "main": [[{"node": "BA — Expand B", "type": "main", "index": 0}]]
        },
        "BA — Expand B": {
            "main": [[{"node": "BA — Append B", "type": "main", "index": 0}]]
        },
        "BA — Append B": {
            "main": [[{"node": "BA — Start Balances", "type": "main", "index": 0}]]
        },
        "BA — Start Balances": {
            "main": [
                [
                    {"node": "BA — HTTP DeepSeek", "type": "main", "index": 0},
                    {"node": "BA — HTTP Polza", "type": "main", "index": 0},
                ]
            ]
        },
        "BA — HTTP DeepSeek": {
            "main": [[{"node": "BA — Merge Balances", "type": "main", "index": 0}]]
        },
        "BA — HTTP Polza": {
            "main": [[{"node": "BA — Merge Balances", "type": "main", "index": 1}]]
        },
        "BA — Merge Balances": {
            "main": [[{"node": "BA — Format Message", "type": "main", "index": 0}]]
        },
        "BA — Format Message": {
            "main": [[{"node": "BA — Has Chat?", "type": "main", "index": 0}]]
        },
        "BA — Has Chat?": {
            "main": [
                [{"node": "BA — Send Telegram", "type": "main", "index": 0}],
                [{"node": "BA — Mark Skip Error", "type": "main", "index": 0}],
            ]
        },
        "BA — Send Telegram": {
            "main": [[{"node": "BA — Mark Notified", "type": "main", "index": 0}]]
        },
        # When skip telegram due to missing chat, still try to persist URLs via Mark Notified path?
        # Mark Skip Error only sets error. Better: also mark notified without telegram when sheets ok.
    }

    # Improve skip path: if sheets created but no chat, mark notified with note in error_message
    # Replace Mark Skip Error to still save URLs — update FORMAT to always go Mark Notified,
    # and only optionally Send Telegram.

    return {
        "name": "classification-batch-acceptance",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "meta": {"templateCredsSetupCompleted": True},
    }



def main():
    wf = build()

    # Always send telegram (continueOnFail) then mark notified — no fragile boolean IF.
    nodes_by_name = {n["name"]: n for n in wf["nodes"]}
    if "BA — Send Telegram" in nodes_by_name:
        nodes_by_name["BA — Send Telegram"]["continueOnFail"] = True
    # Drop IF + No Chat nodes
    wf["nodes"] = [
        n for n in wf["nodes"]
        if n["name"] not in {"BA — Has Chat?", "BA — Mark Notified No Chat"}
    ]
    wf["connections"]["BA — Format Message"] = {
        "main": [[{"node": "BA — Send Telegram", "type": "main", "index": 0}]]
    }
    wf["connections"]["BA — Send Telegram"] = {
        "main": [[{"node": "BA — Mark Notified", "type": "main", "index": 0}]]
    }
    wf["connections"].pop("BA — Has Chat?", None)

    # Mark Notified should tolerate missing telegram by using Format Message fields
    # (Send Telegram output may be error object) — rebuild mark query to read from Format Message.
    mark = next(n for n in wf["nodes"] if n["name"] == "BA — Mark Notified")
    mark["parameters"]["query"] = r"""
UPDATE batch_acceptance
SET
  status = 'notified',
  spreadsheet_id = '{{ String($("BA — Format Message").first().json.spreadsheet_id || "").replace(/'/g, "''") }}',
  spreadsheet_url = '{{ String($("BA — Format Message").first().json.spreadsheet_url || "").replace(/'/g, "''") }}',
  sheet_a_url = '{{ String($("BA — Format Message").first().json.sheet_a_url || "").replace(/'/g, "''") }}',
  sheet_b_url = '{{ String($("BA — Format Message").first().json.sheet_b_url || "").replace(/'/g, "''") }}',
  classified_count = {{ Number($("BA — Format Message").first().json.classified_count) || 0 }},
  open_count = {{ Number($("BA — Format Message").first().json.open_count) || 0 }},
  balances_json = '{{ JSON.stringify($("BA — Format Message").first().json.balances_json || []).replace(/'/g, "''") }}'::jsonb,
  error_message = CASE
    WHEN {{ $("BA — Format Message").first().json.ok ? "true" : "false" }} THEN NULL
    ELSE '{{ String($("BA — Format Message").first().json.error || "export_notify_issue").replace(/'/g, "''").slice(0, 500) }}'
  END,
  notified_at = NOW(),
  updated_at = NOW()
WHERE run_id = {{ Number($("BA — Format Message").first().json.run_id) }}
RETURNING run_id, status, spreadsheet_url, sheet_a_url, sheet_b_url, classified_count, open_count, notified_at, error_message;
"""

    out = WF / "classification-batch-acceptance.json"
    out.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    print(f"nodes={len(wf['nodes'])}")

if __name__ == "__main__":
    main()
