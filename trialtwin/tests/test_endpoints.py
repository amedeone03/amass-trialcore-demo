"""Deterministic primary-endpoint canonicalization tests."""

from __future__ import annotations

import unittest

from trialtwin.endpoints import canonicalize_endpoint, canonicalize_endpoint_list


class EndpointCanonicalizationTests(unittest.TestCase):
    def test_cdr_sb_variants(self) -> None:
        for text in (
            "CDR-SB",
            "CDRSB",
            "cdr sb",
            "Clinical Dementia Rating Sum of Boxes",
            "Clinical Dementia Rating-Sum of Boxes",
        ):
            self.assertEqual(canonicalize_endpoint(text), "CDR-SB", text)

    def test_adas_cog_variants(self) -> None:
        for text in (
            "ADAS-Cog",
            "ADAS Cog",
            "ADASCog",
            "Alzheimer's Disease Assessment Scale-Cognitive",
            "Alzheimer's Disease Assessment Scale Cognitive Subscale",
        ):
            self.assertEqual(canonicalize_endpoint(text), "ADAS-Cog", text)

    def test_mmse(self) -> None:
        self.assertEqual(canonicalize_endpoint("MMSE"), "MMSE")
        self.assertEqual(canonicalize_endpoint("Mini-Mental State Examination"), "MMSE")

    def test_adcs_adl(self) -> None:
        self.assertEqual(canonicalize_endpoint("ADCS-ADL"), "ADCS-ADL")
        self.assertEqual(
            canonicalize_endpoint("Alzheimer's Disease Cooperative Study-ADL"),
            "ADCS-ADL",
        )

    def test_unknown_endpoint(self) -> None:
        self.assertEqual(
            canonicalize_endpoint("time to clinical progression"),
            "other: time to clinical progression",
        )
        self.assertEqual(canonicalize_endpoint(""), "unknown")
        self.assertEqual(canonicalize_endpoint(None), "unknown")

    def test_ambiguous_multi_endpoint(self) -> None:
        canonical, raw = canonicalize_endpoint_list(["CDR-SB", "ADAS-Cog"])
        self.assertTrue(canonical.startswith("ambiguous:"))
        self.assertIn("CDR-SB", canonical)
        self.assertIn("ADAS-Cog", canonical)
        self.assertEqual(raw, "CDR-SB | ADAS-Cog")

    def test_same_family_not_ambiguous(self) -> None:
        canonical, raw = canonicalize_endpoint_list(
            ["CDR-SB", "Clinical Dementia Rating Sum of Boxes"]
        )
        self.assertEqual(canonical, "CDR-SB")
        self.assertIn("CDR-SB", raw)
