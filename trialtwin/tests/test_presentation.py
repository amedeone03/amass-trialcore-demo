"""Tests for display helpers (no Streamlit DOM)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trialtwin.engine import calculate_similarity
from trialtwin.models import HistoricalTrial, Protocol
from trialtwin.presentation import (
    candidate_set_caption,
    coverage_line,
    format_why_value,
    low_coverage_warning,
    ranking_against_caption,
    should_show_demo_outcomes,
    source_badge,
    source_is_live,
)
from trialtwin.app import load_trials_safely


class PresentationHelperTests(unittest.TestCase):
    def test_live_source_hides_outcome_profile(self) -> None:
        self.assertTrue(source_is_live("LIVE AMASS"))
        self.assertFalse(should_show_demo_outcomes("LIVE AMASS"))
        self.assertTrue(should_show_demo_outcomes("LOCAL DEMO DATA"))
        self.assertEqual(source_badge("LIVE AMASS")[0], "AMASS TRIALCORE")
        self.assertEqual(source_badge("LOCAL DEMO DATA")[0], "LOCAL SYNTHETIC DATA")

    def test_candidate_count_labeling(self) -> None:
        self.assertEqual(
            candidate_set_caption(97),
            "Closest matches among 97 retrieved historical candidates",
        )
        self.assertEqual(
            ranking_against_caption(97),
            "Ranking against 97 retrieved Phase III Alzheimer trials",
        )

    def test_unknown_why_value_is_not_different(self) -> None:
        self.assertEqual(format_why_value("duration_months", "unknown"), "Unknown in source data")
        self.assertEqual(format_why_value("intervention", "ambiguous: a | b"), "Unknown in source data")

    def test_low_coverage_warning_helper(self) -> None:
        protocol = Protocol(
            intervention="x",
            disease_stage="early",
            biomarker_strategy=True,
            sample_size=1800,
            duration_months=18,
            primary_endpoint="CDR-SB",
        )
        trial = HistoricalTrial(
            id="T",
            title="t",
            disease="Alzheimer's disease",
            phase="Phase III",
            intervention="x",
            disease_stage="unknown",
            biomarker_strategy=None,
            sample_size=None,
            duration_months=None,
            primary_endpoint="unknown",
            outcome_class="unknown",
            why_stopped="unknown",
        )
        result = calculate_similarity(protocol, trial)
        warning = low_coverage_warning(result)
        self.assertIsNotNone(warning)
        self.assertIn("coverage", warning.lower())
        self.assertIn("coverage", coverage_line(result).lower())

    def test_load_trials_safely_does_not_swallow_typeerror(self) -> None:
        with patch("trialtwin.app.load_cached_historical_set", side_effect=TypeError("bug")):
            with self.assertRaises(TypeError):
                load_trials_safely()
