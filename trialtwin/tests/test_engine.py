"""Deterministic tests for the TrialTwin similarity engine."""

from __future__ import annotations

import unittest
from dataclasses import replace

from trialtwin.engine import (
    DEFAULT_CONFIG,
    FEATURE_WEIGHTS,
    compare_protocol_scenarios,
    calculate_similarity,
    rank_historical_trials,
    summarize_historical_neighborhood,
)
from trialtwin.models import HistoricalTrial, Protocol


def _trial(**overrides: object) -> HistoricalTrial:
    base: dict[str, object] = {
        "id": "T-A",
        "title": "Trial A",
        "disease": "Alzheimer's disease",
        "phase": "Phase III",
        "target": "amyloid-beta",
        "disease_stage": "early",
        "biomarker_strategy": True,
        "sample_size": 1800,
        "duration_months": 18,
        "primary_endpoint": "CDR-SB",
        "outcome_class": "favorable",
        "why_stopped": "demo",
    }
    base.update(overrides)
    return HistoricalTrial(**base)  # type: ignore[arg-type]


def _protocol(**overrides: object) -> Protocol:
    base: dict[str, object] = {
        "disease": "Alzheimer's disease",
        "phase": "Phase III",
        "target": "amyloid-beta",
        "disease_stage": "early",
        "biomarker_strategy": True,
        "sample_size": 1800,
        "duration_months": 18,
        "primary_endpoint": "CDR-SB",
    }
    base.update(overrides)
    return Protocol(**base)  # type: ignore[arg-type]


class SimilarityEngineTests(unittest.TestCase):
    def test_weights_sum_to_one(self) -> None:
        self.assertAlmostEqual(sum(FEATURE_WEIGHTS.values()), 1.0)

    def test_exact_match(self) -> None:
        result = calculate_similarity(_protocol(), _trial())
        self.assertAlmostEqual(result.similarity_score, 1.0)
        self.assertTrue(all(item.status == "match" for item in result.feature_comparisons))
        self.assertAlmostEqual(
            sum(item.contribution for item in result.feature_comparisons), 1.0
        )
        self.assertEqual(result.historical_outcome_class, "favorable")

    def test_complete_mismatch(self) -> None:
        protocol = _protocol()
        trial = _trial(
            id="T-Z",
            disease="Parkinson's disease",
            phase="Phase II",
            target="tau",
            disease_stage="moderate",
            biomarker_strategy=False,
            primary_endpoint="ADAS-Cog",
            duration_months=36,
            sample_size=3800,
        )
        result = calculate_similarity(protocol, trial)
        self.assertAlmostEqual(result.similarity_score, 0.0)
        self.assertTrue(all(item.status == "mismatch" for item in result.feature_comparisons))
        self.assertTrue(all(item.contribution == 0.0 for item in result.feature_comparisons))

    def test_partial_numerical_similarity(self) -> None:
        protocol = _protocol(duration_months=18, sample_size=1800)
        trial = _trial(duration_months=12, sample_size=1800)
        result = calculate_similarity(protocol, trial)
        duration = next(
            item for item in result.feature_comparisons if item.feature_name == "duration_months"
        )
        self.assertEqual(duration.status, "partial")
        expected = max(0.0, 1.0 - abs(18 - 12) / DEFAULT_CONFIG.numeric_scales["duration_months"])
        self.assertAlmostEqual(duration.contribution, FEATURE_WEIGHTS["duration_months"] * expected)
        self.assertGreater(result.similarity_score, 0.0)
        self.assertLess(result.similarity_score, 1.0)

    def test_missing_historical_field_is_unknown_not_mismatch(self) -> None:
        protocol = _protocol()
        trial = _trial(biomarker_strategy=None, disease_stage="unknown")
        result = calculate_similarity(protocol, trial)
        by_name = {item.feature_name: item for item in result.feature_comparisons}
        self.assertEqual(by_name["biomarker_strategy"].status, "unknown")
        self.assertEqual(by_name["disease_stage"].status, "unknown")
        self.assertEqual(by_name["biomarker_strategy"].contribution, 0.0)
        self.assertAlmostEqual(result.similarity_score, 1.0)
        matched = [
            item
            for item in result.feature_comparisons
            if item.status == "match"
        ]
        self.assertAlmostEqual(sum(item.contribution for item in matched), 1.0)

    def test_ambiguous_target_is_unknown(self) -> None:
        result = calculate_similarity(
            _protocol(),
            _trial(target="ambiguous: lecanemab | donanemab"),
        )
        target = next(item for item in result.feature_comparisons if item.feature_name == "target")
        self.assertEqual(target.status, "unknown")
        self.assertAlmostEqual(result.similarity_score, 1.0)

    def test_ranking_descending(self) -> None:
        protocol = _protocol()
        close = _trial(id="T-CLOSE")
        far = _trial(
            id="T-FAR",
            disease_stage="moderate",
            biomarker_strategy=False,
            primary_endpoint="ADAS-Cog",
            target="tau",
        )
        ranked = rank_historical_trials(protocol, [far, close])
        self.assertEqual([item.trial_id for item in ranked], ["T-CLOSE", "T-FAR"])
        self.assertGreater(ranked[0].similarity_score, ranked[1].similarity_score)

    def test_deterministic_tie_breaking(self) -> None:
        protocol = _protocol()
        first = _trial(id="T-B", title="B")
        second = _trial(id="T-A", title="A")
        ranked = rank_historical_trials(protocol, [first, second])
        self.assertEqual(ranked[0].similarity_score, ranked[1].similarity_score)
        self.assertEqual([item.trial_id for item in ranked], ["T-A", "T-B"])

    def test_what_if_scenario_comparison(self) -> None:
        with_biomarker = _protocol(biomarker_strategy=True)
        without_biomarker = _protocol(biomarker_strategy=False)
        enriched = _trial(id="ENRICHED", biomarker_strategy=True)
        unenriched = _trial(id="UNENRICHED", biomarker_strategy=False)
        comparison = compare_protocol_scenarios(
            with_biomarker,
            without_biomarker,
            [enriched, unenriched],
            top_k=1,
        )
        self.assertEqual(comparison.ranking_a[0].trial_id, "ENRICHED")
        self.assertEqual(comparison.ranking_b[0].trial_id, "UNENRICHED")
        self.assertEqual(comparison.note, "historical neighborhood changed.")
        self.assertIn("ENRICHED", comparison.top_matches_only_in_a)
        self.assertIn("UNENRICHED", comparison.top_matches_only_in_b)
        changed_ids = {item.trial_id for item in comparison.changed_rankings}
        self.assertEqual(changed_ids, {"ENRICHED", "UNENRICHED"})

    def test_neighborhood_summary_is_descriptive(self) -> None:
        protocol = _protocol()
        trials = [
            _trial(id="A", outcome_class="favorable"),
            _trial(id="B", outcome_class="unfavorable"),
            _trial(id="C", outcome_class="unclear"),
        ]
        ranked = rank_historical_trials(protocol, trials)
        summary = summarize_historical_neighborhood(ranked, top_k=3)
        self.assertEqual(summary.label, "Historical outcome profile of closest matches")
        self.assertEqual(summary.favorable, 1)
        self.assertEqual(summary.unfavorable, 1)
        self.assertEqual(summary.unclear, 1)
        self.assertEqual(summary.unknown, 0)
        self.assertNotIn("probability", summary.label.lower())
        self.assertNotIn("success rate", summary.label.lower())

    def test_score_is_reproducible(self) -> None:
        protocol = _protocol(duration_months=18, sample_size=900)
        trial = _trial(duration_months=9, sample_size=400)
        first = calculate_similarity(protocol, trial)
        second = calculate_similarity(replace(protocol), replace(trial))
        self.assertEqual(first.similarity_score, second.similarity_score)
        self.assertEqual(
            [item.contribution for item in first.feature_comparisons],
            [item.contribution for item in second.feature_comparisons],
        )

    def test_every_feature_has_a_comparison(self) -> None:
        result = calculate_similarity(_protocol(), _trial())
        names = [item.feature_name for item in result.feature_comparisons]
        self.assertEqual(
            names,
            [
                "disease",
                "phase",
                "disease_stage",
                "biomarker_strategy",
                "primary_endpoint",
                "duration_months",
                "sample_size",
                "target",
            ],
        )


if __name__ == "__main__":
    unittest.main()
