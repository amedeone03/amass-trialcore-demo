"""Pure visualization data for TrialTwin charts. No Streamlit, no ranking math."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from trialtwin.engine import FEATURE_ORDER, SimilarityResult
from trialtwin.models import HistoricalTrial
from trialtwin.presentation import FEATURE_LABEL

Movement = Literal["moved_in", "moved_out", "stayed"]
FingerprintStatus = Literal["Exact", "Similar", "Different", "Unknown"]

STATUS_TO_FINGERPRINT: dict[str, FingerprintStatus] = {
    "match": "Exact",
    "partial": "Similar",
    "mismatch": "Different",
    "unknown": "Unknown",
}

# Visual fill only — not a clinical or engine score.
STATUS_FILL: dict[str, int] = {
    "match": 10,
    "partial": 7,
    "mismatch": 3,
    "unknown": 0,
}

SHIFT_LINE_COLORS = (
    "#A78BFA",
    "#22D3EE",
    "#C4B5FD",
    "#67E8F9",
    "#818CF8",
    "#94A3B8",
)


@dataclass(frozen=True)
class RankShiftRow:
    trial_id: str
    title: str
    short_title: str
    rank_before: int | None
    rank_after: int | None
    similarity_before: float | None
    similarity_after: float | None
    coverage_before: float | None
    coverage_after: float | None
    movement: Movement
    color: str


@dataclass(frozen=True)
class NeighborhoodShift:
    top_k: int
    chart_k: int
    changed_count: int
    top_match_changed: bool
    moved_in_ids: tuple[str, ...]
    moved_out_ids: tuple[str, ...]
    rows: tuple[RankShiftRow, ...]
    avg_similarity_before: float
    avg_similarity_after: float
    avg_coverage_before: float
    avg_coverage_after: float
    can_draw: bool
    empty_reason: str


@dataclass(frozen=True)
class FingerprintRow:
    feature_name: str
    label: str
    status: FingerprintStatus
    fill: int
    bar: str


@dataclass(frozen=True)
class CoveragePoint:
    trial_id: str
    title: str
    similarity_pct: float
    coverage_pct: float
    intervention: str
    is_top: bool


def shorten_title(title: str, limit: int = 36) -> str:
    text = (title or "").strip()
    if text.upper().startswith("[DEMO/MOCK]"):
        text = text[11:].strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 1)] + "..."


def _rank_map(ranking: list[SimilarityResult] | tuple[SimilarityResult, ...]) -> dict[str, int]:
    return {item.trial_id: index + 1 for index, item in enumerate(ranking)}


def _result_map(
    ranking: list[SimilarityResult] | tuple[SimilarityResult, ...],
) -> dict[str, SimilarityResult]:
    return {item.trial_id: item for item in ranking}


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def calculate_neighborhood_shift(
    ranking_a: list[SimilarityResult] | tuple[SimilarityResult, ...],
    ranking_b: list[SimilarityResult] | tuple[SimilarityResult, ...],
    *,
    top_k: int = 3,
    chart_k: int = 5,
) -> NeighborhoodShift:
    """Describe rank movement. Does not recompute similarity."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    if not ranking_a or not ranking_b:
        return NeighborhoodShift(
            top_k=top_k,
            chart_k=chart_k,
            changed_count=0,
            top_match_changed=False,
            moved_in_ids=(),
            moved_out_ids=(),
            rows=(),
            avg_similarity_before=0.0,
            avg_similarity_after=0.0,
            avg_coverage_before=0.0,
            avg_coverage_after=0.0,
            can_draw=False,
            empty_reason="No rankings are available to compare.",
        )

    unique_ids = {item.trial_id for item in ranking_a} | {item.trial_id for item in ranking_b}
    if len(unique_ids) < 2:
        return NeighborhoodShift(
            top_k=top_k,
            chart_k=chart_k,
            changed_count=0,
            top_match_changed=False,
            moved_in_ids=(),
            moved_out_ids=(),
            rows=(),
            avg_similarity_before=_average([item.similarity_score for item in ranking_a[:top_k]]),
            avg_similarity_after=_average([item.similarity_score for item in ranking_b[:top_k]]),
            avg_coverage_before=_average([item.comparison_coverage for item in ranking_a[:top_k]]),
            avg_coverage_after=_average([item.comparison_coverage for item in ranking_b[:top_k]]),
            can_draw=False,
            empty_reason="A neighborhood-shift graph needs at least two historical trials.",
        )

    set_a = {item.trial_id for item in ranking_a[:top_k]}
    set_b = {item.trial_id for item in ranking_b[:top_k]}
    moved_out = tuple(sorted(set_a - set_b))
    moved_in = tuple(sorted(set_b - set_a))
    changed_count = len(set_a - set_b)
    top_match_changed = ranking_a[0].trial_id != ranking_b[0].trial_id

    window = max(chart_k, top_k)
    ordered: list[str] = []
    for item in list(ranking_b[:window]) + list(ranking_a[:window]):
        if item.trial_id not in ordered:
            ordered.append(item.trial_id)

    ranks_a = _rank_map(ranking_a)
    ranks_b = _rank_map(ranking_b)
    by_a = _result_map(ranking_a)
    by_b = _result_map(ranking_b)

    rows: list[RankShiftRow] = []
    for index, trial_id in enumerate(ordered):
        result = by_b.get(trial_id) or by_a[trial_id]
        if trial_id in set_b - set_a:
            movement: Movement = "moved_in"
        elif trial_id in set_a - set_b:
            movement = "moved_out"
        else:
            movement = "stayed"
        rows.append(
            RankShiftRow(
                trial_id=trial_id,
                title=result.trial_title,
                short_title=shorten_title(result.trial_title),
                rank_before=ranks_a.get(trial_id),
                rank_after=ranks_b.get(trial_id),
                similarity_before=by_a[trial_id].similarity_score if trial_id in by_a else None,
                similarity_after=by_b[trial_id].similarity_score if trial_id in by_b else None,
                coverage_before=by_a[trial_id].comparison_coverage if trial_id in by_a else None,
                coverage_after=by_b[trial_id].comparison_coverage if trial_id in by_b else None,
                movement=movement,
                color=SHIFT_LINE_COLORS[index % len(SHIFT_LINE_COLORS)],
            )
        )

    return NeighborhoodShift(
        top_k=top_k,
        chart_k=window,
        changed_count=changed_count,
        top_match_changed=top_match_changed,
        moved_in_ids=moved_in,
        moved_out_ids=moved_out,
        rows=tuple(rows),
        avg_similarity_before=_average([item.similarity_score for item in ranking_a[:top_k]]),
        avg_similarity_after=_average([item.similarity_score for item in ranking_b[:top_k]]),
        avg_coverage_before=_average([item.comparison_coverage for item in ranking_a[:top_k]]),
        avg_coverage_after=_average([item.comparison_coverage for item in ranking_b[:top_k]]),
        can_draw=True,
        empty_reason="",
    )


def build_match_fingerprint(result: SimilarityResult) -> tuple[FingerprintRow, ...]:
    by_name = {item.feature_name: item for item in result.feature_comparisons}
    rows: list[FingerprintRow] = []
    for name in FEATURE_ORDER:
        item = by_name.get(name)
        status_key = item.status if item is not None else "unknown"
        fill = STATUS_FILL.get(status_key, 0)
        rows.append(
            FingerprintRow(
                feature_name=name,
                label=FEATURE_LABEL.get(name, name),
                status=STATUS_TO_FINGERPRINT.get(status_key, "Unknown"),
                fill=fill,
                bar=("█" * fill) + ("░" * (10 - fill)),
            )
        )
    return tuple(rows)


def build_similarity_coverage_points(
    ranking: list[SimilarityResult] | tuple[SimilarityResult, ...],
    trials: list[HistoricalTrial] | tuple[HistoricalTrial, ...],
    *,
    top_k: int = 3,
) -> tuple[CoveragePoint, ...]:
    trial_by_id = {trial.id: trial for trial in trials}
    top_ids = {item.trial_id for item in ranking[:top_k]}
    points: list[CoveragePoint] = []
    for item in ranking:
        trial = trial_by_id.get(item.trial_id)
        intervention = trial.intervention if trial is not None else ""
        points.append(
            CoveragePoint(
                trial_id=item.trial_id,
                title=item.trial_title,
                similarity_pct=item.similarity_score * 100.0,
                coverage_pct=item.comparison_coverage * 100.0,
                intervention=intervention,
                is_top=item.trial_id in top_ids,
            )
        )
    return tuple(points)


def neighborhood_change_caption(shift: NeighborhoodShift) -> str:
    return (
        f"{shift.changed_count} of {shift.top_k} "
        f"top historical neighbors changed"
    )
