"""Tests for visualization data helpers — not Plotly pixels."""

from __future__ import annotations

import unittest

from trialtwin.amass_client import load_local_trials
from trialtwin.app import demo_scenario_bundle, describe_protocol_changes
from trialtwin.engine import calculate_similarity, rank_historical_trials
from trialtwin.models import HistoricalTrial, Protocol
from trialtwin.presentation import DEMO_PROTOCOL_A, DEMO_PROTOCOL_B
from trialtwin.visualization import (
    CoveragePoint,
    build_match_fingerprint,
    build_match_profile,
    build_similarity_coverage_points,
    build_spotlight_rank_flow_data,
    calculate_neighborhood_shift,
    concise_trial_label,
    neighborhood_change_caption,
    scatter_is_informative,
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

    def test_concise_demo_labels(self) -> None:
        self.assertEqual(
            concise_trial_label("[DEMO/MOCK] Early Alzheimer's anti-amyloid Phase III with PET enrichment"),
            "Early anti-amyloid",
        )
        self.assertEqual(
            concise_trial_label("[DEMO/MOCK] Mild-to-moderate Alzheimer's tau-directed Phase III without enrichment"),
            "Tau-directed",
        )
        self.assertEqual(
            concise_trial_label("[DEMO/MOCK] Mild Alzheimer's BACE-inhibitor Phase III without biomarker selection"),
            "BACE inhibitor",
        )
        self.assertEqual(
            concise_trial_label("[DEMO/MOCK] Prodromal Alzheimer's amyloid Phase III with CSF enrichment"),
            "Prodromal amyloid",
        )
        self.assertEqual(
            concise_trial_label("[DEMO/MOCK] Moderate Alzheimer's symptomatic Phase III without enrichment"),
            "Moderate symptomatic",
        )
        self.assertEqual(
            concise_trial_label("[DEMO/MOCK] Mild-to-moderate Alzheimer's anti-amyloid Phase III with PET plus CSF"),
            "PET/CSF anti-amyloid",
        )

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
        self.assertTrue(by_id["A1"].dominant)
        self.assertTrue(by_id["B1"].dominant)
        self.assertFalse(by_id["A2"].dominant)
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

    def test_match_profile_preserves_engine_values(self) -> None:
        result = calculate_similarity(_protocol(), _trial("T"))
        profile = build_match_profile(result)
        labels = [axis.label for axis in profile.axes]
        self.assertEqual(
            labels,
            ["Intervention", "Disease stage", "Biomarker", "Endpoint", "Duration", "Sample size"],
        )
        by_name = {axis.feature_name: axis for axis in profile.axes}
        self.assertTrue(profile.can_draw)
        self.assertEqual(profile.comparable_count, 6)
        self.assertEqual(by_name["intervention"].similarity, 1.0)
        self.assertEqual(by_name["intervention"].display_pct, 100.0)
        self.assertEqual(by_name["intervention"].status, "Exact")
        self.assertEqual(by_name["sample_size"].similarity, 1.0)
        engine_by_name = {item.feature_name: item for item in result.feature_comparisons}
        self.assertEqual(engine_by_name["intervention"].similarity, 1.0)

        numeric_trial = HistoricalTrial(
            id="N",
            title="n",
            disease="Alzheimer's disease",
            phase="Phase III",
            intervention="amyloid-beta",
            disease_stage="early",
            biomarker_strategy=True,
            sample_size=800,
            duration_months=18,
            primary_endpoint="CDR-SB",
            outcome_class="unknown",
            why_stopped="unknown",
        )
        numeric = calculate_similarity(_protocol(), numeric_trial)
        sample = next(item for item in numeric.feature_comparisons if item.feature_name == "sample_size")
        expected = max(0.0, 1.0 - abs(1800 - 800) / 2000.0)
        self.assertAlmostEqual(sample.similarity, expected)
        axis = {item.feature_name: item for item in build_match_profile(numeric).axes}["sample_size"]
        self.assertAlmostEqual(axis.similarity, expected)
        self.assertAlmostEqual(axis.display_pct, expected * 100.0)
        self.assertEqual(axis.status, "Similar")

    def test_match_profile_unknown_is_not_a_midpoint(self) -> None:
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
        result = calculate_similarity(_protocol(), sparse)
        duration = next(item for item in result.feature_comparisons if item.feature_name == "duration_months")
        self.assertIsNone(duration.similarity)
        profile = build_match_profile(result)
        by_name = {axis.feature_name: axis for axis in profile.axes}
        self.assertFalse(by_name["duration_months"].available)
        self.assertIsNone(by_name["duration_months"].similarity)
        self.assertIsNone(by_name["duration_months"].display_pct)
        self.assertEqual(by_name["duration_months"].status, "Unknown")
        self.assertNotEqual(by_name["duration_months"].display_pct, 50.0)
        self.assertTrue(profile.can_draw)

    def test_match_profile_too_few_axes(self) -> None:
        sparse = HistoricalTrial(
            id="LIVE-LIKE",
            title="partial",
            disease="Alzheimer's disease",
            phase="Phase III",
            intervention="amyloid-beta",
            disease_stage="unknown",
            biomarker_strategy=None,
            sample_size=None,
            duration_months=None,
            primary_endpoint="unknown",
            outcome_class="unknown",
            why_stopped="unknown",
        )
        result = calculate_similarity(_protocol(), sparse)
        profile = build_match_profile(result)
        self.assertEqual(profile.comparable_count, 1)
        self.assertFalse(profile.can_draw)
        self.assertIn("Not enough comparable dimensions", profile.empty_reason)
        by_name = {axis.feature_name: axis for axis in profile.axes}
        self.assertTrue(by_name["intervention"].available)
        self.assertFalse(by_name["duration_months"].available)

    def test_demo_match_profile_is_six_axis(self) -> None:
        trials, _source, _note, _protocol_a, protocol_b = demo_scenario_bundle()
        ranking = rank_historical_trials(protocol_b, list(trials))
        profile = build_match_profile(ranking[0])
        self.assertEqual(len(profile.axes), 6)
        self.assertTrue(profile.can_draw)
        self.assertEqual(profile.comparable_count, 6)
        self.assertAlmostEqual(profile.comparison_coverage, ranking[0].comparison_coverage)
        self.assertTrue(any(axis.status == "Exact" for axis in profile.axes))
        self.assertTrue(any(axis.status == "Different" for axis in profile.axes))

    def test_radar_values_independent_from_coverage(self) -> None:
        full = calculate_similarity(_protocol(), _trial("F"))
        sparse = HistoricalTrial(
            id="S",
            title="s",
            disease="Alzheimer's disease",
            phase="Phase III",
            intervention="amyloid-beta",
            disease_stage="unknown",
            biomarker_strategy=None,
            sample_size=1800,
            duration_months=None,
            primary_endpoint="unknown",
            outcome_class="unknown",
            why_stopped="unknown",
        )
        limited = calculate_similarity(_protocol(), sparse)
        self.assertGreater(full.comparison_coverage, limited.comparison_coverage)
        full_axis = {axis.feature_name: axis for axis in build_match_profile(full).axes}["intervention"]
        limited_axis = {axis.feature_name: axis for axis in build_match_profile(limited).axes}["intervention"]
        self.assertEqual(full_axis.similarity, limited_axis.similarity)
        self.assertEqual(full_axis.display_pct, limited_axis.display_pct)
        self.assertNotEqual(full.comparison_coverage, limited.comparison_coverage)

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

    def test_scatter_hidden_when_coverage_is_uniform(self) -> None:
        protocol = _protocol()
        trials = [_trial("A"), _trial("B")]
        ranking = rank_historical_trials(protocol, trials)
        points = build_similarity_coverage_points(ranking, trials)
        self.assertFalse(scatter_is_informative(points))
        self.assertFalse(scatter_is_informative(()))
        varied = (
            points[0],
            CoveragePoint(
                trial_id="C",
                title="c",
                similarity_pct=40.0,
                coverage_pct=50.0,
                intervention="amyloid-beta",
                is_top=False,
            ),
        )
        self.assertTrue(scatter_is_informative(varied))

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
        labels = {row.trial_id: row.short_title for row in shift.rows}
        self.assertIn("Tau-directed", labels.values())
        self.assertIn("Early anti-amyloid", labels.values())
        local = load_local_trials()
        self.assertEqual(len(local), 6)
        points = build_similarity_coverage_points(ranking_b, list(trials))
        self.assertFalse(scatter_is_informative(points))

    def test_spotlight_rank_flow_flags_and_labels(self) -> None:
        protocol = _protocol()
        a1 = calculate_similarity(protocol, _trial("A1", "Early Alzheimer's anti-amyloid trial"))
        a2 = calculate_similarity(protocol, _trial("A2", "Prodromal Alzheimer's amyloid trial"))
        b1 = calculate_similarity(protocol, _trial("B1", "Mild-to-moderate Alzheimer's tau-directed trial"))
        ranking_a = [a1, a2]
        ranking_b = [b1, a1]
        shift = calculate_neighborhood_shift(ranking_a, ranking_b, top_k=1, chart_k=2)
        flow = build_spotlight_rank_flow_data(shift)
        by_id = {row.trial_id: row for row in flow}
        self.assertEqual(by_id["A1"].before_rank, 1)
        self.assertEqual(by_id["A1"].after_rank, 2)
        self.assertEqual(by_id["B1"].after_rank, 1)
        self.assertTrue(by_id["B1"].moved_in_top3)
        self.assertTrue(by_id["A1"].moved_out_top3)
        self.assertFalse(by_id["A1"].stayed_top3)
        self.assertTrue(by_id["A2"].contextual)
        self.assertEqual(by_id["A1"].short_label, "Early anti-amyloid")
        self.assertEqual(by_id["B1"].short_label, "Tau-directed")
        self.assertIn("Early Alzheimer's anti-amyloid trial", by_id["A1"].full_title)
        self.assertEqual(by_id["A1"].left_label, "#1 Early anti-amyloid")
        self.assertEqual(by_id["B1"].right_label, "#1 Tau-directed")
        self.assertIsNone(by_id["A2"].after_rank)
        self.assertEqual(build_spotlight_rank_flow_data(calculate_neighborhood_shift([], [])), ())

    def test_spotlight_stayed_top3(self) -> None:
        protocol = _protocol()
        a1 = calculate_similarity(protocol, _trial("A1", "Alpha one"))
        a2 = calculate_similarity(protocol, _trial("A2", "Alpha two"))
        ranking = [a1, a2]
        shift = calculate_neighborhood_shift(ranking, ranking, top_k=1, chart_k=2)
        flow = {row.trial_id: row for row in build_spotlight_rank_flow_data(shift)}
        self.assertTrue(flow["A1"].stayed_top3)
        self.assertFalse(flow["A1"].moved_in_top3)
        self.assertFalse(flow["A1"].moved_out_top3)
        self.assertTrue(flow["A2"].contextual)

    def test_demo_spotlight_top3_swap(self) -> None:
        trials, _source, _note, protocol_a, protocol_b = demo_scenario_bundle()
        shift = calculate_neighborhood_shift(
            rank_historical_trials(protocol_a, list(trials)),
            rank_historical_trials(protocol_b, list(trials)),
            top_k=3,
            chart_k=5,
        )
        flow = build_spotlight_rank_flow_data(shift)
        entered = {row.short_label for row in flow if row.moved_in_top3}
        left = {row.short_label for row in flow if row.moved_out_top3}
        self.assertEqual(entered, {"Tau-directed", "BACE inhibitor", "Moderate symptomatic"})
        self.assertEqual(left, {"Early anti-amyloid", "PET/CSF anti-amyloid", "Prodromal amyloid"})
        first_after = next(row for row in flow if row.after_rank == 1)
        first_before = next(row for row in flow if row.before_rank == 1)
        self.assertEqual(first_after.short_label, "Tau-directed")
        self.assertEqual(first_before.short_label, "Early anti-amyloid")
        self.assertTrue(all(row.before_rank is not None and row.after_rank is not None for row in flow))
        self.assertEqual(min(row.before_rank for row in flow), 1)
        self.assertEqual(min(row.after_rank for row in flow), 1)
        stayed = [row for row in flow if row.stayed_top3]
        self.assertEqual(stayed, [])
        by_id = {row.trial_id: row for row in flow}
        for source in shift.rows:
            prepared = by_id[source.trial_id]
            self.assertEqual(prepared.before_rank, source.rank_before)
            self.assertEqual(prepared.after_rank, source.rank_after)
            self.assertEqual(prepared.full_title, source.title)

    def test_spotlight_empty_and_partial_rankings(self) -> None:
        empty = build_spotlight_rank_flow_data(calculate_neighborhood_shift([], []))
        self.assertEqual(empty, ())
        protocol = _protocol()
        only_before = calculate_similarity(protocol, _trial("ONLY_A", "Early Alzheimer's anti-amyloid trial"))
        only_after = calculate_similarity(protocol, _trial("ONLY_B", "Mild-to-moderate Alzheimer's tau-directed trial"))
        shared = calculate_similarity(protocol, _trial("BOTH", "PET plus CSF anti-amyloid trial"))
        shift = calculate_neighborhood_shift([only_before, shared], [only_after, shared], top_k=1, chart_k=2)
        flow = {row.trial_id: row for row in build_spotlight_rank_flow_data(shift)}
        self.assertIsNone(flow["ONLY_A"].after_rank)
        self.assertIsNone(flow["ONLY_B"].before_rank)
        self.assertEqual(flow["BOTH"].before_rank, 2)
        self.assertEqual(flow["BOTH"].after_rank, 2)
        self.assertEqual(flow["ONLY_A"].before_similarity, only_before.similarity_score)
        self.assertIsNone(flow["ONLY_A"].after_similarity)
        self.assertFalse(any(row.before_rank == 0 or row.after_rank == 0 for row in flow.values()))
        self.assertEqual(flow["ONLY_A"].short_label, "Early anti-amyloid")
        self.assertIn("PET plus CSF", flow["BOTH"].full_title)
