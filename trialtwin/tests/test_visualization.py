"""Tests for visualization data helpers — not Plotly pixels."""

from __future__ import annotations

import unittest

from trialtwin.amass_client import load_local_trials
from trialtwin.app import demo_scenario_bundle, describe_protocol_changes
from trialtwin.engine import calculate_similarity, rank_historical_trials
from trialtwin.models import HistoricalTrial, Protocol
from trialtwin.presentation import DEMO_PROTOCOL_A, DEMO_PROTOCOL_B
from trialtwin.visualization import (
    build_match_fingerprint,
    build_similarity_coverage_points,
    calculate_neighborhood_shift,
    neighborhood_change_caption,
    shorten_title,
)


def _trial(trial_id: str, title: str = "") -> HistoricalTrial:
    return HistoricalTrial(
        id=trial_id,
        title=title or trial_id,
        disease="Alzheimer's disease",
        phase="Phase III",
        intervention="amyloid-beta",
        disease_stage="early",
        biomarker_strategy=True,
        sample_size=1800,
        duration_months=18,
        primary_endpoint="CDR-SB",
        outcome_class="unknown",
        why_stopped="unknown",
    )


def _protocol() -> Protocol:
    return Protocol(
        intervention="amyloid-beta",
        disease_stage="early",
        biomarker_strategy=True,
        sample_size=1800,
        duration_months=18,
        primary_endpoint="CDR-SB",
    )


class VisualizationHelperTests(unittest.TestCase):
    def test_shorten_title(self) -> None:
        self.assertEqual(shorten_title("Short"), "Short")
        self.assertTrue(shorten_title("x" * 80).endswith("..."))
        self.assertLessEqual(len(shorten_title("x" * 80)), 36)
        self.assertTrue(shorten_title("[DEMO/MOCK] Mild Alzheimer's BACE-inhibitor Phase III").startswith("Mild"))

    def test_empty_ranking(self) -> None:
        shift = calculate_neighborhood_shift([], [])
        self.assertFalse(shift.can_draw)
        self.assertEqual(shift.changed_count, 0)

    def test_one_result_does_not_draw(self) -> None:
        protocol = _protocol()
        only = calculate_similarity(protocol, _trial("ONLY"))
        shift = calculate_neighborhood_shift([only], [only])
        self.assertFalse(shift.can_draw)
        self.assertIn("two", shift.empty_reason)

    def test_union_ranks_moved_in_out(self) -> None:
        protocol = _protocol()
        a1 = calculate_similarity(protocol, _trial("A1", "Alpha one"))
        a2 = calculate_similarity(protocol, _trial("A2", "Alpha two"))
        b1 = calculate_similarity(protocol, _trial("B1", "Beta one"))
        ranking_a = [a1, a2]
        ranking_b = [b1, a1]
        shift = calculate_neighborhood_shift(ranking_a, ranking_b, top_k=1, chart_k=2)
        self.assertTrue(shift.can_draw)
        self.assertEqual(shift.changed_count, 1)
        self.assertTrue(shift.top_match_changed)
        self.assertEqual(shift.moved_out_ids, ("A1",))
        self.assertEqual(shift.moved_in_ids, ("B1",))
        ids = {row.trial_id for row in shift.rows}
        self.assertEqual(ids, {"A1", "A2", "B1"})
        by_id = {row.trial_id: row for row in shift.rows}
        self.assertEqual(by_id["A1"].rank_before, 1)
        self.assertEqual(by_id["A1"].rank_after, 2)
        self.assertEqual(by_id["B1"].movement, "moved_in")
        self.assertEqual(by_id["A1"].movement, "moved_out")
        self.assertEqual(by_id["A2"].rank_before, 2)
        self.assertIsNone(by_id["A2"].rank_after)
        self.assertIn("1 of 1", neighborhood_change_caption(shift))

    def test_fingerprint_status_mapping(self) -> None:
        result = calculate_similarity(_protocol(), _trial("T"))
        rows = build_match_fingerprint(result)
        self.assertEqual(len(rows), 6)
        by_name = {row.feature_name: row for row in rows}
        self.assertEqual(by_name["intervention"].status, "Exact")
        self.assertEqual(by_name["intervention"].fill, 10)
        sparse = HistoricalTrial(
            id="U",
            title="u",
            disease="Alzheimer's disease",
            phase="Phase III",
            intervention="amyloid-beta",
            disease_stage="unknown",
            biomarker_strategy=True,
            sample_size=1800,
            duration_months=None,
            primary_endpoint="CDR-SB",
            outcome_class="unknown",
            why_stopped="unknown",
        )
        unknown_rows = {
            row.feature_name: row
            for row in build_match_fingerprint(calculate_similarity(_protocol(), sparse))
        }
        self.assertEqual(unknown_rows["duration_months"].status, "Unknown")
        self.assertEqual(unknown_rows["duration_months"].fill, 0)
        self.assertEqual(unknown_rows["disease_stage"].status, "Unknown")

    def test_scatter_empty_ranking(self) -> None:
        self.assertEqual(build_similarity_coverage_points([], []), ())

    def test_scatter_points(self) -> None:
        protocol = _protocol()
        trials = [_trial("A"), _trial("B")]
        ranking = rank_historical_trials(protocol, trials)
        points = build_similarity_coverage_points(ranking, trials, top_k=1)
        self.assertEqual(len(points), 2)
        self.assertEqual(sum(1 for point in points if point.is_top), 1)
        self.assertTrue(all(0.0 <= point.similarity_pct <= 100.0 for point in points))
        self.assertTrue(all(point.intervention == "amyloid-beta" for point in points))

    def test_demo_changes_exactly_one_field(self) -> None:
        changes = describe_protocol_changes(DEMO_PROTOCOL_A, DEMO_PROTOCOL_B)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0], "Biomarker confirmation")
        self.assertEqual(changes[0][1], "Required")
        self.assertEqual(changes[0][2], "Not required")

    def test_demo_swaps_top_neighborhood(self) -> None:
        trials, _source, _note, protocol_a, protocol_b = demo_scenario_bundle()
        ranking_a = rank_historical_trials(protocol_a, list(trials))
        ranking_b = rank_historical_trials(protocol_b, list(trials))
        shift = calculate_neighborhood_shift(ranking_a, ranking_b, top_k=3, chart_k=5)
        self.assertEqual(shift.changed_count, 3)
        self.assertTrue(shift.top_match_changed)
        self.assertEqual(len(shift.moved_in_ids), 3)
        self.assertEqual(len(shift.moved_out_ids), 3)
        local = load_local_trials()
        self.assertEqual(len(local), 6)
