/**
 * Offline fixture tests for Norm — Normalize Sem attrs.
 * Run: node --test scripts/sem_normalize_attrs_fixtures.test.mjs
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const NORM_PATH = join(__dirname, "hierarchy_nodes", "sem_normalize_attrs.js");

function runNorm(items) {
  const code = readFileSync(NORM_PATH, "utf8");
  const fn = new Function("items", code);
  return fn(items);
}

function item(partial) {
  return {
    json: {
      product_id: 1,
      normalized_text: partial.normalized_text || "",
      product_kind: partial.product_kind || "drug",
      medical_device_profile: partial.medical_device_profile || null,
      attr_profile: partial.attr_profile || {},
      semantic_attrs: {
        administration_route: partial.route ?? null,
        dosage_form: partial.form ?? null,
        age_segment: partial.age ?? null,
        brand: "X",
        product_kind: partial.product_kind || "drug",
        medical_device_profile: partial.medical_device_profile || null,
        attr_profile: partial.attr_profile || {},
        ...(partial.attrs || {}),
      },
    },
  };
}

test("route: внутрь/орально → перорально", () => {
  for (const route of ["внутрь", "Внутрь", "орально", "Перорально", "для приема внутрь"]) {
    const [out] = runNorm([item({ route, form: "таблетки" })]);
    assert.equal(out.json.attr_administration_route, "перорально");
    assert.equal(out.json.semantic_attrs.administration_route, "перорально");
  }
});

test("route: наружное → наружно; инъекции → инъекционное", () => {
  const [a] = runNorm([item({ route: "наружное применение", form: "мазь" })]);
  assert.equal(a.json.attr_administration_route, "наружно");
  const [b] = runNorm([item({ route: "для инъекций", form: null })]);
  assert.equal(b.json.attr_administration_route, "инъекционное");
});

test("form: табл./жеват./капс./раствор для … / ф/п / пластырь", () => {
  const cases = [
    ["табл.", "таблетки"],
    ["таблетки жеват.", "таблетки жевательные"],
    ["капс.", "капсулы"],
    ["раствор для внутримышечного введения", "раствор"],
    ["раствор для приема внутрь", "раствор"],
    ["Фильтр-пакет", "фильтр-пакеты"],
    ["пластырь мозольный", "пластырь"],
    ["plastyr", "пластырь"],
  ];
  for (const [form, expect] of cases) {
    const [out] = runNorm([item({ form, route: "внутрь" })]);
    assert.equal(out.json.attr_dosage_form, expect, form);
  }
});

test("cosmetic bath salt → form не применимо via dict rule; route null", () => {
  // Policy v3: no blanket force-NA for cosmetic; bath-salt wording still maps form→NA in dict.
  const [out] = runNorm([
    item({
      product_kind: "cosmetic_hygiene",
      form: "морская соль для ванн",
      route: null,
      attr_profile: {
        administration_route: "applicable",
        dosage_form: "applicable",
      },
      normalized_text: "СОЛЬ ДЛЯ ВАНН МОРСКАЯ",
    }),
  ]);
  assert.equal(out.json.attr_dosage_form, "не применимо");
  assert.equal(out.json.attr_administration_route, null);
});

test("cosmetic cream → наружно + крем", () => {
  const [out] = runNorm([
    item({
      product_kind: "cosmetic_hygiene",
      form: "крем",
      route: "наружное",
      attr_profile: {
        administration_route: "applicable",
        dosage_form: "applicable",
      },
      normalized_text: "КРЕМ ДЕТСКИЙ ПИТАТЕЛЬНЫЙ 50МЛ",
    }),
  ]);
  assert.equal(out.json.attr_dosage_form, "крем");
  assert.equal(out.json.attr_administration_route, "наружно");
});

test("hygiene_like medical_device → route/form не применимо", () => {
  const [out] = runNorm([
    item({
      product_kind: "medical_device",
      medical_device_profile: "hygiene_like",
      route: null,
      form: null,
      age: null,
      attr_profile: {
        administration_route: "not_applicable",
        dosage_form: "not_applicable",
      },
      normalized_text: "Я САМАЯ ПАЛОЧКИ ВАТНЫЕ №200",
    }),
  ]);
  assert.equal(out.json.attr_administration_route, "не применимо");
  assert.equal(out.json.attr_dosage_form, "не применимо");
});

test("clinical_like syringe → route инъекционное", () => {
  const [out] = runNorm([
    item({
      product_kind: "medical_device",
      medical_device_profile: "clinical_like",
      route: "инъекционное",
      form: "шприц",
      normalized_text: "ШПРИЦ ОДНОРАЗ. 20МЛ",
    }),
  ]);
  assert.equal(out.json.attr_administration_route, "инъекционное");
  assert.equal(out.json.attr_dosage_form, null); // шприц not in form dict
});

test("age: дети / взрослые / BAA fallback универсальный", () => {
  const [kids] = runNorm([
    item({ age: "4–6 лет", normalized_text: "сироп детский 4–6 лет" }),
  ]);
  assert.equal(kids.json.attr_age_segment, "дети");

  const [adults] = runNorm([item({ age: "Для взрослых", form: "таблетки" })]);
  assert.equal(adults.json.attr_age_segment, "взрослые");

  const [mixed] = runNorm([
    item({ age: "взрослые и дети старше 12 лет", form: "спрей" }),
  ]);
  assert.equal(mixed.json.attr_age_segment, "универсальный");

  const [baa] = runNorm([
    item({
      product_kind: "vitamin_or_baa",
      age: null,
      form: "капсулы",
      route: "внутрь",
      normalized_text: "ЧЕРНИКА ФОРТЕ КАПС. №45",
    }),
  ]);
  assert.equal(baa.json.attr_age_segment, "универсальный");
  assert.equal(baa.json.attr_administration_route, "перорально");
  assert.equal(baa.json.attr_dosage_form, "капсулы");
});

test("drug: no invent when empty", () => {
  const [out] = runNorm([
    item({
      product_kind: "drug",
      route: null,
      form: null,
      age: null,
      normalized_text: "НЕКОЕ СРЕДСТВО БЕЗ ФОРМЫ",
    }),
  ]);
  assert.equal(out.json.attr_administration_route, null);
  assert.equal(out.json.attr_dosage_form, null);
  assert.equal(out.json.attr_age_segment, null);
});

test("pairedItem + ...item.json preserved", () => {
  const [out] = runNorm([
    {
      json: {
        run_id: 7,
        product_id: 9,
        keep_me: true,
        product_kind: "drug",
        semantic_attrs: { administration_route: "Внутрь", dosage_form: "табл.", age_segment: "взрослые" },
      },
      pairedItem: { item: 3 },
    },
  ]);
  assert.equal(out.json.keep_me, true);
  assert.equal(out.json.run_id, 7);
  assert.deepEqual(out.pairedItem, { item: 3 });
  assert.equal(out.json.attr_administration_route, "перорально");
  assert.equal(out.json.attr_dosage_form, "таблетки");
});

test("назальный спрей + в/м раствор", () => {
  const [nasal] = runNorm([
    item({
      route: "назально",
      form: "спрей назальный",
      normalized_text: "ОТРИВИН СПРЕЙ НАЗ.",
    }),
  ]);
  assert.equal(nasal.json.attr_administration_route, "назальный");
  assert.equal(nasal.json.attr_dosage_form, "спрей");

  const [im] = runNorm([
    item({
      route: "Внутримышечно",
      form: "Раствор для внутримышечного введения",
    }),
  ]);
  assert.equal(im.json.attr_administration_route, "внутримышечно");
  assert.equal(im.json.attr_dosage_form, "раствор");
});

test("rx_otc: рецептурный→rx, без рецепта→otc, non-drug→не применимо", () => {
  const [rx] = runNorm([
    item({
      product_kind: "drug",
      attrs: { rx_otc: "рецептурный" },
    }),
  ]);
  assert.equal(rx.json.attr_rx_otc, "rx");

  const [otc] = runNorm([
    item({
      product_kind: "drug",
      attrs: { rx_otc: "без рецепта" },
    }),
  ]);
  assert.equal(otc.json.attr_rx_otc, "otc");

  const [baa] = runNorm([
    item({
      product_kind: "vitamin_or_baa",
      attrs: { rx_otc: "otc" },
    }),
  ]);
  assert.equal(baa.json.attr_rx_otc, "не применимо");
});
