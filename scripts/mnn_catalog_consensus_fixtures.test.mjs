/**
 * Offline fixtures for MNN catalog consensus (safe union + canonical output).
 * Bridges into scripts/lib/mnn_catalog_consensus.py
 */
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import path from "path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lib = path.join(root, "scripts", "lib");

const py = `
import json, sys
sys.path.insert(0, ${JSON.stringify(lib)})
from mnn_catalog_consensus import SourceResult, resolve_catalog_consensus
from mnn_enrichment_map import map_enrichment_response, should_call_enrichment
from mnn_normalization import (
    is_descriptive_non_mnn,
    normalize_mnn_alias,
    split_mnn_components,
    format_mnn_components,
    substance_key,
    extract_protected_complex_detail,
)
from mnn_source_identity import (
    apply_identity_gate,
    extract_input_explicit_mnn,
    pick_final_mnn_method,
    score_source_match,
    classify_source_url_or_page,
)

def sources_from_values(values, field_types=None, identity=None):
    out = []
    sites = ["uteka", "apteka", "asna", "vidal"]
    for i, v in enumerate(values):
        if v is None:
            continue
        ft = (field_types[i] if field_types else None) or "explicit_mnn"
        kwargs = dict(
            source=sites[i % len(sites)],
            raw_mnn=v,
            field_type=ft,
            evidence_excerpt=v if ft != "description" else ("терапевтическая группа: " + v),
        )
        if identity and i < len(identity) and identity[i]:
            kwargs.update(identity[i])
        out.append(SourceResult(**kwargs))
    return out

cases = json.load(sys.stdin)
results = []
for c in cases:
    kind = c.get("kind", "resolve")
    if kind == "alias":
        comps = split_mnn_components(c["raw"])
        got = format_mnn_components(comps) if comps else None
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "descriptive":
        got = is_descriptive_non_mnn(c["raw"])
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "substance_keys":
        got = [substance_key(x) for x in c["raws"]]
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "complex_detail":
        comps = split_mnn_components(c["raw"])
        got = {
            "resolved_mnn": format_mnn_components(comps) if comps else None,
            "resolved_mnn_components_detail": extract_protected_complex_detail(c["raw"]),
        }
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "explicit":
        got = extract_input_explicit_mnn(c["normalized_text"]).to_dict()
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "url_class":
        got = classify_source_url_or_page(
            c.get("url"),
            card_fetched=c.get("card_fetched", False),
            http_status=c.get("http_status"),
        )
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "identity_gate":
        gate = apply_identity_gate(
            c["sources"],
            normalized_text=c["normalized_text"],
            input_brand=c.get("input_brand"),
            input_form=c.get("input_form"),
            input_dose=c.get("input_dose"),
        )
        got = {
            "accepted_mnn": [s.get("raw_mnn") for s in gate["accepted"]],
            "rejected_mnn": [s.get("raw_mnn") for s in gate["rejected"]],
            "ambiguous_mnn": [s.get("raw_mnn") for s in gate["ambiguous"]],
            "accepted_count": gate["accepted_count"],
            "rejected_count": gate["rejected_count"],
            "ambiguous_count": gate["ambiguous_count"],
            "strength": gate["input_explicit"].get("input_explicit_strength"),
            "explicit_mnn": gate["input_explicit"].get("input_explicit_mnn"),
        }
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "identity_resolve":
        gate = apply_identity_gate(
            c["sources"],
            normalized_text=c["normalized_text"],
        )
        voting = []
        for s in gate["accepted"]:
            voting.append(SourceResult(
                source=s["source"],
                url=s.get("url"),
                title=s.get("title"),
                raw_mnn=s.get("raw_mnn"),
                field_type=s.get("field_type") or "explicit_mnn",
                evidence_excerpt=s.get("raw_mnn"),
                match_status="accepted",
                match_score=s.get("match_score"),
                source_class="product_card",
                matched_product_title=s.get("title"),
            ))
        for s in gate["rejected"] + gate["ambiguous"]:
            voting.append(SourceResult(
                source=s["source"],
                url=s.get("url"),
                title=s.get("title"),
                raw_mnn=s.get("raw_mnn"),
                field_type=s.get("field_type") or "explicit_mnn",
                evidence_excerpt=s.get("raw_mnn"),
                match_status=s.get("match_status") or "rejected",
                match_score=s.get("match_score"),
                source_class=s.get("source_class") or "product_card",
                matched_product_title=s.get("title"),
            ))
        r = resolve_catalog_consensus(
            voting,
            product_kind=c.get("product_kind", "drug"),
            normalized_text=c["normalized_text"],
        )
        final = pick_final_mnn_method(
            catalog_resolved=r,
            input_explicit=gate["input_explicit"],
            enrichment_mnn=c.get("enrichment_mnn"),
            enrichment_accepted=bool(c.get("enrichment_accepted")),
        )
        got = {
            "resolved_mnn": r.get("resolved_mnn"),
            "status": r.get("mnn_resolution_status"),
            "reason": r.get("resolution_reason"),
            "final_mnn": final.get("final_candidate_mnn"),
            "final_method": final.get("final_mnn_method"),
            "needs_review": final.get("needs_human_review"),
            "detail": r.get("resolved_mnn_components_detail"),
            "rejected_vote_count": len(r.get("rejected_sources") or []),
        }
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    elif kind == "enrich_map":
        got = map_enrichment_response(c["resp"])
        results.append({
            "id": c["id"],
            "got": {
                "mnn_enriched": got.get("mnn_enriched"),
                "enrichment_accepted": got.get("enrichment_accepted"),
                "needs_human_review": got.get("needs_human_review"),
                "mnn_enrichment_status": got.get("mnn_enrichment_status"),
            },
            "want": c["want"],
        })
    elif kind == "skip_enrich":
        got = should_call_enrichment(
            product_kind=c.get("product_kind"),
            normalized_text=c.get("normalized_text"),
            needs_mnn_enrichment=c.get("needs_mnn_enrichment", True),
            is_homeopathy=c.get("is_homeopathy", False),
        )
        results.append({"id": c["id"], "got": got, "want": c["want"]})
    else:
        src = sources_from_values(c["values"], c.get("field_types"), c.get("identity"))
        if c.get("rx"):
            for i, rx in enumerate(c["rx"]):
                if i < len(src) and rx:
                    src[i].raw_rx_otc = rx
        if c.get("age"):
            for i, age in enumerate(c["age"]):
                if i < len(src) and age:
                    src[i].raw_age = age
        r = resolve_catalog_consensus(
            src,
            product_kind=c.get("product_kind", "drug"),
            normalized_text=c.get("normalized_text", "TEST DRUG"),
        )
        got = {
            "resolved_mnn": r.get("resolved_mnn"),
            "status": r.get("mnn_resolution_status"),
            "reason": r.get("resolution_reason"),
            "needs": r.get("needs_mnn_enrichment"),
            "components": r.get("resolved_mnn_components"),
            "detail": r.get("resolved_mnn_components_detail"),
            "rx": r.get("resolved_rx_otc"),
            "age": r.get("resolved_age_segment"),
        }
        results.append({"id": c["id"], "got": got, "want": c["want"]})
print(json.dumps(results, ensure_ascii=False))
`;

const cases = [
  // --- aliases / canonical ---
  { id: "alias_levomenthol", kind: "alias", raw: "Levomenthol", want: "Левоментол" },
  { id: "alias_eucalyptus", kind: "alias", raw: "Листья эвкалипта", want: "Эвкалипта листьев экстракт" },
  {
    id: "alias_thiamphenicol",
    kind: "alias",
    raw: "Тиамфеникол, глицинат ацетилцистеинат",
    want: "Тиамфеникола глицинат ацетилцистеинат",
  },
  {
    id: "alias_chloramphenicol",
    kind: "alias",
    raw: "Хлорамфеникол [D,L]",
    want: "Хлорамфеникол",
  },
  {
    id: "alias_iron",
    kind: "alias",
    raw: "Железа (III) гидроксид сахарозный комплекс",
    want: "Железа комплекс",
  },
  {
    id: "descriptive_atc",
    kind: "descriptive",
    raw: "Другие психостимуляторы и ноотропные препараты",
    want: true,
  },

  // --- consensus ---
  {
    id: "single_source_unresolved",
    values: ["Пирацетам", null, null],
    want: { status: "unresolved_catalog", reason: "single_source", needs: true, resolved_mnn: null },
  },
  {
    id: "two_source_same",
    values: ["Пирацетам", "Пирацетам"],
    want: {
      status: "resolved_catalog",
      reason: "consensus",
      needs: false,
      resolved_mnn: "Пирацетам",
    },
  },
  {
    id: "valid_compatible_union_paracetamol",
    values: [
      "Парацетамол + Фенилэфрин + Аскорбиновая кислота",
      "Парацетамол* + Фенирамин* + Аскорбиновая кислота",
      "Парацетамол, Аскорбиновая кислота, Фенирамин",
      "Парацетамол",
    ],
    want: {
      status: "resolved_catalog",
      resolved_mnn: "Парацетамол, Аскорбиновая кислота, Фенирамин",
      needs: false,
    },
  },
  {
    id: "valid_union_nacl",
    values: [
      "Натрия хлорида раствор сложный [Калия хлорид + Кальция хлорид + Натрия хлорид]",
      "Калия хлорид+Кальция хлорид+Натрия хлорид",
      "Натрия хлорида раствор сложный",
    ],
    want: {
      status: "resolved_catalog",
      resolved_mnn: "Натрия хлорид, Калия хлорид, Кальция хлорид",
      needs: false,
    },
  },
  {
    id: "valid_union_amlodipine",
    values: ["Амлодипин + Небиволол", "Небиволол* + Амлодипин", "Амлодипин"],
    want: {
      status: "resolved_catalog",
      resolved_mnn: "Амлодипин, Небиволол",
      needs: false,
    },
  },
  {
    id: "intersection_without_anchor_unresolved",
    // both description → no qualified components / no anchor
    values: ["Парацетамол + Ибупрофен", "Парацетамол + Напроксен"],
    field_types: ["description", "description"],
    want: {
      status: "unresolved_catalog",
      reason: "descriptive_only",
      needs: true,
      resolved_mnn: null,
    },
  },
  {
    id: "description_extra_not_included",
    values: ["Ибупрофен", "Ибупрофен", "Парацетамол"],
    field_types: ["explicit_mnn", "explicit_mnn", "description"],
    want: {
      status: "resolved_catalog",
      resolved_mnn: "Ибупрофен",
      needs: false,
    },
  },
  {
    id: "equal_disjoint_unresolved",
    values: ["Нитрофурал", "Прокаин"],
    want: {
      status: "unresolved_catalog",
      needs: true,
      resolved_mnn: null,
    },
  },
  {
    id: "ibuprofen_subset_union",
    values: ["Ибупрофен + Парацетамол", "Ибупрофен"],
    want: {
      status: "resolved_catalog",
      resolved_mnn: "Ибупрофен, Парацетамол",
      needs: false,
    },
  },
  {
    id: "rx_age_independent",
    values: ["Пирацетам", "Пирацетам"],
    rx: ["rx", "rx"],
    age: ["взрослые", "взрослые"],
    want: {
      status: "resolved_catalog",
      resolved_mnn: "Пирацетам",
      rx: "rx",
      age: "взрослые",
    },
  },
  {
    id: "rx_single_unknown",
    values: ["Пирацетам", "Пирацетам"],
    rx: ["rx", null],
    want: { rx: "unknown", status: "resolved_catalog" },
  },

  // --- enrichment skip / map ---
  {
    id: "skip_device",
    kind: "skip_enrich",
    product_kind: "medical_device",
    normalized_text: "Тонометр",
    needs_mnn_enrichment: true,
    want: false,
  },
  {
    id: "skip_homeopathy",
    kind: "skip_enrich",
    product_kind: "drug",
    normalized_text: "ОКСИЛЛАН гомеопатические гранулы",
    is_homeopathy: true,
    needs_mnn_enrichment: true,
    want: false,
  },
  {
    id: "skip_already_resolved",
    kind: "skip_enrich",
    product_kind: "drug",
    normalized_text: "Пирацетам",
    needs_mnn_enrichment: false,
    want: false,
  },
  {
    id: "map_ok",
    kind: "enrich_map",
    resp: {
      status: "ok",
      Category: "Drug",
      mnn: "Пирацетам",
      RX_OTC: "OTC",
      Age: "Взрослый",
      evidence: [{ url: "https://example.com", title: "x" }],
    },
    want: {
      mnn_enriched: "Пирацетам",
      enrichment_accepted: true,
      needs_human_review: false,
      mnn_enrichment_status: "ok",
    },
  },
  {
    id: "map_ok_partial",
    kind: "enrich_map",
    resp: {
      status: "ok_partial",
      Category: "Drug",
      mnn: null,
      RX_OTC: "OTC",
      Age: "Взрослый",
      evidence: [{ url: "https://example.com" }],
    },
    want: {
      mnn_enriched: null,
      enrichment_accepted: false,
      needs_human_review: true,
      mnn_enrichment_status: "ok_partial",
    },
  },
  {
    id: "map_error",
    kind: "enrich_map",
    resp: {
      status: "error",
      error_code: "search_empty",
      Category: "Other",
      mnn: null,
      evidence: [],
    },
    want: {
      mnn_enriched: null,
      enrichment_accepted: false,
      needs_human_review: true,
      mnn_enrichment_status: "error",
    },
  },

  // --- identity gate / normalization fixes ---
  {
    id: "alias_chondroitin_collapse",
    kind: "alias",
    raw: "Хондроитинсульфат + Хондроитина сульфат + Хондроитина сульфат натрия",
    want: "Хондроитина сульфат натрия",
  },
  {
    id: "hydrocortisone_keys_distinct",
    kind: "substance_keys",
    raws: ["Гидрокортизон", "Гидрокортизона бутират"],
    want: ["гидрокортизон", "гидрокортизона бутират"],
  },
  {
    id: "detralex_protected_complex",
    kind: "complex_detail",
    raw: "Очищенная микронизированная флавоноидная фракция (диосмин + флавоноиды в пересчете на гесперидин)",
    want: {
      resolved_mnn: "Очищенная микронизированная флавоноидная фракция",
      resolved_mnn_components_detail: [
        "Диосмин",
        "Флавоноиды в пересчёте на гесперидин",
      ],
    },
  },
  {
    id: "detralex_consensus_dual_fields",
    values: [
      "Очищенная микронизированная флавоноидная фракция (диосмин + флавоноиды в пересчете на гесперидин)",
      "Гесперидин + Диосмин",
      "Очищенная микронизированная флавоноидная фракция (диосмин+флавоноиды в пересчете на гесперидин)",
    ],
    want: {
      status: "resolved_catalog",
      resolved_mnn: "Очищенная микронизированная флавоноидная фракция",
      detail: ["Диосмин", "Флавоноиды в пересчёте на гесперидин"],
      needs: false,
    },
  },
  {
    id: "hydrocortisone_related_conflict",
    values: ["Гидрокортизон", "Гидрокортизона бутират", "Гидрокортизон"],
    want: {
      status: "unresolved_catalog",
      reason: "related_but_not_equal_conflict",
      resolved_mnn: null,
    },
  },
  {
    id: "explicit_strong_meldonium",
    kind: "explicit",
    normalized_text: "МЕЛЬДОНИЙ КАПС 250 МГ №60",
    want: {
      input_explicit_mnn: "Мельдоний",
      input_explicit_strength: "strong",
      input_explicit_mnn_confidence: "high",
    },
  },
  {
    id: "explicit_strong_ambroxol",
    kind: "explicit",
    normalized_text: "АМБРОКСОЛ Вертекс 30 мг таблетки",
    want: {
      input_explicit_mnn: "Амброксол",
      input_explicit_strength: "strong",
    },
  },
  {
    id: "explicit_weak_multi",
    kind: "explicit",
    normalized_text: "ГЕСПЕРИДИН+ДИОСМИН 100мг+900мг",
    want: { input_explicit_strength: "weak" },
  },
  {
    id: "search_only_url_class",
    kind: "url_class",
    url: "https://uteka.ru/search/?query=амброксол",
    card_fetched: false,
    want: "listing",
  },
  {
    id: "search_only_no_url",
    kind: "url_class",
    url: null,
    card_fetched: false,
    want: "search_only",
  },
  {
    id: "product_card_url_class",
    kind: "url_class",
    url: "https://uteka.ru/product/ambroxol-vertex/",
    card_fetched: true,
    http_status: 200,
    want: "product_card",
  },
  {
    id: "gate_rejects_albendazole_for_diosmin",
    kind: "identity_gate",
    normalized_text: "ГЕСПЕРИДИН+ДИОСМИН 100мг+900мг",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/albendazole",
        title: "Албендазол 400 мг таблетки",
        raw_mnn: "Албендазол",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "asna",
        url: "https://asna.ru/cards/diosmin.html",
        title: "Гесперидин+Диосмин 100мг+900мг таблетки",
        raw_mnn: "Гесперидин + Диосмин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      rejected_mnn: ["Албендазол"],
      accepted_mnn: ["Гесперидин + Диосмин"],
    },
  },
  {
    id: "gate_rejects_valsartan_for_ambroxol",
    kind: "identity_gate",
    normalized_text: "АМБРОКСОЛ Вертекс 30 мг таблетки",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/valsartan-amlodipine",
        title: "Валсартан+Амлодипин 160мг+10мг таблетки",
        raw_mnn: "Валсартан, Амлодипин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "asna",
        url: "https://asna.ru/cards/ambroxol.html",
        title: "Амброксол Вертекс 30 мг таблетки",
        raw_mnn: "Амброксол",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      strength: "strong",
      explicit_mnn: "Амброксол",
      rejected_mnn: ["Валсартан, Амлодипин"],
      accepted_mnn: ["Амброксол"],
    },
  },
  {
    id: "gate_rejects_tolperisone_for_lidocaine",
    kind: "identity_gate",
    normalized_text: "ЛИДОКАИН Буфус раствор",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/tolperisone",
        title: "Толперизон 150 мг таблетки",
        raw_mnn: "Толперизон",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      strength: "strong",
      rejected_count: 1,
      accepted_count: 0,
    },
  },
  {
    id: "gate_rejects_unrelated_for_tamoxifen",
    kind: "identity_gate",
    normalized_text: "ТАМОКСИФЕН таблетки 20 мг",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/metronidazole",
        title: "Метронидазол 250 мг",
        raw_mnn: "Метронидазол",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "asna",
        url: "https://asna.ru/cards/tamoxifen.html",
        title: "Тамоксифен 20 мг таблетки",
        raw_mnn: "Тамоксифен",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      strength: "strong",
      rejected_mnn: ["Метронидазол"],
      accepted_mnn: ["Тамоксифен"],
    },
  },
  {
    id: "meldonium_strong_input_final",
    kind: "identity_resolve",
    normalized_text: "МЕЛЬДОНИЙ КАПС 250 МГ",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/atorvastatin",
        title: "Аторвастатин 20 мг",
        raw_mnn: "Аторвастатин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "asna",
        url: "https://asna.ru/cards/rosuvastatin.html",
        title: "Розувастатин 10 мг",
        raw_mnn: "Розувастатин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      final_mnn: "Мельдоний",
      final_method: "input_explicit_mnn",
      needs_review: false,
      rejected_vote_count: 2,
    },
  },
  {
    id: "atorvastatin_strong_rejects_unrelated",
    kind: "identity_resolve",
    normalized_text: "АТОРВАСТАТИН 20 мг таблетки",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/enalapril",
        title: "Эналаприл 10 мг",
        raw_mnn: "Эналаприл",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "vidal",
        url: "https://www.vidal.ru/drugs/atorvastatin",
        title: "Аторвастатин 20 мг таблетки",
        raw_mnn: "Аторвастатин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "asna",
        url: "https://asna.ru/cards/atorvastatin2.html",
        title: "Аторвастатин-СЗ 20 мг таблетки",
        raw_mnn: "Аторвастатин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      resolved_mnn: "Аторвастатин",
      status: "resolved_catalog",
      final_method: "catalog_consensus",
      rejected_vote_count: 1,
    },
  },
  {
    id: "valid_card_match_accepted",
    kind: "identity_gate",
    normalized_text: "ПАРАЦЕТАМОЛ 500 мг таблетки №10",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/paracetamol",
        title: "Парацетамол 500 мг таблетки №10",
        raw_mnn: "Парацетамол",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
        matched_form: "таблетки",
        matched_dosage: "500 мг",
        matched_pack: "10",
      },
    ],
    want: {
      accepted_count: 1,
      strength: "strong",
      explicit_mnn: "Парацетамол",
    },
  },
  {
    id: "single_source_matching_card",
    kind: "identity_resolve",
    normalized_text: "ПАРАЦЕТАМОЛ 500 мг таблетки",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/paracetamol",
        title: "Парацетамол 500 мг таблетки",
        raw_mnn: "Парацетамол",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      status: "unresolved_catalog",
      reason: "single_source",
      final_method: "input_explicit_mnn",
      final_mnn: "Парацетамол",
    },
  },
  {
    id: "no_url_cannot_vote",
    kind: "identity_resolve",
    normalized_text: "ИБУПРОФЕН 200 мг таблетки",
    sources: [
      {
        source: "uteka",
        url: null,
        title: "Ибупрофен 200 мг",
        raw_mnn: "Ибупрофен",
        source_class: "search_only",
        card_fetched: false,
      },
      {
        source: "asna",
        url: null,
        title: "Ибупрофен 200 мг",
        raw_mnn: "Ибупрофен",
        source_class: "search_only",
        card_fetched: false,
      },
    ],
    want: {
      resolved_mnn: null,
      rejected_vote_count: 2,
      final_method: "input_explicit_mnn",
      final_mnn: "Ибупрофен",
    },
  },
  {
    id: "search_only_cannot_vote_high_snippet",
    kind: "identity_gate",
    normalized_text: "ЛИЗИНОПРИЛ ТАБ 10 МГ",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/search/?query=лизиноприл",
        title: "Лизиноприл таб 10 мг — результаты поиска",
        raw_mnn: "Лизиноприл",
        source_class: "search_only",
        card_fetched: false,
      },
    ],
    want: {
      ambiguous_count: 1,
      accepted_count: 0,
      strength: "strong",
    },
  },
  {
    id: "rejected_excluded_from_frequency",
    kind: "identity_resolve",
    normalized_text: "РОЗУВАСТАТИН 10 мг таблетки",
    sources: [
      {
        source: "uteka",
        url: "https://uteka.ru/product/enalapril",
        title: "Эналаприл 10 мг",
        raw_mnn: "Эналаприл",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "asna",
        url: "https://asna.ru/cards/rosuvastatin.html",
        title: "Розувастатин 10 мг таблетки",
        raw_mnn: "Розувастатин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
      {
        source: "vidal",
        url: "https://www.vidal.ru/drugs/rosuvastatin-canon",
        title: "Розувастатин Канон 10 мг таблетки",
        raw_mnn: "Розувастатин",
        source_class: "product_card",
        card_fetched: true,
        http_status: 200,
      },
    ],
    want: {
      resolved_mnn: "Розувастатин",
      status: "resolved_catalog",
      rejected_vote_count: 1,
    },
  },
];

function matchWant(got, want) {
  if (want === null || typeof want !== "object") {
    return got === want;
  }
  if (Array.isArray(want)) {
    return JSON.stringify(got) === JSON.stringify(want);
  }
  for (const [k, v] of Object.entries(want)) {
    if (JSON.stringify(got[k]) !== JSON.stringify(v)) return false;
  }
  return true;
}

const res = spawnSync("/usr/bin/python3", ["-c", py], {
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
  const ok = matchWant(r.got, r.want);
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
