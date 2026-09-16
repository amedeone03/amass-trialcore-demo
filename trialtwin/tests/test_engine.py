"""Deterministic tests for the ProtocolNeighbor similarity engine."""

from __future__ import annotations

import unittest
from dataclasses import replace

from trialtwin.engine import (
    DEFAULT_CONFIG,
    FEATURE_ORDER,
    FEATURE_WEIGHTS,
    calculate_similarity,
    compare_protocol_scenarios,
    is_low_coverage,
    matches_candidate_pool,
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
        "intervention": "amyloid-beta",
        "disease_stage": "early",
        "biomarker_strategy": True,
        "sample_size": 1800,
        "duration_months": 18,
        "primary_endpoint": "CDR-SB",
        "outcome_class": "favorable",
        "why_stopped": "demo",
        "study_span_months": 40,
        "amass_id": "AMTC_a",
        "registry_id": "NCT1",
        "source_registry": "clinicaltrials_gov",
        "source_url": "https://clinicaltrials.gov/study/NCT1",
    }
    base.update(overrides)
    return HistoricalTrial(**base)  # type: ignore[arg-type]


def _protocol(**overrides: object) -> Protocol:
    base: dict[str, object] = {
        "disease": "Alzheimer's disease",
        "phase": "Phase III",
        "intervention": "amyloid-beta",
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
        self.assertNotIn("disease", FEATURE_ORDER)
        self.assertNotIn("phase", FEATURE_ORDER)
        self.assertNotIn("study_span_months", FEATURE_ORDER)

    def test_exact_match(self) -> None:
        result = calculate_similarity(_protocol(), _trial())
        self.assertAlmostEqual(result.similarity_score, 1.0)
        self.assertAlmostEqual(result.comparison_coverage, 1.0)
        self.assertEqual(result.comparable_feature_count, 6)
        self.assertEqual(result.total_feature_count, 6)
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
            intervention="tau",
            disease_stage="moderate",
            biomarker_strategy=False,
            primary_endpoint="ADAS-Cog",
            duration_months=36,
            sample_size=3800,
        )
        result = calculate_similarity(protocol, trial)
        self.assertAlmostEqual(result.similarity_score, 0.0)
        self.assertTrue(all(item.status == "mismatch" for item in result.feature_comparisons))

    def test_disease_and_phase_are_not_scored(self) -> None:
        protocol_ad = _protocol(disease="Alzheimer's disease", phase="Phase III")
        protocol_other = _protocol(disease="Parkinson's disease", phase="Phase II")
        trial = _trial()
        a = calculate_similarity(protocol_ad, trial)
        b = calculate_similarity(protocol_other, trial)
        self.assertEqual(a.similarity_score, b.similarity_score)
        names = [item.feature_name for item in a.feature_comparisons]
        self.assertNotIn("disease", names)
        self.assertNotIn("phase", names)

    def test_candidate_pool_filter_still_uses_disease_and_phase(self) -> None:
        self.assertTrue(matches_candidate_pool(_trial()))
        self.assertFalse(matches_candidate_pool(_trial(disease="Parkinson's disease")))
        self.assertFalse(matches_candidate_pool(_trial(phase="Phase II")))

    def test_intervention_is_scored(self) -> None:
        match = calculate_similarity(_protocol(), _trial())
        mismatch = calculate_similarity(_protocol(), _trial(id="T-B", intervention="tau"))
        self.assertGreater(match.similarity_score, mismatch.similarity_score)
        item = next(
            row for row in mismatch.feature_comparisons if row.feature_name == "intervention"
        )
        self.assertEqual(item.status, "mismatch")

    def test_canonical_endpoint_is_scored(self) -> None:
        result = calculate_similarity(
            _protocol(primary_endpoint="CDR-SB"),
            _trial(primary_endpoint="CDR-SB"),
        )
        item = next(
            row for row in result.feature_comparisons if row.feature_name == "primary_endpoint"
        )
        self.assertEqual(item.status, "match")

    def test_unknown_duration_excluded(self) -> None:
        result = calculate_similarity(_protocol(), _trial(duration_months=None))
        duration = next(
            item for item in result.feature_comparisons if item.feature_name == "duration_months"
        )
        self.assertEqual(duration.status, "unknown")
        self.assertEqual(duration.contribution, 0.0)
        self.assertLess(result.comparison_coverage, 1.0)
        self.assertAlmostEqual(result.similarity_score, 1.0)

    def test_study_span_never_scored(self) -> None:
        a = calculate_similarity(_protocol(), _trial(study_span_months=12))
        b = calculate_similarity(_protocol(), _trial(id="T-B", study_span_months=99))
        self.assertEqual(a.similarity_score, b.similarity_score)
        names = [item.feature_name for item in a.feature_comparisons]
        self.assertNotIn("study_span_months", names)

    def test_outcome_never_scored(self) -> None:
        protocol = _protocol()
        favorable = calculate_similarity(protocol, _trial(outcome_class="favorable"))
        unfavorable = calculate_similarity(
            protocol, _trial(id="T-B", outcome_class="unfavorable")
        )
        self.assertAlmostEqual(favorable.similarity_score, unfavorable.similarity_score)

    def test_provenance_never_scored(self) -> None:
        a = calculate_similarity(_protocol(), _trial(amass_id="A", registry_id="N1"))
        b = calculate_similarity(_protocol(), _trial(id="T-B", amass_id="B", registry_id="N2"))
        self.assertEqual(a.similarity_score, b.similarity_score)
        names = [item.feature_name for item in a.feature_comparisons]
        self.assertNotIn("amass_id", names)
        self.assertNotIn("source_url", names)

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

    def test_missing_historical_field_is_unknown_not_mismatch(self) -> None:
        protocol = _protocol()
        trial = _trial(biomarker_strategy=None, disease_stage="unknown")
        result = calculate_similarity(protocol, trial)
        by_name = {item.feature_name: item for item in result.feature_comparisons}
        self.assertEqual(by_name["biomarker_strategy"].status, "unknown")
        self.assertEqual(by_name["disease_stage"].status, "unknown")
        self.assertEqual(by_name["biomarker_strategy"].contribution, 0.0)
        self.assertAlmostEqual(result.similarity_score, 1.0)

    def test_ambiguous_intervention_is_unknown(self) -> None:
        result = calculate_similarity(
            _protocol(),
            _trial(intervention="ambiguous: lecanemab | donanemab"),
        )
        item = next(
            row for row in result.feature_comparisons if row.feature_name == "intervention"
        )
        self.assertEqual(item.status, "unknown")
        self.assertAlmostEqual(result.similarity_score, 1.0)

    def test_coverage_full_when_all_comparable(self) -> None:
        result = calculate_similarity(_protocol(), _trial())
        self.assertAlmostEqual(result.comparison_coverage, 1.0)
        self.assertEqual(result.comparable_feature_count, result.total_feature_count)

    def test_coverage_decreases_when_half_weight_unknown(self) -> None:
        # Make the two heaviest fields unknown: stage + biomarker = 8/15.
        result = calculate_similarity(
            _protocol(),
            _trial(disease_stage="unknown", biomarker_strategy=None),
        )
        expected = 1.0 - (FEATURE_WEIGHTS["disease_stage"] + FEATURE_WEIGHTS["biomarker_strategy"])
        self.assertAlmostEqual(result.comparison_coverage, expected)
        self.assertAlmostEqual(result.similarity_score, 1.0)
        # Remaining weight is 7/15 ≈ 0.467, below the 0.50 prototype warning.

    def test_high_similarity_can_still_have_low_coverage(self) -> None:
        result = calculate_similarity(
            _protocol(),
            _trial(
                disease_stage="unknown",
                biomarker_strategy=None,
                primary_endpoint="unknown",
                duration_months=None,
                sample_size=None,
            ),
        )
        self.assertAlmostEqual(result.similarity_score, 1.0)
        self.assertAlmostEqual(result.comparison_coverage, FEATURE_WEIGHTS["intervention"])
        self.assertTrue(is_low_coverage(result.comparison_coverage))
        self.assertEqual(result.comparable_feature_count, 1)

    def test_coverage_independent_from_similarity(self) -> None:
        high_sim_low_cov = calculate_similarity(
            _protocol(),
            _trial(
                disease_stage="unknown",
                biomarker_strategy=None,
                primary_endpoint="unknown",
                duration_months=None,
                sample_size=None,
            ),
        )
        low_sim_full_cov = calculate_similarity(
            _protocol(),
            _trial(
                intervention="tau",
                disease_stage="moderate",
                biomarker_strategy=False,
                primary_endpoint="ADAS-Cog",
                duration_months=36,
                sample_size=3800,
            ),
        )
        self.assertGreater(high_sim_low_cov.similarity_score, low_sim_full_cov.similarity_score)
        self.assertLess(high_sim_low_cov.comparison_coverage, low_sim_full_cov.comparison_coverage)

    def test_ranking_descending(self) -> None:
        protocol = _protocol()
        close = _trial(id="T-CLOSE")
        far = _trial(
            id="T-FAR",
            disease_stage="moderate",
            biomarker_strategy=False,
            primary_endpoint="ADAS-Cog",
            intervention="tau",
        )
        ranked = rank_historical_trials(protocol, [far, close])
        self.assertEqual([item.trial_id for item in ranked], ["T-CLOSE", "T-FAR"])

    def test_deterministic_tie_breaking(self) -> None:
        protocol = _protocol()
        first = _trial(id="T-B", title="B")
        second = _trial(id="T-A", title="A")
        ranked = rank_historical_trials(protocol, [first, second])
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

    def test_neighborhood_summary_is_descriptive(self) -> None:
        protocol = _protocol()
        trials = [
            _trial(id="A", outcome_class="favorable"),
            _trial(id="B", outcome_class="unfavorable"),
            _trial(id="C", outcome_class="unclear"),
        ]
        ranked = rank_historical_trials(protocol, trials)
        summary = summarize_historical_neighborhood(ranked, top_k=3)
        self.assertEqual(summary.favorable, 1)
        self.assertEqual(summary.unfavorable, 1)
        self.assertEqual(summary.unclear, 1)

    def test_score_is_reproducible(self) -> None:
        protocol = _protocol(duration_months=18, sample_size=900)
        trial = _trial(duration_months=9, sample_size=400)
        first = calculate_similarity(protocol, trial)
        second = calculate_similarity(replace(protocol), replace(trial))
        self.assertEqual(first.similarity_score, second.similarity_score)

    def test_every_feature_has_a_comparison(self) -> None:
        result = calculate_similarity(_protocol(), _trial())
        names = [item.feature_name for item in result.feature_comparisons]
        self.assertEqual(list(FEATURE_ORDER), names)

    def test_closer_duration_scores_higher(self) -> None:
        protocol = _protocol(duration_months=18)
        closer = calculate_similarity(protocol, _trial(id="NEAR", duration_months=12))
        farther = calculate_similarity(protocol, _trial(id="FAR", duration_months=36))
        self.assertGreater(closer.similarity_score, farther.similarity_score)


if __name__ == "__main__":
    unittest.main()
