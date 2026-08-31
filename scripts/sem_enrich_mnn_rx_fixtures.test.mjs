/**
 * Offline fixture tests for MNN/RX enrichment prompt + post-process.
 * Run: node --test scripts/sem_enrich_mnn_rx_fixtures.test.mjs
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BUILD_PATH = join(__dirname, "hierarchy_nodes", "enrichment_build_prompt.js");
const POST_PATH = join(__dirname, "hierarchy_nodes", "enrichment_post_process.js");

function loadApi(path) {
  const code = readFileSync(path, "utf8");
  const wrapped = code.replace(
    /return items\.map[\s\S]*$/,
    `
return {
  decideEligibility: typeof decideEligibility === "function" ? decideEligibility : undefined,
  nutrientHit: typeof nutrientHit === "function" ? nutrientHit : undefined,
  buildEnrichedRecord: typeof buildEnrichedRecord === "function" ? buildEnrichedRecord : undefined,
  safeParseJson: typeof safeParseJson === "function" ? safeParseJson : undefined,
  normalizeRxEnriched: typeof normalizeRxEnriched === "function" ? normalizeRxEnriched : undefined,
  normalizeCombinationHint: typeof normalizeCombinationHint === "function" ? normalizeCombinationHint : undefined,
  buildDrugUser: typeof buildDrugUser === "function" ? buildDrugUser : undefined,
  buildVitaminUser: typeof buildVitaminUser === "function" ? buildVitaminUser : undefined,
  SYSTEM_DRUG: typeof SYSTEM_DRUG !== "undefined" ? SYSTEM_DRUG : undefined,
  SYSTEM_VITAMIN: typeof SYSTEM_VITAMIN !== "undefined" ? SYSTEM_VITAMIN : undefined,
  PROMPT_VERSION: typeof PROMPT_VERSION !== "undefined" ? PROMPT_VERSION : undefined,
  NUTRIENT_RULES: typeof NUTRIENT_RULES !== "undefined" ? NUTRIENT_RULES : undefined,
};
`
  );
  return new Function(wrapped)();
}

function runCode(path, items) {
  const code = readFileSync(path, "utf8");
  const fn = new Function("items", code);
  return fn(items);
}

const postApi = loadApi(POST_PATH);
const buildApi = loadApi(BUILD_PATH);

test("prompt_version is prompt_enrichment_v1", () => {
  assert.equal(buildApi.PROMPT_VERSION, "prompt_enrichment_v1");
});

test("build prompt: drug branch sets system + user with MNN/RX task", () => {
  const [out] = runCode(BUILD_PATH, [
    {
      json: {
        enrich_kind: "drug",
        product_kind: "drug",
        normalized_text: "Нурофен таблетки 200 мг",
        attr_brand: "Нурофен",
        attr_mnn: null,
        attr_rx_otc: null,
        attr_dosage_form: "таблетки",
        attr_administration_route: "перорально",
        attr_dosage: "200 мг",
        semantic_explanation: "НПВС",
      },
    },
  ]);
  assert.match(out.json.prompt_system, /clinical pharmacology/i);
  assert.match(out.json.prompt_user, /Нурофен таблетки/);
  assert.match(out.json.prompt_user, /attr_mnn/);
  assert.equal(out.json.prompt_version, "prompt_enrichment_v1");
});

test("build prompt: vitamin branch asks for nutrient + combination_hint", () => {
  const [out] = runCode(BUILD_PATH, [
    {
      json: {
        enrich_kind: "vitamin_or_baa",
        product_kind: "vitamin_or_baa",
        normalized_text: "Куркумин 500 мг капсулы",
        attr_brand: null,
        attr_mnn: null,
        attr_combination_hint: null,
        attr_dosage_form: "капсулы",
        attr_dosage: "500 мг",
        attr_nosology: "нутрицевтики",
        semantic_explanation: "БАД",
      },
    },
  ]);
  assert.match(out.json.prompt_system, /nutraceuticals/i);
  assert.match(out.json.prompt_user, /Куркумин/);
  assert.match(out.json.prompt_user, /combination_hint/);
});

test("eligibility: drug with empty mnn → enrich", () => {
  const d = postApi.decideEligibility({
    product_kind: "drug",
    attr_mnn: "",
    attr_rx_otc: "rx",
    normalized_text: "Бренд X таблетки",
  });
  assert.equal(d.enrich, true);
  assert.equal(d.enrich_kind, "drug");
});

test("eligibility: drug with canon mnn+rx → skip", () => {
  const d = postApi.decideEligibility({
    product_kind: "drug",
    attr_mnn: "Ибупрофен",
    attr_rx_otc: "otc",
    normalized_text: "Нурофен ибупрофен 200 мг",
  });
  assert.equal(d.enrich, false);
  assert.equal(d.enrich_skip_reason, "drug_mnn_and_rx_ok");
});

test("eligibility: drug with free-text rx → enrich", () => {
  const d = postApi.decideEligibility({
    product_kind: "drug",
    attr_mnn: "Ибупрофен",
    attr_rx_otc: "рецептурный",
    normalized_text: "X",
  });
  assert.equal(d.enrich, true);
});

test("eligibility: vitamin nutrient hit → enrich", () => {
  const d = postApi.decideEligibility({
    product_kind: "vitamin_or_baa",
    attr_mnn: "Комплекс",
    attr_rx_otc: "не применимо",
    normalized_text: "Куркумин форте капсулы 500 мг",
  });
  assert.equal(d.enrich, true);
});

test("eligibility: vitamin Комплекс + multivitamin brand → skip", () => {
  const d = postApi.decideEligibility({
    product_kind: "vitamin_or_baa",
    attr_mnn: "Комплекс",
    normalized_text: "Компливит таблетки покрытые оболочкой",
    attr_brand: "Компливит",
  });
  assert.equal(d.enrich, false);
  assert.equal(d.enrich_skip_reason, "vitamin_complex_skip");
});

test("eligibility: cosmetic → out of scope", () => {
  const d = postApi.decideEligibility({
    product_kind: "cosmetic_hygiene",
    attr_mnn: "",
    normalized_text: "крем",
  });
  assert.equal(d.enrich, false);
  assert.equal(d.enrich_skip_reason, "kind_out_of_scope");
});

test("nutrientHit: Омега-3 / Коэнзим Q10", () => {
  assert.equal(postApi.nutrientHit("омега-3 1000 мг"), "Омега-3");
  assert.equal(postApi.nutrientHit("Коэнзим Q10 капсулы"), "Коэнзим Q10");
});

test("post-process: drug JSON → mnn_enriched + rx", () => {
  const [out] = runCode(POST_PATH, [
    {
      json: {
        product_id: 42,
        enrich_kind: "drug",
        product_kind: "drug",
        normalized_text: "Нурофен 200 мг",
        attr_mnn: null,
        attr_rx_otc: "рецептурный",
        enrichment_raw: JSON.stringify({
          mnn: "Ибупрофен",
          rx_otc: "otc",
          confidence: 0.91,
          explanation: "Явный НПВС без рецепта.",
        }),
      },
    },
  ]);
  assert.equal(out.json.mnn_enriched, "Ибупрофен");
  assert.equal(out.json.rx_otc_enriched, "otc");
  assert.equal(out.json.mnn_source, "qwen_enrichment");
  assert.equal(out.json.confidence_enriched, 0.91);
  assert.equal(out.json.error_message, null);
  assert.equal(out.json.attr_mnn, null);
  assert.equal(out.json.attr_rx_otc, "рецептурный");
});

test("post-process: vitamin JSON → combination_hint + rx не применимо", () => {
  const [out] = runCode(POST_PATH, [
    {
      json: {
        product_id: 7,
        enrich_kind: "vitamin_or_baa",
        product_kind: "vitamin_or_baa",
        normalized_text: "Таурин 500 мг",
        attr_mnn: null,
        enrichment_raw: JSON.stringify({
          mnn: "Таурин",
          combination_hint: "monocomponent",
          confidence: 0.88,
          explanation: "Монокомпонентный БАД.",
        }),
      },
    },
  ]);
  assert.equal(out.json.mnn_enriched, "Таурин");
  assert.equal(out.json.rx_otc_enriched, "не применимо");
  assert.equal(out.json.combination_hint_enriched, "monocomponent");
});

test("post-process: error → null mnn + unknown rx", () => {
  const [out] = runCode(POST_PATH, [
    {
      json: {
        product_id: 1,
        enrich_kind: "drug",
        product_kind: "drug",
        error_message: "timeout",
        enrichment_raw: null,
      },
    },
  ]);
  assert.equal(out.json.mnn_enriched, null);
  assert.equal(out.json.rx_otc_enriched, "unknown");
  assert.equal(out.json.error_message, "timeout");
});

test("post-process: markdown-fenced JSON still parses", () => {
  const parsed = postApi.safeParseJson('```json\n{"mnn":"Хром","rx_otc":"unknown","confidence":0.5,"explanation":"x"}\n```');
  assert.equal(parsed.mnn, "Хром");
});

test("normalizeRxEnriched maps free-text", () => {
  assert.equal(postApi.normalizeRxEnriched("рецептурный", "drug"), "rx");
  assert.equal(postApi.normalizeRxEnriched("без рецепта", "drug"), "otc");
  assert.equal(postApi.normalizeRxEnriched(null, "drug"), "unknown");
  assert.equal(postApi.normalizeRxEnriched("otc", "vitamin_or_baa"), "не применимо");
});
