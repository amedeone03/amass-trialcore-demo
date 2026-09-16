"""Deterministic protocol-to-history similarity engine.

This is an interpretable prototype heuristic. Weights are not clinical
evidence and must not be presented as medically validated. Scores measure
resemblance only. They are not probabilities of success or failure.

Disease and phase define the candidate pool. They are not similarity features.
Calendar study span, outcome labels, and provenance never enter the score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from trialtwin.models import HistoricalTrial, OutcomeClass, Protocol

FeatureStatus = Literal["match", "partial", "mismatch", "unknown"]

# Design characteristics that can still vary after Alzheimer / Phase III filtering.
FEATURE_ORDER = (
    "intervention",
    "disease_stage",
    "biomarker_strategy",
    "primary_endpoint",
    "duration_months",
    "sample_size",
)

# Relative weights from the original prototype after dropping disease (0.15)
# and phase (0.10), then renormalized to sum to 1.0.
# Original remaining mass = 0.75.
# intervention remains 1/15 (~6.7%): a prototype leftover, not a clinical ranking.
FEATURE_WEIGHTS: dict[str, float] = {
    "disease_stage": 4.0 / 15.0,
    "biomarker_strategy": 4.0 / 15.0,
    "primary_endpoint": 3.0 / 15.0,
    "duration_months": 2.0 / 15.0,
    "sample_size": 1.0 / 15.0,
    "intervention": 1.0 / 15.0,
}

# Linear distance scales: similarity = max(0, 1 - |p - h| / scale).
NUMERIC_SCALES: dict[str, float] = {
    "duration_months": 18.0,
    "sample_size": 2000.0,
}

CATEGORICAL_FEATURES = frozenset(
    {
        "intervention",
        "disease_stage",
        "biomarker_strategy",
        "primary_endpoint",
    }
)
NUMERIC_FEATURES = frozenset({"duration_months", "sample_size"})

LOW_COVERAGE_THRESHOLD = 0.50

STATUS_MARK = {
    "match": "exact",
    "partial": "similar",
    "mismatch": "different",
    "unknown": "unknown",
}

LOCKED_DISEASE = "Alzheimer's disease"
LOCKED_PHASE = "Phase III"


@dataclass(frozen=True)
class SimilarityConfig:
    """Visible, editable heuristic configuration.

    These values are a prototype similarity heuristic, not clinical evidence.
    """

    weights: dict[str, float] = field(default_factory=lambda: dict(FEATURE_WEIGHTS))
    numeric_scales: dict[str, float] = field(default_factory=lambda: dict(NUMERIC_SCALES))

    def __post_init__(self) -> None:
        missing = [name for name in FEATURE_ORDER if name not in self.weights]
        if missing:
            raise ValueError(f"SimilarityConfig.weights missing features: {missing}")
        total = sum(self.weights[name] for name in FEATURE_ORDER)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Feature weights must sum to 1.00; got {total}.")
        for name in NUMERIC_FEATURES:
            scale = self.numeric_scales.get(name)
            if scale is None or scale <= 0:
                raise ValueError(f"numeric_scales[{name!r}] must be a positive number.")


DEFAULT_CONFIG = SimilarityConfig()


@dataclass(frozen=True)
class FeatureComparison:
    """One protocol feature compared with one historical-trial feature.

    ``similarity`` is the feature-level resemblance in [0, 1] before weight
    renormalization, or None when the field is unknown. ``contribution`` is
    that value after comparable-weight renormalization and is not a radar axis.
    """

    feature_name: str
    protocol_value: str
    historical_value: str
    status: FeatureStatus
    contribution: float
    explanation: str
    similarity: float | None


@dataclass(frozen=True)
class SimilarityResult:
    """Explainable resemblance between a protocol and one historical trial.

    ``similarity_score`` is resemblance among comparable fields only.
    ``comparison_coverage`` is the share of intended feature weight that had
    usable data. The two metrics are independent.
    """

    trial_id: str
    trial_title: str
    similarity_score: float
    feature_comparisons: tuple[FeatureComparison, ...]
    historical_outcome_class: OutcomeClass
    why_stopped: str
    comparable_feature_count: int
    total_feature_count: int
    comparison_coverage: float
    comparable_weight: float


@dataclass(frozen=True)
class NeighborhoodSummary:
    """Descriptive outcome counts among the closest historical matches.

    This is not a predicted success rate and must not be converted into one.
    """

    label: str
    top_k: int
    trial_ids: tuple[str, ...]
    favorable: int
    unfavorable: int
    unclear: int
    unknown: int


@dataclass(frozen=True)
class RankChange:
    """Rank position of one trial under two protocol scenarios."""

    trial_id: str
    rank_a: int
    rank_b: int


@dataclass(frozen=True)
class ScenarioComparison:
    """Side-by-side rankings for two protocols against the same history.

    Changes are neighborhood changes only. They are not improvements or
    worsenings and are not predictions.
    """

    ranking_a: tuple[SimilarityResult, ...]
    ranking_b: tuple[SimilarityResult, ...]
    changed_rankings: tuple[RankChange, ...]
    top_k: int
    top_matches_only_in_a: tuple[str, ...]
    top_matches_only_in_b: tuple[str, ...]
    note: str = "historical neighborhood changed."


def _is_unreliable_text(value: str | None) -> bool:
    if value is None:
        return True
    text = value.strip()
    if not text:
        return True
    lowered = text.casefold()
    return lowered == "unknown" or lowered.startswith("ambiguous:")


def _display(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        text = value.strip()
        return text if text else "unknown"
    return str(value)


def _categorical_values(
    protocol: Protocol, trial: HistoricalTrial, feature_name: str
) -> tuple[Any, Any]:
    return getattr(protocol, feature_name), getattr(trial, feature_name)


def _protocol_number(protocol: Protocol, feature_name: str) -> int | None:
    value = getattr(protocol, feature_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    return value


def _trial_number(trial: HistoricalTrial, feature_name: str) -> int | None:
    value = getattr(trial, feature_name)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _categorical_comparable(protocol_value: Any, historical_value: Any) -> bool:
    if historical_value is None or protocol_value is None:
        return False
    if isinstance(protocol_value, bool) or isinstance(historical_value, bool):
        return isinstance(protocol_value, bool) and isinstance(historical_value, bool)
    if isinstance(protocol_value, str) and isinstance(historical_value, str):
        return not _is_unreliable_text(protocol_value) and not _is_unreliable_text(
            historical_value
        )
    return False


def _categorical_equal(protocol_value: Any, historical_value: Any) -> bool:
    if isinstance(protocol_value, bool) and isinstance(historical_value, bool):
        return protocol_value is historical_value
    assert isinstance(protocol_value, str) and isinstance(historical_value, str)
    return protocol_value.strip().casefold() == historical_value.strip().casefold()


def _linear_numeric_similarity(protocol_value: int, historical_value: int, scale: float) -> float:
    """Prototype heuristic: max(0, 1 - |p - h| / scale). Linear, not clinical."""
    return max(0.0, 1.0 - abs(protocol_value - historical_value) / scale)


def matches_candidate_pool(
    trial: HistoricalTrial,
    *,
    disease: str = LOCKED_DISEASE,
    phase: str = LOCKED_PHASE,
) -> bool:
    """Eligibility filter. Not a similarity feature."""
    return (
        trial.disease.strip().casefold() == disease.strip().casefold()
        and trial.phase.strip().casefold() == phase.strip().casefold()
    )


def is_low_coverage(coverage: float, threshold: float = LOW_COVERAGE_THRESHOLD) -> bool:
    return coverage < threshold


def calculate_similarity(
    protocol: Protocol,
    historical_trial: HistoricalTrial,
    config: SimilarityConfig | None = None,
) -> SimilarityResult:
    """Compare protocol design fields with one historical trial.

    ``similarity_score`` is a weighted resemblance heuristic in [0, 1] over
    comparable fields only. Unknown fields are excluded from the score
    denominator. ``comparison_coverage`` is sum(weights of comparable fields)
    / sum(weights of all similarity fields).
    """
    cfg = config or DEFAULT_CONFIG
    raw: list[tuple[str, FeatureStatus, float, str, str, str]] = []

    for feature_name in FEATURE_ORDER:
        if feature_name in CATEGORICAL_FEATURES:
            protocol_value, historical_value = _categorical_values(
                protocol, historical_trial, feature_name
            )
            proto_text = _display(protocol_value)
            hist_text = _display(historical_value)
            if not _categorical_comparable(protocol_value, historical_value):
                raw.append(
                    (
                        feature_name,
                        "unknown",
                        0.0,
                        proto_text,
                        hist_text,
                        "No reliable value on one or both sides; excluded from the score denominator.",
                    )
                )
                continue
            if _categorical_equal(protocol_value, historical_value):
                raw.append(
                    (
                        feature_name,
                        "match",
                        1.0,
                        proto_text,
                        hist_text,
                        "Exact match. Full feature weight applies after renormalization.",
                    )
                )
            else:
                raw.append(
                    (
                        feature_name,
                        "mismatch",
                        0.0,
                        proto_text,
                        hist_text,
                        "Values differ. This feature contributes 0.",
                    )
                )
            continue

        protocol_number = _protocol_number(protocol, feature_name)
        trial_number = _trial_number(historical_trial, feature_name)
        proto_text = _display(protocol_number)
        hist_text = _display(trial_number)
        if protocol_number is None or trial_number is None:
            raw.append(
                (
                    feature_name,
                    "unknown",
                    0.0,
                    proto_text,
                    hist_text,
                    "No reliable numeric value on one or both sides; excluded from the score denominator.",
                )
            )
            continue
        scale = cfg.numeric_scales[feature_name]
        similarity = _linear_numeric_similarity(protocol_number, trial_number, scale)
        if similarity == 1.0:
            status: FeatureStatus = "match"
            explanation = (
                f"Exact numeric match. Linear heuristic with scale={scale:g}."
            )
        elif similarity == 0.0:
            status = "mismatch"
            explanation = (
                f"Absolute difference is at least the scale ({scale:g}); contribution is 0. "
                "Prototype linear distance, not a clinical model."
            )
        else:
            status = "partial"
            explanation = (
                f"Partial numeric resemblance: max(0, 1 - |{protocol_number} - {trial_number}| "
                f"/ {scale:g}) = {similarity:.4f}. Prototype linear heuristic."
            )
        raw.append((feature_name, status, similarity, proto_text, hist_text, explanation))

    comparable_weight = sum(
        cfg.weights[name] for name, status, *_ in raw if status != "unknown"
    )
    total_weight = sum(cfg.weights[name] for name in FEATURE_ORDER)
    comparison_coverage = comparable_weight / total_weight if total_weight else 0.0
    comparable_feature_count = sum(1 for _, status, *_ in raw if status != "unknown")
    total_feature_count = len(FEATURE_ORDER)

    comparisons: list[FeatureComparison] = []
    score = 0.0
    for feature_name, status, similarity, proto_text, hist_text, explanation in raw:
        weight = cfg.weights[feature_name]
        if status == "unknown" or comparable_weight == 0.0:
            contribution = 0.0
        else:
            contribution = (weight / comparable_weight) * similarity
            score += contribution
        comparisons.append(
            FeatureComparison(
                feature_name=feature_name,
                protocol_value=proto_text,
                historical_value=hist_text,
                status=status,
                contribution=contribution,
                explanation=explanation,
                similarity=None if status == "unknown" else similarity,
            )
        )

    return SimilarityResult(
        trial_id=historical_trial.id,
        trial_title=historical_trial.title,
        similarity_score=score,
        feature_comparisons=tuple(comparisons),
        historical_outcome_class=historical_trial.outcome_class,
        why_stopped=historical_trial.why_stopped,
        comparable_feature_count=comparable_feature_count,
        total_feature_count=total_feature_count,
        comparison_coverage=comparison_coverage,
        comparable_weight=comparable_weight,
    )


def rank_historical_trials(
    protocol: Protocol,
    historical_trials: list[HistoricalTrial],
    config: SimilarityConfig | None = None,
) -> list[SimilarityResult]:
    """Score every trial and sort by score descending, then trial_id ascending."""
    results = [
        calculate_similarity(protocol, trial, config=config) for trial in historical_trials
    ]
    results.sort(key=lambda item: (-item.similarity_score, item.trial_id))
    return results


def summarize_historical_neighborhood(
    results: list[SimilarityResult],
    top_k: int = 5,
) -> NeighborhoodSummary:
    """Count descriptive outcome labels among the closest matches.

    Do not treat these counts as a probability of success or failure.
    """
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    selected = results[:top_k]
    counts = {"favorable": 0, "unfavorable": 0, "unclear": 0, "unknown": 0}
    for item in selected:
        counts[item.historical_outcome_class] = counts.get(item.historical_outcome_class, 0) + 1
    return NeighborhoodSummary(
        label="Historical outcome profile of closest matches",
        top_k=len(selected),
        trial_ids=tuple(item.trial_id for item in selected),
        favorable=counts["favorable"],
        unfavorable=counts["unfavorable"],
        unclear=counts["unclear"],
        unknown=counts["unknown"],
    )


def compare_protocol_scenarios(
    protocol_a: Protocol,
    protocol_b: Protocol,
    trials: list[HistoricalTrial],
    *,
    top_k: int = 5,
    config: SimilarityConfig | None = None,
) -> ScenarioComparison:
    """Rank the same history under two protocols. Reports neighborhood change only."""
    ranking_a = rank_historical_trials(protocol_a, trials, config=config)
    ranking_b = rank_historical_trials(protocol_b, trials, config=config)
    rank_a = {item.trial_id: index + 1 for index, item in enumerate(ranking_a)}
    rank_b = {item.trial_id: index + 1 for index, item in enumerate(ranking_b)}
    changed = tuple(
        RankChange(trial_id=trial_id, rank_a=rank_a[trial_id], rank_b=rank_b[trial_id])
        for trial_id in sorted(rank_a)
        if rank_a[trial_id] != rank_b[trial_id]
    )
    top_a = {item.trial_id for item in ranking_a[:top_k]}
    top_b = {item.trial_id for item in ranking_b[:top_k]}
    return ScenarioComparison(
        ranking_a=tuple(ranking_a),
        ranking_b=tuple(ranking_b),
        changed_rankings=changed,
        top_k=top_k,
        top_matches_only_in_a=tuple(sorted(top_a - top_b)),
        top_matches_only_in_b=tuple(sorted(top_b - top_a)),
        note="historical neighborhood changed.",
    )


def format_similarity_result(result: SimilarityResult) -> str:
    """Human-readable feature-by-feature explanation. Not a clinical recommendation."""
    percent = result.similarity_score * 100.0
    coverage = result.comparison_coverage * 100.0
    lines = [
        f"{result.trial_id}",
        f"{result.trial_title}",
        f"Historical similarity: {percent:.1f}% (resemblance heuristic, not a success probability)",
        (
            f"Comparison coverage: {coverage:.0f}% · "
            f"{result.comparable_feature_count}/{result.total_feature_count} features available"
        ),
        f"Historical outcome: {result.historical_outcome_class} (descriptive only; not a prediction)",
        "WHY THIS MATCH?",
    ]
    for item in result.feature_comparisons:
        mark = STATUS_MARK[item.status]
        lines.append(
            f"  {item.feature_name:<22} {mark:<9} "
            f"protocol={item.protocol_value} | historical={item.historical_value} "
            f"| contribution={item.contribution:.4f}"
        )
        lines.append(f"    {item.explanation}")
    return "\n".join(lines)
