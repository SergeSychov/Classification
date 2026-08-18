#!/usr/bin/env node
/**
 * Local M3.2a skeleton executor: runs Code/IF nodes from the workflow JSON
 * with a mocked n8n $input. Used because this n8n 2.27 instance cannot
 * CLI-execute (task broker port collision) and Public API has no /run.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const WF = JSON.parse(
  fs.readFileSync(path.join(ROOT, "workflows", "rx-otc-product-retrieval-dev.json"), "utf8")
);

const SMOKES = {
  A: {
    product_id: 3065,
    normalized_text_full:
      "ФЛУКОНАЗОЛ-OBL КАПС. 150МГ №4 | ОБОЛЕНСКОЕ ФП АО | ОБОЛЕНСКОЕ ФП АО",
    brand_or_product_name: null,
    dosage_form: null,
    strength: null,
    pack: null,
    manufacturer_normalized: null,
    mnn_if_known: null,
    country_or_market_if_known: "RU",
  },
  B: {
    body: {
      product_id: 9197,
      normalized_text_full:
        "ПОМОГУША СИРОП ДЕТСКИЙ ДЛЯ ДЕТЕЙ С 3-Х ЛЕТ ПРОТИВОПРОСТУДНЫЙ 100МЛ | ЮГ ООО | ЮГ ООО",
      country_or_market_if_known: "RU",
    },
  },
  C: { body: { product_id: 999999, normalized_text_full: "" } },
};

function nodeByName(name) {
  return WF.nodes.find((n) => n.name === name);
}

function runCode(js, items) {
  const $input = {
    all: () => items.map((json, i) => ({ json, pairedItem: { item: i } })),
    first: () => ({ json: items[0], pairedItem: { item: 0 } }),
  };
  const context = { $input, console };
  vm.createContext(context);
  const wrapped = `"use strict";\n(function(){\n${js}\n})()`;
  const result = vm.runInContext(wrapped, context);
  return (result || []).map((row) => row.json);
}

function evalIf(node, json) {
  const cond = node.parameters.conditions.conditions[0];
  const leftExpr = String(cond.leftValue || "");
  const m = leftExpr.match(/\$json\.([a-zA-Z0-9_]+)/);
  const left = m ? json[m[1]] : undefined;
  const op = cond.operator.operation;
  if (op === "true") return Boolean(left) === true;
  if (op === "false") return Boolean(left) === false;
  if (op === "equals") return String(left) === String(cond.rightValue);
  throw new Error(`unsupported if op ${op} on ${node.name}`);
}

function nextNodes(fromName, outIndex) {
  const mains = (WF.connections[fromName] || {}).main || [];
  const branch = mains[outIndex] || [];
  return branch.map((l) => l.node);
}

function execute(startName, startJson) {
  const ran = [];
  let items = [startJson];
  const queue = [{ name: startName, items }];
  const skip = new Set([
    "n8n-nodes-base.stickyNote",
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.noOp",
  ]);

  while (queue.length) {
    const cur = queue.shift();
    const node = nodeByName(cur.name);
    if (!node) throw new Error(`missing node ${cur.name}`);
    ran.push(cur.name);
    const t = node.type;
    let outItems = cur.items;
    let outIndex = 0;

    if (t === "n8n-nodes-base.manualTrigger" || t === "n8n-nodes-base.webhook") {
      outItems = cur.items;
    } else if (t === "n8n-nodes-base.code") {
      outItems = runCode(node.parameters.jsCode, cur.items);
    } else if (t === "n8n-nodes-base.if") {
      const pass = evalIf(node, cur.items[0] || {});
      outIndex = pass ? 0 : 1;
    } else if (skip.has(t)) {
      continue;
    } else {
      throw new Error(`unexpected type ${t} (${cur.name})`);
    }

    for (const nxt of nextNodes(cur.name, outIndex)) {
      queue.push({ name: nxt, items: outItems });
    }
  }

  const aggNode = "Fin — Aggregate Result";
  // re-run path is sequential single-item; last queue processing stored in ran.
  // Capture aggregate by executing from start and recording when we hit it.
  return { ran, items: outItemsFromLastAggregate(startName, startJson), startName };
}

function outItemsFromLastAggregate(startName, startJson) {
  let items = [startJson];
  const queue = [{ name: startName, items }];
  let lastAgg = null;
  while (queue.length) {
    const cur = queue.shift();
    const node = nodeByName(cur.name);
    const t = node.type;
    let outItems = cur.items;
    let outIndex = 0;
    if (t === "n8n-nodes-base.code") {
      outItems = runCode(node.parameters.jsCode, cur.items);
      if (cur.name === "Fin — Aggregate Result") lastAgg = outItems[0];
    } else if (t === "n8n-nodes-base.if") {
      outIndex = evalIf(node, cur.items[0] || {}) ? 0 : 1;
    }
    if (t === "n8n-nodes-base.respondToWebhook" || t === "n8n-nodes-base.noOp" || t === "n8n-nodes-base.stickyNote") {
      continue;
    }
    for (const nxt of nextNodes(cur.name, outIndex)) {
      queue.push({ name: nxt, items: outItems });
    }
  }
  return lastAgg;
}

function collectRan(startName, startJson) {
  const ran = [];
  let items = [startJson];
  const queue = [{ name: startName, items }];
  while (queue.length) {
    const cur = queue.shift();
    const node = nodeByName(cur.name);
    ran.push(cur.name);
    const t = node.type;
    let outItems = cur.items;
    let outIndex = 0;
    if (t === "n8n-nodes-base.code") outItems = runCode(node.parameters.jsCode, cur.items);
    else if (t === "n8n-nodes-base.if") outIndex = evalIf(node, cur.items[0] || {}) ? 0 : 1;
    if (t === "n8n-nodes-base.respondToWebhook" || t === "n8n-nodes-base.noOp") continue;
    for (const nxt of nextNodes(cur.name, outIndex)) queue.push({ name: nxt, items: outItems });
  }
  return ran;
}

function checkA(j, ran) {
  const issues = [];
  const ident = j.identity || {};
  const qp = j.query_plan || {};
  const res = j.result || {};
  if (j.m2_gate !== "pass") issues.push(`m2_gate=${j.m2_gate}`);
  if (ident.brand !== "ФЛУКОНАЗОЛ-OBL") issues.push(`brand=${ident.brand}`);
  if (ident.form !== "капсулы") issues.push(`form=${ident.form}`);
  if (ident.strength !== "150 мг") issues.push(`strength=${ident.strength}`);
  if (ident.pack !== "N4") issues.push(`pack=${ident.pack}`);
  if (!(ident.identity_query || "").includes('"ФЛУКОНАЗОЛ-OBL" "капсулы" "150 мг"')) {
    issues.push(`identity_query=${ident.identity_query}`);
  }
  if (qp.q1_count !== 3 || qp.q2_count !== 3 || qp.q3_count !== 2) issues.push(`planned=${JSON.stringify(qp)}`);
  if (qp.executed_search_query_count !== 0 || qp.executed_fetch_page_count !== 0) issues.push("executed != 0");
  if (res.outcome !== "unresolved" || res.error_code !== "E_SOURCE_NOT_FOUND") issues.push(`result=${JSON.stringify(res)}`);
  if (j.input_validation_passed !== true) issues.push("input_validation_passed");
  if (!ran.includes("Q1 — Build GRLS Query")) issues.push("Q1 did not run");
  return issues;
}

function checkB(j, ran) {
  const issues = [];
  const res = j.result || {};
  if (j.m2_gate !== "exclude") issues.push(`m2_gate=${j.m2_gate}`);
  if (res.outcome !== "not_applicable" || res.error_code !== "E_M2_NON_DRUG") issues.push(`result=${JSON.stringify(res)}`);
  if (ran.some((n) => n.startsWith("Q1 —") || n.startsWith("Q2 —") || n.startsWith("Q3 —"))) {
    issues.push("Q1/Q2/Q3 ran on excluded item");
  }
  if ((j.query_plan || {}).q1_count) issues.push(`q1_count=${j.query_plan.q1_count}`);
  return issues;
}

function checkC(j, ran) {
  const issues = [];
  const res = j.result || {};
  if (j.input_validation_passed !== false) issues.push(`input_validation_passed=${j.input_validation_passed}`);
  if (res.outcome !== "rejected" || res.error_code !== "E_INPUT_IDENTITY") issues.push(`result=${JSON.stringify(res)}`);
  if (ran.some((n) => n.startsWith("Q1 —") || n.startsWith("Q2 —") || n.startsWith("Q3 —"))) {
    issues.push("query plan executed on invalid input");
  }
  return issues;
}

const out = {};
for (const [key, payload] of Object.entries(SMOKES)) {
  const start = "In — Manual Trigger";
  const agg = outItemsFromLastAggregate(start, payload);
  const ran = collectRan(start, payload);
  const issues = key === "A" ? checkA(agg, ran) : key === "B" ? checkB(agg, ran) : checkC(agg, ran);
  out[key] = {
    ok: issues.length === 0,
    issues,
    aggregate: agg,
    nodes_run: ran,
    q_ran: {
      q1: ran.includes("Q1 — Build GRLS Query"),
      q2: ran.includes("Q2 — Build Official Query"),
      q3: ran.includes("Q3 — Build Support Query"),
    },
  };
}

if (require.main === module) {
  console.log(JSON.stringify(out, null, 2));
  const failed = Object.values(out).some((x) => !x.ok);
  process.exit(failed ? 2 : 0);
}

module.exports = { out };
