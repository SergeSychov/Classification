#!/usr/bin/env python3
"""Offline fixture tests for RX/OTC evidence contract v2. No network."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_rx_otc_m3_2b_one_item as m  # noqa: E402


def _ident() -> dict:
    return m.build_identity(dict(m.DEFAULT_SKU))


class EvidenceContractV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        m.set_network_enabled(False)

    def test_network_disabled_blocks_http(self) -> None:
        with self.assertRaises(RuntimeError):
            m.http_get("http://127.0.0.1/")

    def test_a_non_fetched_snippet_is_discovery_only(self) -> None:
        hit = m.make_discovery_hit(
            url="https://example.invalid/flukonazol-obl",
            title="Флуконазол-OBL — инструкция",
            snippet="Без рецепта",
            query_kind="grls_primary",
            query='"ФЛУКОНАЗОЛ-OBL" "капсулы" "150 мг"',
        )
        self.assertFalse(hit["from_fetch"])
        for forbidden in (
            "explicit_status_text",
            "status_pattern",
            "validation_passed",
            "candidate_rx_otc_value",
        ):
            self.assertNotIn(forbidden, hit)
        ident = _ident()
        resolved = m.resolve_from_validated([])
        self.assertIsNone(resolved["candidate_rx_otc_value"])
        self.assertIsNone(resolved["final_rx_otc_value"])
        self.assertEqual(resolved["outcome"], "unresolved")
        # Snippet cannot become validated evidence.
        self.assertNotIn("validation_passed", hit)
        self.assertIsNone(resolved["candidate_rx_otc_value"])

    def test_b_fetched_vidal_p2_candidate_otc_final_null(self) -> None:
        ident = _ident()
        url = m.VIDAL_OBL_URL
        doc = m.make_fetched_document(
            url=url,
            query_kind="support_card",
            http_status=200,
            retrieved_at="2026-08-18T00:00:00+00:00",
            raw_artifact_path="redesign/artifacts/mnn_rx_otc_retrieval_v1_searxng_raw.jsonl",
            source_type="rls_or_vidal_product_card",
            source_tier="P2",
            page_title="Флуконазол-OBL инструкция по применению",
            page_text_excerpt=(
                "Лекарственные формы Флуконазол-OBL Без рецепта "
                "Капсулы 150 мг: 1 шт. РУ: ЛП-№(001911)-(РГ-RU)"
            ),
        )
        ev = m.validate_fetched_document(doc, ident)
        self.assertTrue(ev["from_fetch"])
        self.assertEqual(ev["http_status"], 200)
        self.assertEqual(ev["source_tier"], "P2")
        self.assertEqual(ev["identity_grade"], "A")
        self.assertTrue(ev["validation_passed"])
        self.assertEqual(ev["candidate_rx_otc_value"], "otc")
        resolved = m.resolve_from_validated([ev])
        self.assertEqual(resolved["outcome"], "supported_only")
        self.assertEqual(resolved["candidate_rx_otc_value"], "otc")
        self.assertIsNone(resolved["final_rx_otc_value"])
        self.assertEqual(resolved["evidence_tier"], "tier_2_supported_soft_signal")
        self.assertNotEqual(resolved["evidence_tier"], "tier_1_product_specific")

    def test_c_fetched_p1_may_set_final(self) -> None:
        ident = _ident()
        doc = m.make_fetched_document(
            url="https://grls.rosminzdrav.ru/Grls_View_v2.aspx?routingGuid=abc&idReg=123",
            query_kind="grls_primary",
            http_status=200,
            retrieved_at="2026-08-18T00:00:00+00:00",
            raw_artifact_path="fixture",
            source_type="grls_official_product_record",
            source_tier="P1",
            page_title="Флуконазол-OBL капсулы 150 мг",
            page_text_excerpt=(
                "Флуконазол-OBL капсулы 150 мг. "
                "Отпускается по рецепту. Производитель Оболенское."
            ),
        )
        ev = m.validate_fetched_document(doc, ident)
        self.assertEqual(ev["source_tier"], "P1")
        self.assertTrue(ev["validation_passed"])
        self.assertEqual(ev["candidate_rx_otc_value"], "rx")
        resolved = m.resolve_from_validated([ev])
        self.assertEqual(resolved["outcome"], "accepted")
        self.assertEqual(resolved["candidate_rx_otc_value"], "rx")
        self.assertEqual(resolved["final_rx_otc_value"], "rx")
        self.assertEqual(resolved["evidence_tier"], "tier_1_product_specific")

    def test_d_fetched_p3_cannot_set_candidate_or_final(self) -> None:
        ident = _ident()
        doc = m.make_fetched_document(
            url="https://www.rlsnet.ru/active-substance/flukonazol-543",
            query_kind="support_card",
            http_status=200,
            retrieved_at="2026-08-18T00:00:00+00:00",
            raw_artifact_path="fixture",
            source_type="generic_mnn_or_molecule_page",
            source_tier="P3",
            page_title="Флуконазол — вещество",
            page_text_excerpt="Флуконазол. Условия отпуска: по рецепту.",
        )
        ev = m.validate_fetched_document(doc, ident)
        self.assertEqual(ev["source_tier"], "P3")
        self.assertFalse(ev["validation_passed"])
        self.assertIsNone(ev["candidate_rx_otc_value"])
        resolved = m.resolve_from_validated([ev])
        self.assertIsNone(resolved["candidate_rx_otc_value"])
        self.assertIsNone(resolved["final_rx_otc_value"])
        self.assertNotEqual(resolved["outcome"], "accepted")
        result = {
            "discovery_hits": [],
            "fetched_documents": [doc],
            "validated_evidence": [ev],
            "final_rx_otc_value": resolved["final_rx_otc_value"],
        }
        val = m.contract_validation(result)
        self.assertEqual(val["p3_candidate_count"], 0)


def run_fixture_suite() -> dict:
    m.set_network_enabled(False)
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromTestCase(EvidenceContractV2Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    cases = {
        "A_non_fetched_snippet": None,
        "B_fetched_vidal_p2": None,
        "C_fetched_p1": None,
        "D_fetched_p3": None,
    }
    mapping = {
        "test_a_non_fetched_snippet_is_discovery_only": "A_non_fetched_snippet",
        "test_b_fetched_vidal_p2_candidate_otc_final_null": "B_fetched_vidal_p2",
        "test_c_fetched_p1_may_set_final": "C_fetched_p1",
        "test_d_fetched_p3_cannot_set_candidate_or_final": "D_fetched_p3",
    }
    failed = {t._testMethodName for t, _ in result.failures + result.errors}
    for method, key in mapping.items():
        cases[key] = "PASS" if method not in failed else "FAIL"
    return {
        "ok": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "cases": cases,
    }


if __name__ == "__main__":
    out = run_fixture_suite()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    raise SystemExit(0 if out["ok"] else 1)
