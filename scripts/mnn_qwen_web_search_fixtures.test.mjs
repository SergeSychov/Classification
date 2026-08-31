/**
 * Lightweight fixtures for MNN Qwen post-process rules (no network).
 */
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pyFile = path.join(root, "scripts/mnn_qwen_web_search_test.py");

const bridge = `
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("t", ${JSON.stringify(pyFile)})
m = importlib.util.module_from_spec(spec)
sys.modules["t"] = m
spec.loader.exec_module(m)

cases = json.load(sys.stdin)
out = []
for c in cases:
    row = {
        "product_id": "x",
        "normalized_text": "t",
        "catalog_mnn_for_comparison": c.get("catalog", ""),
        "catalog_source_summary": "",
        "qwen_search_query": "q",
    }
    api = c.get("api")
    err = c.get("error")
    r = m.post_process(row, api=api, error=err, latency_ms=1, request_payload={})
    r = m.compare_qwen_vs_catalog(r)
    out.append({
        "id": c["id"],
        "status": r.get("qwen_search_status"),
        "mnn": r.get("qwen_search_mnn") or None,
        "vs": r.get("qwen_vs_catalog_status"),
        "src": r.get("qwen_search_source_count"),
    })
print(json.dumps(out, ensure_ascii=False))
`;

const cases = [
  {
    id: "no_annotations_rejects_mnn",
    catalog: "Ибупрофен",
    api: {
      choices: [
        {
          message: {
            content: '{"mnn":"Ибупрофен","status":"found","model_confidence":0.9}',
            annotations: [],
          },
        },
      ],
    },
    want: { status: "search_not_confirmed", mnn: null, vs: "qwen_search_not_confirmed" },
  },
  {
    id: "with_annotations_found",
    catalog: "Ибупрофен",
    api: {
      choices: [
        {
          message: {
            content:
              '{"mnn":"Ибупрофен","status":"found","model_confidence":0.9,"identity_match":{"brand_match":true,"dosage_form_match":true,"dosage_match":true},"used_source_indexes":[1],"evidence":"ok"}',
            annotations: [
              {
                type: "url_citation",
                url_citation: {
                  url: "https://uteka.ru/product/nurofen",
                  title: "Нурофен",
                },
              },
            ],
          },
        },
      ],
    },
    want: { status: "found", mnn: "Ибупрофен", vs: "exact_match" },
  },
  {
    id: "api_error",
    catalog: "Ибупрофен",
    error: "HTTP 500",
    api: null,
    want: { status: "api_error", mnn: null, vs: "qwen_api_error" },
  },
  {
    id: "normalized_match",
    catalog: "Ибупрофен + Парацетамол",
    api: {
      choices: [
        {
          message: {
            content:
              '{"mnn":"Парацетамол + Ибупрофен","status":"found","model_confidence":0.8,"identity_match":{},"used_source_indexes":[1],"evidence":"x"}',
            annotations: [
              {
                type: "url_citation",
                url_citation: { url: "https://example.com/a", title: "a" },
              },
            ],
          },
        },
      ],
    },
    want: { status: "found", vs: "normalized_match" },
  },
];

const res = spawnSync("python3", ["-c", bridge], {
  input: JSON.stringify(cases),
  encoding: "utf8",
  cwd: root,
});
if (res.status !== 0) {
  console.error(res.stderr || res.stdout);
  process.exit(1);
}
const got = JSON.parse(res.stdout);
let failed = 0;
for (let i = 0; i < cases.length; i++) {
  const g = got[i];
  const w = cases[i].want;
  const ok =
    g.status === w.status &&
    (w.mnn === undefined || g.mnn === w.mnn) &&
    g.vs === w.vs;
  if (!ok) {
    failed++;
    console.error("FAIL", cases[i].id, g, "want", w);
  } else console.log("ok", cases[i].id);
}
if (failed) process.exit(1);
console.log(`all ${cases.length} passed`);
