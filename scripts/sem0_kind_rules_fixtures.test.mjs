/**
 * Offline fixtures for Sem0 correctProductKind syringe rules.
 * Run: node --test scripts/sem0_kind_rules_fixtures.test.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, "hierarchy_nodes", "sem0_post_process.js");

function loadCorrectProductKind() {
  const code = readFileSync(SRC, "utf8");
  // Extract helper functions + correctProductKind into a sandbox.
  const start = code.indexOf("/** Named injectable drug brands");
  const end = code.indexOf("function applyPolicyOverlay");
  if (start < 0 || end < 0) throw new Error("could not locate correctProductKind block");
  const block = code.slice(start, end);
  // eslint-disable-next-line no-new-func
  const fn = new Function(`${block}; return correctProductKind;`);
  return fn();
}

const correctProductKind = loadCorrectProductKind();

test("empty disposable syringe → medical_device", () => {
  const r = correctProductKind(
    "drug",
    "Инъекции",
    "ШПРИЦ ОДНОРАЗ. 3-Х КОМП. 20МЛ LUER-SLIP ИГЛА ПРИЛОЖ. 21G №1 VM"
  );
  assert.equal(r.kind, "medical_device");
  assert.equal(r.note, "kind_fix:empty_syringe_device");
});

test("insulin syringe U-100 device → medical_device", () => {
  const r = correctProductKind(
    "drug",
    null,
    "ШПРИЦ ИНСУЛИН. U-100 ОДНОРАЗ. 3-Х КОМП. 1МЛ №100 ПАКРО МЕДИКАЛ"
  );
  assert.equal(r.kind, "medical_device");
});

test("pen needle → medical_device", () => {
  const r = correctProductKind(
    "drug",
    null,
    "ИГЛА IME-FINE УНИВЕРСАЛЬНАЯ ИНЪЕКЦИОННАЯ ОДНОРАЗОВАЯ ДЛЯ ИНСУЛИНОВЫХ ШПРИЦ-РУЧЕК 31G"
  );
  assert.equal(r.kind, "medical_device");
});

test("Toujeo pen stays / becomes drug", () => {
  const r = correctProductKind(
    "medical_device",
    "Приборы и средства для инъекций",
    "ТУДЖЕО СОЛО СТАР Р-Р ДЛЯ П/К ВВЕД. 300ЕД/МЛ КАРТРИДЖ В ШПРИЦ-РУЧКЕ 1,5МЛ №5"
  );
  assert.equal(r.kind, "drug");
  assert.equal(r.note, "kind_fix:syringe_drug");
});

test("NovoRapid stays drug", () => {
  const r = correctProductKind(
    "drug",
    "Инъекции",
    "НОВОРАПИД ФЛЕКСПЕН Р-Р ДЛЯ В/В П/К ВВЕД. 100ЕД/МЛ КАРТРИДЖ 3МЛ №5+ШПРИЦ-РУЧКА"
  );
  assert.equal(r.kind, "drug");
  assert.equal(r.note, null); // already drug, no change needed
});
