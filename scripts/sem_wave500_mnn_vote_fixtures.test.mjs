/**
 * Fixtures for catalog MNN vote/normalize rules.
 * Runs the Python helpers via a tiny bridge script.
 */
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import path from "path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const py = `
import json, sys
sys.path.insert(0, ${JSON.stringify(path.join(root, "scripts"))})
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cat", ${JSON.stringify(path.join(root, "scripts/sem_wave500_mnn_from_catalogs.py"))}
)
m = importlib.util.module_from_spec(spec)
sys.modules["cat"] = m
spec.loader.exec_module(m)
cases = json.load(sys.stdin)
out = []
for c in cases:
    got = m.vote_mnn(c["values"])
    out.append({"got": got, "want": c.get("want"), "id": c.get("id")})
print(json.dumps(out, ensure_ascii=False))
`;

const cases = [
  {
    id: "single_source",
    values: ["Пирацетам", null, null],
    want: "Пирацетам",
  },
  {
    id: "descriptive_ignored",
    values: [
      "Другие психостимуляторы и ноотропные препараты",
      "Мозга крупного рогатого скота гидролизат",
    ],
    want: "Мозга крупного рогатого скота гидролизат",
  },
  {
    id: "levomenthol",
    values: ["Levomenthol", "Левоментол"],
    want: "Левоментол",
  },
  {
    id: "eucalyptus",
    values: ["Эвкалипта листьев экстракт", "Листья эвкалипта"],
    want: "Эвкалипта листьев экстракт",
  },
  {
    id: "thiamphenicol",
    values: [
      "Тиамфеникола глицинат ацетилцистеинат",
      "Тиамфеникол, глицинат ацетилцистеинат",
    ],
    want: "Тиамфеникола глицинат ацетилцистеинат",
  },
  {
    id: "chloramphenicol",
    values: ["D,L-хлорамфеникол", "Хлорамфеникол [D,L]", "Хлорамфеникол"],
    want: "Хлорамфеникол [D,L]",
  },
  {
    id: "iron",
    values: [
      "Железа (III) гидроксид сахарозный комплекс",
      "Железа",
      "Железо-сахарозный комплекс",
    ],
    want: "Железа комплекс",
  },
  {
    id: "paracetamol_freq",
    values: [
      "Парацетамол + Фенилэфрин + Аскорбиновая кислота",
      "Парацетамол* + Фенирамин* + Аскорбиновая кислота",
      "Парацетамол, Аскорбиновая кислота, Фенирамин",
      "Парацетамол",
    ],
    want: "Парацетамол, Аскорбиновая кислота, Фенирамин",
  },
  {
    id: "nacl_complex",
    values: [
      "Натрия хлорида раствор сложный [Калия хлорид + Кальция хлорид + Натрия хлорид]",
      "Калия хлорид+Кальция хлорид+Натрия хлорид",
      "Натрия хлорида раствор сложный",
    ],
    want: "Натрия хлорид, Калия хлорид, Кальция хлорид",
  },
  {
    id: "levonorgestrel",
    values: ["Левоноргестрел+Этинилэстрадиол", "Этинилэстрадиол"],
    want: "Этинилэстрадиол, Левоноргестрел",
  },
  {
    id: "ibuprofen",
    values: ["Ибупрофен + Парацетамол", "Ибупрофен"],
    want: "Ибупрофен, Парацетамол",
  },
  {
    id: "diphenhydramine",
    values: ["Дифенгидрамин+Напроксен", "Дифенгидрамин"],
    want: "Дифенгидрамин, Напроксен",
  },
  {
    id: "amlodipine",
    values: ["Амлодипин + Небиволол", "Небиволол* + Амлодипин", "Амлодипин"],
    want: "Амлодипин, Небиволол",
  },
  {
    id: "algeldrate",
    values: ["Алгелдрат + Бензокаин + Магния гидроксид", "Магния гидроксид"],
    want: "Магния гидроксид, Алгелдрат, Бензокаин",
  },
  {
    id: "conflict_disjoint",
    values: ["Нитрофурал", "Прокаин"],
    want: null,
  },
];

const res = spawnSync("python3", ["-c", py], {
  input: JSON.stringify(cases),
  encoding: "utf8",
  cwd: root,
});
if (res.status !== 0) {
  console.error(res.stderr || res.stdout);
  process.exit(1);
}
const results = JSON.parse(res.stdout);
let failed = 0;
for (const r of results) {
  const ok = r.got === r.want;
  if (!ok) {
    failed += 1;
    console.error(`FAIL ${r.id}: got=${JSON.stringify(r.got)} want=${JSON.stringify(r.want)}`);
  } else {
    console.log(`ok ${r.id}`);
  }
}
if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log(`all ${results.length} passed`);
