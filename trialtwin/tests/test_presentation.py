"""Tests for display helpers (no Streamlit DOM)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trialtwin.amass_client import load_local_trials
from trialtwin.app import demo_scenario_bundle, load_trials_safely
from trialtwin.engine import calculate_similarity, compare_protocol_scenarios
from trialtwin.models import HistoricalTrial, Protocol, load_historical_trials
from trialtwin.presentation import (
    APP_STATE_VERSION,
    DEMO_PROTOCOL_A,
    DEMO_PROTOCOL_B,
    DEMO_SOURCE,
    STATE_VERSION_KEY,
    candidate_set_caption,
    coverage_line,
    format_why_value,
    intervention_choices,
    low_coverage_warning,
    migrate_owned_session_state,
    ranking_against_caption,
    should_show_demo_outcomes,
    source_badge,
    source_is_live,
)


class PresentationHelperTests(unittest.TestCase):
    def test_live_source_hides_outcome_profile(self) -> None:
        self.assertTrue(source_is_live("LIVE AMASS"))
        self.assertFalse(should_show_demo_outcomes("LIVE AMASS"))
        self.assertTrue(should_show_demo_outcomes(DEMO_SOURCE))
        self.assertEqual(source_badge("LIVE AMASS")[0], "AMASS TRIALCORE")
        self.assertEqual(source_badge(DEMO_SOURCE)[0], "LOCAL SYNTHETIC DEMO")

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
        self.assertIn("limited comparable data", warning.lower())
        self.assertIn("%", coverage_line(result))

    def test_load_trials_safely_does_not_swallow_typeerror(self) -> None:
        with patch("trialtwin.app.load_cached_historical_set", side_effect=TypeError("bug")):
            with self.assertRaises(TypeError):
                load_trials_safely()

    def test_local_trials_have_intervention(self) -> None:
        trials = load_historical_trials()
        self.assertTrue(trials)
        self.assertTrue(all(hasattr(trial, "intervention") for trial in trials))
        self.assertTrue(intervention_choices(trials))

    def test_demo_bundle_never_calls_amass(self) -> None:
        with patch("trialtwin.app.get_historical_trials") as fetch:
            with patch("trialtwin.amass_client.fetch_alzheimer_phase3_trials") as live:
                trials, source, note, protocol_a, protocol_b = demo_scenario_bundle()
        fetch.assert_not_called()
        live.assert_not_called()
        self.assertEqual(source, DEMO_SOURCE)
        self.assertEqual(len(trials), 6)
        self.assertEqual(protocol_a, DEMO_PROTOCOL_A)
        self.assertEqual(protocol_b, DEMO_PROTOCOL_B)
        self.assertEqual(protocol_a.primary_endpoint, "ADAS-Cog")
        self.assertEqual(protocol_a.disease_stage, "Late")
        self.assertTrue(protocol_a.biomarker_strategy)
        self.assertFalse(protocol_b.biomarker_strategy)
        self.assertIn("Synthetic", note)

    def test_demo_scenario_changes_neighborhood(self) -> None:
        trials = load_local_trials()
        comparison = compare_protocol_scenarios(
            DEMO_PROTOCOL_A, DEMO_PROTOCOL_B, trials, top_k=3
        )
        top_a = {item.trial_id for item in comparison.ranking_a[:3]}
        top_b = {item.trial_id for item in comparison.ranking_b[:3]}
        self.assertNotEqual(top_a, top_b)

    def test_state_migration_clears_stale_keys(self) -> None:
        state = {
            STATE_VERSION_KEY: 1,
            "scenario_a": object(),
            "protocol_target": "amyloid-beta",
            "matches_requested": True,
            "stInternal": "keep",
        }
        migrated = migrate_owned_session_state(state, current_version=APP_STATE_VERSION)
        self.assertTrue(migrated)
        self.assertEqual(state[STATE_VERSION_KEY], APP_STATE_VERSION)
        self.assertNotIn("scenario_a", state)
        self.assertNotIn("protocol_target", state)
        self.assertNotIn("matches_requested", state)
        self.assertEqual(state["stInternal"], "keep")

    def test_state_migration_preserves_matching_version(self) -> None:
        state = {
            STATE_VERSION_KEY: APP_STATE_VERSION,
            "scenario_a": "keep-me",
            "matches_requested": True,
        }
        migrated = migrate_owned_session_state(state, current_version=APP_STATE_VERSION)
        self.assertFalse(migrated)
        self.assertEqual(state["scenario_a"], "keep-me")
        self.assertTrue(state["matches_requested"])
