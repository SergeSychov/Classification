#!/usr/bin/env python3
"""Create inactive M3.2a skeleton workflow rx-otc-product-retrieval-dev and run smokes.

Does not modify prod Stage 2 / hierarchy-dev. No HTTP/LLM/Postgres nodes.
No git commit. run_id remains null (no classification_runs).
"""
from __future__ import annotations

import json
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
SLUG = "rx-otc-product-retrieval-dev"
N8N_CONTAINER = "myn8n-n8n-iucjks-n8n-1"
SSH_HOST = "vps-dokploy"
PROD_ID = "BaBjEPi78taRj2G5"
HIERARCHY_ID = "o8sugljHYuUs7IEC"
IDENTITY_JS = ROOT / "scripts" / "hierarchy_nodes" / "rx_otc_build_identity.js"

M2_EXCLUDED = [
    56, 75, 249, 3763, 5322, 8201, 9197,
    18179, 18830, 21387, 22548, 23695, 26319,
]

SMOKE_A = {
    "product_id": 3065,
    "normalized_text_full": "ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО",
    "brand_or_product_name": None,
    "dosage_form": None,
    "strength": None,
    "pack": None,
    "manufacturer_normalized": None,
    "mnn_if_known": None,
    "country_or_market_if_known": "RU",
}
SMOKE_B = {
    "product_id": 9197,
    "normalized_text_full": "ПОМОГУША СИРОП ДЕТСКИЙ ДЛЯ ДЕТЕЙ С 3-Х ЛЕТ ПРОТИВОПРОСТУДНЫЙ 100МЛ | ЮГ ООО | ЮГ ООО",
    "country_or_market_if_known": "RU",
}
SMOKE_C = {"product_id": 999999, "normalized_text_full": ""}

FORBIDDEN_TYPE_PREFIXES = (
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.postgres",
    "n8n-nodes-base.mySql",
    "n8n-nodes-base.mongoDb",
    "n8n-nodes-base.redis",
    "n8n-nodes-base.ssh",
    "n8n-nodes-base.ftp",
    "n8n-nodes-base.graphql",
    "n8n-nodes-base.elasticsearch",
    "n8n-nodes-base.aws",
    "n8n-nodes-base.google",
    "n8n-nodes-base.openAi",
    "n8n-nodes-base.searxng",
    "@n8n/n8n-nodes-langchain",
    "n8n-nodes-deepseek",
    "n8n-nodes-base.agent",
)

ALLOWED_TYPES = {
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.code",
    "n8n-nodes-base.set",
    "n8n-nodes-base.switch",
    "n8n-nodes-base.merge",
    "n8n-nodes-base.if",
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.stickyNote",
    "n8n-nodes-base.noOp",
}


def nid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rx-otc-m3-2a:{name}"))


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def api_request(method: str, path: str, payload: dict | None = None) -> dict:
    env = load_env(ENV_PATH)
    base_url = env["N8N_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    url = f"{base_url}{path}"
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=120, context=context) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


def webhook_post(path: str, payload: dict) -> tuple[int, str]:
    env = load_env(ENV_PATH)
    url = f"{env['N8N_URL'].rstrip('/')}/webhook/{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def js_map(body: str) -> str:
    return (
        "const items = $input.all();\n"
        "return items.map((item, i) => {\n"
        "  const j = item.json || {};\n"
        f"{body}\n"
        "});\n"
    )


JS_NORMALIZE = js_map(
    """
  const DEFAULT_A = {
    product_id: 3065,
    normalized_text_full: "ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО",
    brand_or_product_name: null,
    dosage_form: null,
    strength: null,
    pack: null,
    manufacturer_normalized: null,
    mnn_if_known: null,
    country_or_market_if_known: "RU"
  };
  const looksWebhook = Boolean(j.headers || j.webhookUrl);
  const body = (j.body && typeof j.body === "object" && !Array.isArray(j.body)) ? j.body : null;
  const src = body && (body.product_id !== undefined || body.normalized_text_full !== undefined || body.normalized_text !== undefined)
    ? body
    : j;
  const pid = src.product_id;
  const text = src.normalized_text_full != null ? src.normalized_text_full : src.normalized_text;
  const empty = (pid === undefined || pid === null || pid === "") && String(text || "").trim() === "";
  const base = empty ? { ...DEFAULT_A } : { ...src };
  if (!base.normalized_text_full && base.normalized_text) base.normalized_text_full = base.normalized_text;
  return {
    json: {
      ...base,
      trigger_source: looksWebhook ? "webhook" : (base.trigger_source || "manual")
    },
    pairedItem: { item: i }
  };
"""
)

JS_INIT = js_map(
    """
  const constants = {
    workflow_version: "rx_otc_retrieval_dev_v1",
    stage: "rx_otc_retrieval",
    mode: "m3_2a_stub",
    run_id: null,
    run_id_mode: "none_no_db_in_m3_2a",
    max_search_queries_per_eligible_sku: 8,
    q1_grls_max_queries: 3,
    q2_official_max_queries: 3,
    q3_support_max_queries: 2,
    max_fetched_candidate_pages_per_eligible_sku: 4,
    m2_excluded_product_ids: [56, 75, 249, 3763, 5322, 8201, 9197, 18179, 18830, 21387, 22548, 23695, 26319],
    isolation: {
      external_http: false,
      llm: false,
      postgres_write: false,
      snapshot_update: false,
      attr_update: false,
      product_kind_update: false,
      workflow_active: false
    }
  };
  return {
    json: {
      ...j,
      ...constants,
      constants
    },
    pairedItem: { item: i }
  };
"""
)

JS_VALIDATE = js_map(
    """
  const pidRaw = j.product_id;
  const pidNum = Number(pidRaw);
  const pidOk = pidRaw !== null && pidRaw !== undefined && pidRaw !== "" && Number.isFinite(pidNum);
  const text = String(j.normalized_text_full || j.normalized_text || "").trim();
  const textOk = text.length >= 3;
  const passed = pidOk && textOk;
  return {
    json: {
      ...j,
      product_id: pidOk ? pidNum : pidRaw,
      input_validation_passed: passed,
      input_reject_reason: passed ? null : (!pidOk ? "missing_product_id" : "empty_or_short_text"),
      outcome: passed ? null : "rejected",
      error_code: passed ? null : "E_INPUT_IDENTITY",
      candidate_rx_otc_value: null,
      final_rx_otc_value: null,
      search_query_count: 0,
      fetched_page_count: 0,
      transport_retry_attempt_count: 0,
      budget_exhausted: false
    },
    pairedItem: { item: i }
  };
"""
)

JS_M2 = js_map(
    """
  const ids = (j.constants && j.constants.m2_excluded_product_ids) || [];
  const pid = Number(j.product_id);
  const exclude = ids.map(Number).includes(pid);
  if (exclude) {
    return {
      json: {
        ...j,
        m2_gate: "exclude",
        candidate_rx_otc_value: null,
        final_rx_otc_value: null,
        outcome: "not_applicable",
        error_code: "E_M2_NON_DRUG",
        search_query_count: 0,
        fetched_page_count: 0,
        transport_retry_attempt_count: 0,
        budget_exhausted: false,
        q1_planned_queries: [],
        q2_planned_queries: [],
        q3_planned_queries: []
      },
      pairedItem: { item: i }
    };
  }
  return {
    json: { ...j, m2_gate: "pass" },
    pairedItem: { item: i }
  };
"""
)


def js_build_queries(layer: str, kind: str, max_n: int, templates: list[str]) -> str:
    tjson = json.dumps(templates, ensure_ascii=False)
    field = f"{layer.lower()}_planned_queries"
    return js_map(
        f"""
  const templates = {tjson};
  const maxN = {max_n};
  const kind = {json.dumps(kind)};
  function fill(tpl) {{
    return tpl
      .split("<brand>").join(j.rx_otc_brand_norm || "")
      .split("<form>").join(j.rx_otc_form_norm || "")
      .split("<strength>").join(j.rx_otc_strength_norm || "")
      .split("<manufacturer>").join(j.rx_otc_manufacturer_short || "");
  }}
  const planned = [];
  if (j.rx_otc_brand_norm) {{
    for (let n = 0; n < templates.length && planned.length < maxN; n++) {{
      planned.push({{
        query_kind: kind,
        query_order: n + 1,
        query: fill(templates[n]),
        stubbed: true,
        executed: false
      }});
    }}
  }}
  return {{
    json: {{
      ...j,
      {field}: planned,
      current_query_kind: kind
    }},
    pairedItem: {{ item: i }}
  }};
"""
    )


JS_Q1 = js_build_queries(
    "Q1",
    "grls_primary",
    3,
    [
        '"<brand>" "<form>" "<strength>" site:grls.rosminzdrav.ru',
        '"<brand>" "<form>" "<strength>" ГРЛС',
        '"<brand>" "<manufacturer>" site:grls.rosminzdrav.ru',
    ],
)
JS_Q2 = js_build_queries(
    "Q2",
    "official_instruction",
    3,
    [
        '"<brand>" "<form>" "<strength>" инструкция условия отпуска',
        '"<brand>" "<form>" "<strength>" "по рецепту"',
        '"<brand>" "<form>" "<strength>" "без рецепта"',
    ],
)
JS_Q3 = js_build_queries(
    "Q3",
    "support_card",
    2,
    [
        '"<brand>" "<form>" "<strength>" site:rlsnet.ru',
        '"<brand>" "<form>" "<strength>" site:vidal.ru',
    ],
)

JS_FETCH = js_map(
    """
  return {
    json: {
      ...j,
      stubbed: true,
      http_status: 0,
      retrieved_candidates: [],
      search_query_count: 0,
      fetched_page_count: 0,
      transport_retry_attempt_count: 0,
      executed_search_query_count: 0,
      executed_fetch_page_count: 0
    },
    pairedItem: { item: i }
  };
"""
)

JS_PARSE = js_map(
    """
  return {
    json: {
      ...j,
      retrieved_candidates: [],
      parsed_stub: true,
      layer_error_code: "E_SOURCE_NOT_FOUND"
    },
    pairedItem: { item: i }
  };
"""
)

JS_VALIDATE_STUB = js_map(
    """
  return {
    json: {
      ...j,
      validation_passed: false,
      tier1_accepted: false,
      validated_evidence: [],
      reject_reason: "stub_no_candidates"
    },
    pairedItem: { item: i }
  };
"""
)

JS_CONFLICT = js_map(
    """
  return {
    json: {
      ...j,
      candidate_rx_otc_value: null,
      final_rx_otc_value: null,
      outcome: "unresolved",
      error_code: "E_SOURCE_NOT_FOUND",
      conflict_status: "unknown",
      validation_passed: false,
      search_query_count: 0,
      fetched_page_count: 0,
      transport_retry_attempt_count: 0,
      budget_exhausted: false
    },
    pairedItem: { item: i }
  };
"""
)

JS_AUDIT = js_map(
    """
  const m2 = j.m2_gate || "pass";
  const valid = j.input_validation_passed !== false;
  let outcome = "unresolved";
  let error_code = "E_SOURCE_NOT_FOUND";
  if (!valid) {
    outcome = "rejected";
    error_code = "E_INPUT_IDENTITY";
  } else if (m2 === "exclude") {
    outcome = "not_applicable";
    error_code = "E_M2_NON_DRUG";
  }
  const q1 = Array.isArray(j.q1_planned_queries) ? j.q1_planned_queries : [];
  const q2 = Array.isArray(j.q2_planned_queries) ? j.q2_planned_queries : [];
  const q3 = Array.isArray(j.q3_planned_queries) ? j.q3_planned_queries : [];
  const audit_result = {
    candidate_rx_otc_value: null,
    final_rx_otc_value: null,
    outcome,
    error_code,
    validation_passed: false,
    search_query_count: 0,
    fetched_page_count: 0,
    transport_retry_attempt_count: 0,
    budget_exhausted: false
  };
  return {
    json: {
      ...j,
      ...audit_result,
      m2_gate: valid ? (m2 === "exclude" ? "exclude" : "pass") : (j.m2_gate || null),
      audit_result,
      query_plan: {
        q1_count: q1.length,
        q2_count: q2.length,
        q3_count: q3.length,
        logical_search_budget: 8,
        fetched_page_budget: 4,
        executed_search_query_count: 0,
        executed_fetch_page_count: 0,
        transport_retry_attempt_count: 0
      }
    },
    pairedItem: { item: i }
  };
"""
)

JS_AGGREGATE = js_map(
    """
  const isolation = (j.constants && j.constants.isolation) || j.isolation || {
    external_http: false, llm: false, postgres_write: false,
    snapshot_update: false, attr_update: false, product_kind_update: false,
    workflow_active: false
  };
  const webhook_response = {
    workflow: "rx-otc-product-retrieval-dev",
    workflow_version: j.workflow_version || "rx_otc_retrieval_dev_v1",
    mode: "m3_2a_stub",
    active_expected: false,
    run_id: null,
    run_id_mode: "none_no_db_in_m3_2a",
    product_id: j.product_id,
    input_validation_passed: Boolean(j.input_validation_passed),
    m2_gate: j.m2_gate || null,
    identity: {
      brand: j.rx_otc_brand_norm || null,
      form: j.rx_otc_form_norm || null,
      strength: j.rx_otc_strength_norm || null,
      pack: j.rx_otc_pack_norm || null,
      manufacturer: j.rx_otc_manufacturer_norm || null,
      identity_text: j.rx_otc_identity_text || null,
      identity_query: j.rx_otc_identity_query || null
    },
    query_plan: j.query_plan || {
      q1_count: 0, q2_count: 0, q3_count: 0,
      logical_search_budget: 8, fetched_page_budget: 4,
      executed_search_query_count: 0, executed_fetch_page_count: 0,
      transport_retry_attempt_count: 0
    },
    result: {
      candidate_rx_otc_value: null,
      final_rx_otc_value: null,
      outcome: j.outcome || "unresolved",
      error_code: j.error_code || "E_SOURCE_NOT_FOUND",
      validation_passed: false
    },
    isolation_confirmation: isolation
  };
  return { json: { ...webhook_response, webhook_response }, pairedItem: { item: i } };
"""
)


def code_node(name: str, js: str, x: int, y: int) -> dict:
    return {
        "parameters": {"jsCode": js.strip() + "\n"},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x, y],
        "id": nid(name),
        "name": name,
    }


def if_node(name: str, left: str, op: str, right: str | None, x: int, y: int) -> dict:
    condition: dict = {
        "id": nid(name + ":cond"),
        "leftValue": left,
        "operator": {"type": "boolean" if op in {"true", "false"} else "string", "operation": op},
    }
    if op in {"true", "false"}:
        condition["operator"]["singleValue"] = True
        condition["rightValue"] = ""
    else:
        condition["rightValue"] = right
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "conditions": [condition],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [x, y],
        "id": nid(name),
        "name": name,
    }


def sticky(name: str, content: str, x: int, y: int, w: int = 360, h: int = 160) -> dict:
    return {
        "parameters": {"content": content, "height": h, "width": w},
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [x, y],
        "id": nid(name),
        "name": name,
    }


def link(src: str, dst: str, out_index: int = 0) -> tuple[str, int, str]:
    return src, out_index, dst


def build_workflow() -> dict:
    identity_js = IDENTITY_JS.read_text(encoding="utf-8")
    nodes = [
        sticky(
            "Note — Isolation",
            "1. M3.2a isolated skeleton: no HTTP, no LLM, no DB writes.",
            -200,
            -80,
        ),
        sticky(
            "Note — P1",
            "2. P1 target in future: GRLS product record / official instruction,\nexplicit captured status only.",
            200,
            -80,
        ),
        sticky(
            "Note — P2",
            "3. P2 future: RLS/Vidal/pharmacy are supporting only;\nnever set final_rx_otc_value.",
            600,
            -80,
        ),
        sticky(
            "Note — M2",
            "4. M2 gate: 13 approved BAS/Other → not_applicable; no retrieval.",
            1000,
            -80,
        ),
        sticky(
            "Note — M3.2b",
            "5. M3.2b requires explicit approval: one-item live retrieval only.",
            1400,
            -80,
        ),
        {
            "parameters": {},
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [0, 280],
            "id": nid("In — Manual Trigger"),
            "name": "In — Manual Trigger",
        },
        {
            "parameters": {
                "httpMethod": "POST",
                "path": "rx-otc-product-retrieval-dev",
                "responseMode": "responseNode",
                "options": {},
            },
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [0, 500],
            "id": nid("In — Webhook"),
            "name": "In — Webhook",
            "webhookId": nid("webhook-id"),
        },
        code_node("In — Normalize Input", JS_NORMALIZE, 280, 380),
        code_node("Run — Init Constants", JS_INIT, 520, 380),
        code_node("Rx — Validate Input Contract", JS_VALIDATE, 760, 380),
        if_node("Rx — Input Valid?", "={{ $json.input_validation_passed }}", "true", None, 1000, 380),
        code_node("Rx — Build Product Identity", identity_js, 1240, 260),
        code_node("Rx — M2 Non-drug Exclusion Gate", JS_M2, 1480, 260),
        if_node("Rx — M2 Exclude?", "={{ $json.m2_gate }}", "equals", "exclude", 1720, 260),
        code_node("Q1 — Build GRLS Query", JS_Q1, 1960, 80),
        code_node("Q1 — Fetch Stub", JS_FETCH, 2200, 80),
        code_node("Q1 — Parse P1 Stub", JS_PARSE, 2440, 80),
        code_node("Rx — Validate P1 Stub", JS_VALIDATE_STUB, 2680, 80),
        code_node("Q2 — Build Official Query", JS_Q2, 1960, 280),
        code_node("Q2 — Fetch Stub", JS_FETCH, 2200, 280),
        code_node("Q2 — Parse Official Stub", JS_PARSE, 2440, 280),
        code_node("Rx — Validate P1 Official Stub", JS_VALIDATE_STUB, 2680, 280),
        code_node("Q3 — Build Support Query", JS_Q3, 1960, 480),
        code_node("Q3 — Fetch Stub", JS_FETCH, 2200, 480),
        code_node("Q3 — Parse Support Stub", JS_PARSE, 2440, 480),
        code_node("Rx — Validate P2 Stub", JS_VALIDATE_STUB, 2680, 480),
        code_node("Rx — Conflict Resolver Stub", JS_CONFLICT, 2920, 280),
        code_node("Art — Build Audit Result", JS_AUDIT, 3160, 380),
        code_node("Fin — Aggregate Result", JS_AGGREGATE, 3400, 380),
        if_node("Fin — Is Webhook?", "={{ $json.trigger_source }}", "equals", "webhook", 3640, 380),
        {
            "parameters": {
                "respondWith": "json",
                "responseBody": "={{ $json.webhook_response }}",
                "options": {},
            },
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.1,
            "position": [3880, 280],
            "id": nid("Fin — Respond to Webhook"),
            "name": "Fin — Respond to Webhook",
        },
        {
            "parameters": {},
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [3880, 500],
            "id": nid("Fin — Manual Done"),
            "name": "Fin — Manual Done",
        },
    ]

    # IF webhook uses trigger_source on envelope — Aggregate currently does not
    # copy trigger_source onto webhook_response. Put it on the item json root.
    # Fin — Is Webhook? reads $json.webhook_response.trigger_source — fix Aggregate.
    edges = [
        link("In — Manual Trigger", "In — Normalize Input"),
        link("In — Webhook", "In — Normalize Input"),
        link("In — Normalize Input", "Run — Init Constants"),
        link("Run — Init Constants", "Rx — Validate Input Contract"),
        link("Rx — Validate Input Contract", "Rx — Input Valid?"),
        link("Rx — Input Valid?", "Rx — Build Product Identity", 0),
        link("Rx — Input Valid?", "Art — Build Audit Result", 1),
        link("Rx — Build Product Identity", "Rx — M2 Non-drug Exclusion Gate"),
        link("Rx — M2 Non-drug Exclusion Gate", "Rx — M2 Exclude?"),
        link("Rx — M2 Exclude?", "Art — Build Audit Result", 0),
        link("Rx — M2 Exclude?", "Q1 — Build GRLS Query", 1),
        link("Q1 — Build GRLS Query", "Q1 — Fetch Stub"),
        link("Q1 — Fetch Stub", "Q1 — Parse P1 Stub"),
        link("Q1 — Parse P1 Stub", "Rx — Validate P1 Stub"),
        link("Rx — Validate P1 Stub", "Q2 — Build Official Query"),
        link("Q2 — Build Official Query", "Q2 — Fetch Stub"),
        link("Q2 — Fetch Stub", "Q2 — Parse Official Stub"),
        link("Q2 — Parse Official Stub", "Rx — Validate P1 Official Stub"),
        link("Rx — Validate P1 Official Stub", "Q3 — Build Support Query"),
        link("Q3 — Build Support Query", "Q3 — Fetch Stub"),
        link("Q3 — Fetch Stub", "Q3 — Parse Support Stub"),
        link("Q3 — Parse Support Stub", "Rx — Validate P2 Stub"),
        link("Rx — Validate P2 Stub", "Rx — Conflict Resolver Stub"),
        link("Rx — Conflict Resolver Stub", "Art — Build Audit Result"),
        link("Art — Build Audit Result", "Fin — Aggregate Result"),
        link("Fin — Aggregate Result", "Fin — Is Webhook?"),
        link("Fin — Is Webhook?", "Fin — Respond to Webhook", 0),
        link("Fin — Is Webhook?", "Fin — Manual Done", 1),
    ]

    connections: dict = {}
    for src, out_i, dst in edges:
        connections.setdefault(src, {"main": []})
        mains = connections[src]["main"]
        while len(mains) <= out_i:
            mains.append([])
        mains[out_i].append({"node": dst, "type": "main", "index": 0})

    return {
        "name": SLUG,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


def patch_aggregate_trigger() -> None:
    global JS_AGGREGATE
    JS_AGGREGATE = js_map(
        """
  const isolation = (j.constants && j.constants.isolation) || j.isolation || {
    external_http: false, llm: false, postgres_write: false,
    snapshot_update: false, attr_update: false, product_kind_update: false,
    workflow_active: false
  };
  const webhook_response = {
    workflow: "rx-otc-product-retrieval-dev",
    workflow_version: j.workflow_version || "rx_otc_retrieval_dev_v1",
    mode: "m3_2a_stub",
    active_expected: false,
    run_id: null,
    run_id_mode: "none_no_db_in_m3_2a",
    product_id: j.product_id,
    input_validation_passed: Boolean(j.input_validation_passed),
    m2_gate: j.m2_gate || null,
    identity: {
      brand: j.rx_otc_brand_norm || null,
      form: j.rx_otc_form_norm || null,
      strength: j.rx_otc_strength_norm || null,
      pack: j.rx_otc_pack_norm || null,
      manufacturer: j.rx_otc_manufacturer_norm || null,
      identity_text: j.rx_otc_identity_text || null,
      identity_query: j.rx_otc_identity_query || null
    },
    query_plan: j.query_plan || {
      q1_count: 0, q2_count: 0, q3_count: 0,
      logical_search_budget: 8, fetched_page_budget: 4,
      executed_search_query_count: 0, executed_fetch_page_count: 0,
      transport_retry_attempt_count: 0
    },
    result: {
      candidate_rx_otc_value: null,
      final_rx_otc_value: null,
      outcome: j.outcome || "unresolved",
      error_code: j.error_code || "E_SOURCE_NOT_FOUND",
      validation_passed: false
    },
    isolation_confirmation: isolation,
    trigger_source: j.trigger_source || "manual"
  };
  return { json: { ...webhook_response, webhook_response, trigger_source: j.trigger_source || "manual" }, pairedItem: { item: i } };
"""
    )


def sanitize_settings(settings: dict | None) -> dict:
    settings = settings or {}
    return {"executionOrder": settings.get("executionOrder", "v1")}


def forbidden_check(nodes: list[dict]) -> dict:
    names = [n["name"] for n in nodes]
    types = [n.get("type") for n in nodes]
    bad = []
    for n in nodes:
        t = n.get("type") or ""
        if t in ALLOWED_TYPES:
            continue
        if any(t.startswith(p) for p in FORBIDDEN_TYPE_PREFIXES) or t not in ALLOWED_TYPES:
            bad.append({"name": n.get("name"), "type": t})
    postgres = [x for x in types if "postgres" in (x or "").lower()]
    http = [x for x in types if "httpRequest" in (x or "") or "langchain" in (x or "")]
    return {
        "ok": not bad and not postgres and not http,
        "forbidden_nodes": bad,
        "has_postgres": bool(postgres),
        "has_http_or_llm": bool(http),
        "node_names": names,
        "node_types": types,
        "node_count": len(nodes),
    }


def snapshot_workflow(wid: str) -> dict:
    wf = api_request("GET", f"/api/v1/workflows/{wid}")
    return {
        "id": wf.get("id"),
        "name": wf.get("name"),
        "active": wf.get("active"),
        "updatedAt": wf.get("updatedAt"),
        "node_count": len(wf.get("nodes") or []),
    }


def put_workflow(workflow_id: str, local: dict, pin_data: dict | None = None) -> dict:
    remote = api_request("GET", f"/api/v1/workflows/{workflow_id}")
    payload = {
        "name": local["name"],
        "nodes": local["nodes"],
        "connections": local["connections"],
        "settings": sanitize_settings(local.get("settings") or remote.get("settings")),
    }
    if pin_data is not None:
        payload["pinData"] = pin_data
    elif "pinData" in remote:
        payload["pinData"] = {}
    return api_request("PUT", f"/api/v1/workflows/{workflow_id}", payload)


def cli_execute(workflow_id: str) -> dict:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        SSH_HOST,
        f"docker exec {N8N_CONTAINER} n8n execute --id={workflow_id} --rawOutput",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr[-4000:],
    }


def wait_latest_execution(workflow_id: str, started_after: float, timeout: int = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = api_request("GET", f"/api/v1/executions?workflowId={workflow_id}&limit=5")
        for execution in result.get("data") or []:
            started_at = execution.get("startedAt")
            if not started_at:
                continue
            ts = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
            if ts + 1 < started_after:
                continue
            if execution.get("finished") or execution.get("status") in {
                "success",
                "error",
                "crashed",
                "canceled",
            }:
                return execution
        time.sleep(1.5)
    raise TimeoutError("execution not found")


def execution_payload(exec_id: str) -> dict:
    data = api_request("GET", f"/api/v1/executions/{exec_id}?includeData=true")
    run_data = (((data.get("data") or {}).get("resultData") or {}).get("runData")) or {}

    def flat(name: str) -> list[dict]:
        out: list[dict] = []
        for run in run_data.get(name) or []:
            for branch in (run.get("data", {}) or {}).get("main") or []:
                if not branch:
                    continue
                for item in branch:
                    out.append(item.get("json") or {})
        return out

    agg = flat("Fin — Aggregate Result")
    return {
        "execution_id": exec_id,
        "status": data.get("status") or data.get("data", {}).get("status") if isinstance(data.get("data"), dict) else data.get("status"),
        "finished": data.get("finished"),
        "mode": data.get("mode"),
        "aggregate": agg[0] if agg else {},
        "nodes_run": list(run_data.keys()),
        "q1_ran": "Q1 — Build GRLS Query" in run_data,
        "q2_ran": "Q2 — Build Official Query" in run_data,
        "q3_ran": "Q3 — Build Support Query" in run_data,
        "respond_ran": "Fin — Respond to Webhook" in run_data,
        "error": ((data.get("data") or {}).get("resultData") or {}).get("error"),
    }


def smoke_ok_a(p: dict) -> tuple[bool, list[str]]:
    j = p.get("aggregate") or {}
    ident = j.get("identity") or {}
    qp = j.get("query_plan") or {}
    res = j.get("result") or {}
    issues = []
    if p.get("error"):
        issues.append(f"execution error: {p['error']}")
    if j.get("m2_gate") != "pass":
        issues.append(f"m2_gate={j.get('m2_gate')}")
    if ident.get("brand") != "ФЛУКОНАЗОЛ-OBL":
        issues.append(f"brand={ident.get('brand')}")
    if ident.get("form") != "капсулы":
        issues.append(f"form={ident.get('form')}")
    if ident.get("strength") != "150 мг":
        issues.append(f"strength={ident.get('strength')}")
    if ident.get("pack") != "N4":
        issues.append(f"pack={ident.get('pack')}")
    q = ident.get("identity_query") or ""
    if '"ФЛУКОНАЗОЛ-OBL" "капсулы" "150 мг"' not in q:
        issues.append(f"identity_query={q}")
    if qp.get("q1_count") != 3 or qp.get("q2_count") != 3 or qp.get("q3_count") != 2:
        issues.append(f"planned counts {qp}")
    if qp.get("executed_search_query_count") != 0 or qp.get("executed_fetch_page_count") != 0:
        issues.append(f"executed {qp}")
    if res.get("outcome") != "unresolved" or res.get("error_code") != "E_SOURCE_NOT_FOUND":
        issues.append(f"result={res}")
    if j.get("input_validation_passed") is not True:
        issues.append("input_validation_passed")
    if not p.get("q1_ran"):
        issues.append("Q1 did not run")
    iso = j.get("isolation_confirmation") or {}
    if iso.get("workflow_active") is not False or iso.get("external_http") is not False:
        issues.append(f"isolation={iso}")
    return not issues, issues


def smoke_ok_b(p: dict) -> tuple[bool, list[str]]:
    j = p.get("aggregate") or {}
    res = j.get("result") or {}
    qp = j.get("query_plan") or {}
    issues = []
    if p.get("error"):
        issues.append(f"execution error: {p['error']}")
    if j.get("m2_gate") != "exclude":
        issues.append(f"m2_gate={j.get('m2_gate')}")
    if res.get("outcome") != "not_applicable" or res.get("error_code") != "E_M2_NON_DRUG":
        issues.append(f"result={res}")
    if p.get("q1_ran") or p.get("q2_ran") or p.get("q3_ran"):
        issues.append("Q1/Q2/Q3 ran on excluded item")
    if qp.get("executed_search_query_count") not in (0, None) and qp.get("executed_search_query_count") != 0:
        issues.append(f"executed {qp}")
    if qp.get("q1_count") not in (0, None) and qp.get("q1_count") != 0:
        issues.append(f"q1_count={qp.get('q1_count')}")
    return not issues, issues


def smoke_ok_c(p: dict) -> tuple[bool, list[str]]:
    j = p.get("aggregate") or {}
    res = j.get("result") or {}
    issues = []
    if p.get("error"):
        issues.append(f"execution error: {p['error']}")
    if j.get("input_validation_passed") is not False:
        issues.append(f"input_validation_passed={j.get('input_validation_passed')}")
    if res.get("outcome") != "rejected" or res.get("error_code") != "E_INPUT_IDENTITY":
        issues.append(f"result={res}")
    if p.get("q1_ran") or p.get("q2_ran") or p.get("q3_ran"):
        issues.append("query plan executed on invalid input")
    return not issues, issues


def run_pinned_smoke(workflow_id: str, local: dict, pin_json: dict) -> dict:
    started = time.time()
    put_workflow(workflow_id, local, {"In — Manual Trigger": [{"json": pin_json}]})
    cli = cli_execute(workflow_id)
    if cli["returncode"] != 0:
        return {"ok": False, "cli": cli, "issues": ["cli_execute failed"]}
    execution = wait_latest_execution(workflow_id, started_after=started - 2)
    payload = execution_payload(str(execution["id"]))
    payload["cli_returncode"] = cli["returncode"]
    return payload


def main() -> int:
    patch_aggregate_trigger()
    local = build_workflow()
    chk = forbidden_check(local["nodes"])
    if not chk["ok"]:
        raise SystemExit(f"forbidden nodes in local JSON: {chk}")

    wf_path = ROOT / "workflows" / f"{SLUG}.json"
    id_path = ROOT / "workflows" / f"{SLUG}.id"
    wf_path.write_text(json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prod_before = snapshot_workflow(PROD_ID)
    hier_before = snapshot_workflow(HIERARCHY_ID)

    existing = api_request("GET", "/api/v1/workflows?limit=250")
    for wf in existing.get("data") or []:
        if wf.get("name") == SLUG:
            raise SystemExit(f"Workflow already exists: id={wf.get('id')}")

    created = api_request(
        "POST",
        "/api/v1/workflows",
        {
            "name": local["name"],
            "nodes": local["nodes"],
            "connections": local["connections"],
            "settings": sanitize_settings(local.get("settings")),
        },
    )
    workflow_id = created["id"]
    id_path.write_text(workflow_id + "\n", encoding="utf-8")

    if created.get("active"):
        try:
            api_request("POST", f"/api/v1/workflows/{workflow_id}/deactivate", {})
        except RuntimeError:
            remote = api_request("GET", f"/api/v1/workflows/{workflow_id}")
            api_request(
                "PUT",
                f"/api/v1/workflows/{workflow_id}",
                {
                    "name": remote["name"],
                    "nodes": remote["nodes"],
                    "connections": remote["connections"],
                    "settings": sanitize_settings(remote.get("settings")),
                    "active": False,
                },
            )

    remote = api_request("GET", f"/api/v1/workflows/{workflow_id}")
    if remote.get("name") != SLUG:
        raise SystemExit(f"name mismatch: {remote.get('name')}")
    if remote.get("active"):
        raise SystemExit("workflow is active after create; aborting smokes")
    remote_chk = forbidden_check(remote.get("nodes") or [])
    if not remote_chk["ok"]:
        raise SystemExit(f"forbidden nodes on remote: {remote_chk}")

    # Smoke A: pin explicit §4 payload (manual)
    a = run_pinned_smoke(workflow_id, local, SMOKE_A)
    a_ok, a_issues = smoke_ok_a(a) if "aggregate" in a else (False, a.get("issues") or ["no aggregate"])
    a["ok"] = a_ok
    a["issues"] = a_issues

    b = run_pinned_smoke(workflow_id, local, {"body": SMOKE_B})
    b_ok, b_issues = smoke_ok_b(b) if "aggregate" in b else (False, b.get("issues") or ["no aggregate"])
    b["ok"] = b_ok
    b["issues"] = b_issues

    c = run_pinned_smoke(workflow_id, local, {"body": SMOKE_C})
    c_ok, c_issues = smoke_ok_c(c) if "aggregate" in c else (False, c.get("issues") or ["no aggregate"])
    c["ok"] = c_ok
    c["issues"] = c_issues

    # Clear pinData
    put_workflow(workflow_id, local, {})
    final = api_request("GET", f"/api/v1/workflows/{workflow_id}")
    if final.get("active"):
        api_request("POST", f"/api/v1/workflows/{workflow_id}/deactivate", {})
        final = api_request("GET", f"/api/v1/workflows/{workflow_id}")

    webhook_status, webhook_body = webhook_post(SLUG, SMOKE_A)

    prod_after = snapshot_workflow(PROD_ID)
    hier_after = snapshot_workflow(HIERARCHY_ID)

    inventory = {
        "workflow_id": workflow_id,
        "workflow_name": final.get("name"),
        "active": final.get("active"),
        "node_names": [n["name"] for n in final.get("nodes") or []],
        "node_types": [n.get("type") for n in final.get("nodes") or []],
        "forbidden_node_check": forbidden_check(final.get("nodes") or []),
        "webhook_path": "/webhook/rx-otc-product-retrieval-dev",
        "workflow_version": "rx_otc_retrieval_dev_v1",
        "updatedAt": final.get("updatedAt"),
    }

    results = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workflow_id": workflow_id,
        "workflow_name": SLUG,
        "active": final.get("active"),
        "smoke_a": {
            "ok": a.get("ok"),
            "issues": a.get("issues"),
            "execution_id": a.get("execution_id"),
            "aggregate": a.get("aggregate"),
            "q_ran": {"q1": a.get("q1_ran"), "q2": a.get("q2_ran"), "q3": a.get("q3_ran")},
        },
        "smoke_b": {
            "ok": b.get("ok"),
            "issues": b.get("issues"),
            "execution_id": b.get("execution_id"),
            "aggregate": b.get("aggregate"),
            "q_ran": {"q1": b.get("q1_ran"), "q2": b.get("q2_ran"), "q3": b.get("q3_ran")},
        },
        "smoke_c": {
            "ok": c.get("ok"),
            "issues": c.get("issues"),
            "execution_id": c.get("execution_id"),
            "aggregate": c.get("aggregate"),
            "q_ran": {"q1": c.get("q1_ran"), "q2": c.get("q2_ran"), "q3": c.get("q3_ran")},
        },
        "production_webhook_while_inactive": {
            "url": f"/webhook/{SLUG}",
            "status": webhook_status,
            "body_excerpt": webhook_body[:400],
            "expected": "404 because active=false",
        },
        "isolation": {
            "prod_before": prod_before,
            "prod_after": prod_after,
            "hierarchy_before": hier_before,
            "hierarchy_after": hier_after,
            "prod_unchanged": prod_before == prod_after,
            "hierarchy_unchanged": hier_before == hier_after,
        },
    }

    art_dir = ROOT / "redesign" / "artifacts"
    (art_dir / "rx_otc_retrieval_m3_2a_workflow_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (art_dir / "rx_otc_retrieval_m3_2a_smoke_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary = f"""# M3.2a RX/OTC retrieval skeleton smoke

**Workflow:** `{SLUG}` (`{workflow_id}`)
**active:** `{final.get("active")}`
**workflow_version:** `rx_otc_retrieval_dev_v1`
**mode:** `m3_2a_stub` (no HTTP / LLM / Postgres)

## Forbidden-node check

ok={inventory["forbidden_node_check"]["ok"]}
node_count={inventory["forbidden_node_check"]["node_count"]}

## Smokes

| Case | ok | execution_id | key fields |
|------|----|--------------|------------|
| A eligible 3065 | {a.get("ok")} | {a.get("execution_id")} | m2={((a.get("aggregate") or {}).get("m2_gate"))} outcome={(((a.get("aggregate") or {}).get("result") or {}).get("outcome"))} |
| B exclude 9197 | {b.get("ok")} | {b.get("execution_id")} | m2={((b.get("aggregate") or {}).get("m2_gate"))} outcome={(((b.get("aggregate") or {}).get("result") or {}).get("outcome"))} |
| C invalid 999999 | {c.get("ok")} | {c.get("execution_id")} | valid={((c.get("aggregate") or {}).get("input_validation_passed"))} outcome={(((c.get("aggregate") or {}).get("result") or {}).get("outcome"))} |

A issues: {a.get("issues")}
B issues: {b.get("issues")}
C issues: {c.get("issues")}

Production webhook while inactive: HTTP {webhook_status} (expected 404).

## Isolation

- prod Stage 2 unchanged: {prod_before == prod_after} (`{prod_before.get("updatedAt")}`)
- hierarchy-dev unchanged: {hier_before == hier_after} (`{hier_before.get("updatedAt")}`)
- no DB run_id (null / none_no_db_in_m3_2a)
- no attr/snapshot/product_kind writes
- no git commit/push
"""
    (art_dir / "rx_otc_retrieval_m3_2a_smoke_summary.md").write_text(summary, encoding="utf-8")

    print(
        json.dumps(
            {
                "workflow_id": workflow_id,
                "active": final.get("active"),
                "smoke_a": a.get("ok"),
                "smoke_b": b.get("ok"),
                "smoke_c": c.get("ok"),
                "issues": {"a": a.get("issues"), "b": b.get("issues"), "c": c.get("issues")},
                "webhook_inactive_status": webhook_status,
                "export": str(wf_path.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not (a_ok and b_ok and c_ok):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
