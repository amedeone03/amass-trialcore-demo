"""Offline TrialTwin pipeline demo. Local JSON only. No Amass, UI, or LLM."""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trialtwin.engine import (
    FEATURE_ORDER,
    compare_protocol_scenarios,
    rank_historical_trials,
    summarize_historical_neighborhood,
)
from trialtwin.models import HistoricalTrial, Protocol, load_historical_trials

STATUS_GLYPH = {
    "match": "✓",
    "partial": "~",
    "mismatch": "✗",
    "unknown": "?",
}

FEATURE_LABEL = {
    "disease": "Disease",
    "phase": "Phase",
    "disease_stage": "Stage",
    "biomarker_strategy": "Biomarker",
    "primary_endpoint": "Endpoint",
    "duration_months": "Duration",
    "sample_size": "Sample size",
    "target": "Target",
}

# Value present in data/alzheimer_trials.json. Do not invent a biological target.
DEMO_TARGET = "amyloid-beta"
TOP_K = 5


def fail(message: str) -> None:
    raise SystemExit(f"DEMO VALIDATION FAILED: {message}")


def percent(score: float) -> float:
    return score * 100.0


def validate_trials(trials: list[HistoricalTrial]) -> None:
    if not trials:
        fail("Local dataset loaded zero trials.")
    for trial in trials:
        if not isinstance(trial, HistoricalTrial):
            fail("Loaded object is not a HistoricalTrial.")
        if not trial.id.strip():
            fail("HistoricalTrial is missing an id.")


def validate_pipeline(protocol: Protocol, trials: list[HistoricalTrial], ranked: list) -> None:
    replay = rank_historical_trials(protocol, trials)
    first = [(item.trial_id, item.similarity_score) for item in ranked]
    second = [(item.trial_id, item.similarity_score) for item in replay]
    if first != second:
        fail("Ranking is not deterministic across identical inputs.")

    shuffled = list(trials)
    random.Random(0).shuffle(shuffled)
    shuffled_rank = [
        (item.trial_id, item.similarity_score)
        for item in rank_historical_trials(protocol, shuffled)
    ]
    if first != shuffled_rank:
        fail("Ranking is not deterministic after shuffling input order.")

    if len(ranked) != len(trials):
        fail("Similarity ranking length does not match the trial list.")
    previous_key = None
    for result in ranked:
        score = result.similarity_score
        if not isinstance(score, (int, float)) or not math.isfinite(score):
            fail(f"Invalid similarity score for {result.trial_id}: {score!r}")
        shown = percent(float(score))
        if shown < 0 or shown > 100:
            fail(f"Similarity for {result.trial_id} is outside 0-100: {shown}")
        names = [item.feature_name for item in result.feature_comparisons]
        if names != list(FEATURE_ORDER):
            fail(f"Feature comparisons incomplete for {result.trial_id}.")
        for item in result.feature_comparisons:
            if item.status not in STATUS_GLYPH:
                fail(f"Unknown feature status {item.status!r} on {result.trial_id}.")
            if not math.isfinite(item.contribution):
                fail(f"Invalid contribution on {result.trial_id} / {item.feature_name}.")
        key = (-float(score), result.trial_id)
        if previous_key is not None and key < previous_key:
            fail("Ranking is not sorted by similarity descending, then trial_id.")
        previous_key = key


def format_why(result) -> list[str]:
    lines = []
    for item in result.feature_comparisons:
        glyph = STATUS_GLYPH[item.status]
        label = FEATURE_LABEL[item.feature_name]
        lines.append(
            f"   {glyph} {label}: protocol {item.protocol_value} | "
            f"historical {item.historical_value}"
        )
    return lines


def print_match_list(ranked: list, limit: int) -> None:
    for index, result in enumerate(ranked[:limit], start=1):
        print(f"{index}. [{result.trial_id}] {result.trial_title}")
        print(f"   Similarity: {percent(result.similarity_score):.1f}%")
        print("   Why this match:")
        for line in format_why(result):
            print(line)
        print(
            f"   Historical outcome: {result.historical_outcome_class} "
            "(descriptive only; not a prediction)"
        )
        print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        trials = load_historical_trials()
    except Exception as exc:
        fail(f"JSON cannot be loaded: {exc}")

    validate_trials(trials)
    targets = {trial.target for trial in trials}
    if DEMO_TARGET not in targets:
        fail(f"Demo target {DEMO_TARGET!r} is not in the local dataset: {sorted(targets)}")

    try:
        protocol = Protocol(
            disease="Alzheimer's disease",
            phase="Phase III",
            target=DEMO_TARGET,
            disease_stage="Early",
            biomarker_strategy=True,
            sample_size=1200,
            duration_months=18,
            primary_endpoint="CDR-SB",
        )
        protocol_what_if = Protocol(
            disease=protocol.disease,
            phase=protocol.phase,
            target=protocol.target,
            disease_stage=protocol.disease_stage,
            biomarker_strategy=False,
            sample_size=protocol.sample_size,
            duration_months=protocol.duration_months,
            primary_endpoint=protocol.primary_endpoint,
        )
    except Exception as exc:
        fail(f"Protocol models cannot be created: {exc}")

    ranked = rank_historical_trials(protocol, trials)
    validate_pipeline(protocol, trials, ranked)
    summary = summarize_historical_neighborhood(ranked, top_k=TOP_K)

    print("========================================")
    print("TRIALTWIN — HISTORICAL SANDBOX")
    print("========================================")
    print()
    print("PROPOSED PROTOCOL")
    print()
    print("Disease:")
    print(protocol.disease)
    print("Phase:")
    print(protocol.phase)
    print("Stage:")
    print("Early")
    print("Biomarker:")
    print("Required")
    print("Duration:")
    print(f"{protocol.duration_months} months")
    print("Endpoint:")
    print(protocol.primary_endpoint)
    print("Sample size:")
    print(protocol.sample_size)
    print("Target:")
    print(protocol.target)
    print()
    print("----------------------------------------")
    print("CLOSEST HISTORICAL DESIGNS")
    print("----------------------------------------")
    print()
    print_match_list(ranked, TOP_K)
    print("----------------------------------------")
    print("HISTORICAL OUTCOME PROFILE")
    print("----------------------------------------")
    print()
    print(f"Top {summary.top_k} historical neighbors:")
    print()
    print(f"Favorable: {summary.favorable}")
    print(f"Unfavorable: {summary.unfavorable}")
    print(f"Unclear: {summary.unclear}")
    if summary.unknown:
        print(f"Unknown: {summary.unknown}")
    print()
    print("This is descriptive historical evidence of nearby designs.")
    print("It is not a predicted probability of success or failure.")
    print()

    comparison = compare_protocol_scenarios(
        protocol, protocol_what_if, trials, top_k=TOP_K
    )
    validate_pipeline(protocol_what_if, trials, list(comparison.ranking_b))

    print("========================================")
    print("WHAT-IF SCENARIO")
    print("========================================")
    print()
    print("Changed parameter:")
    print("Biomarker strategy")
    print()
    print("Before:")
    print("Required")
    print()
    print("After:")
    print("Not required")
    print()
    print("----------------------------------------")
    print()
    print("TOP HISTORICAL MATCHES — BEFORE")
    print()
    print_match_list(list(comparison.ranking_a), TOP_K)
    print("TOP HISTORICAL MATCHES — AFTER")
    print()
    print_match_list(list(comparison.ranking_b), TOP_K)
    print("----------------------------------------")
    print()
    print("HISTORICAL NEIGHBORHOOD CHANGE")
    print()
    print("The historical neighborhood changed.")
    print()
    left = comparison.top_matches_only_in_a
    entered = comparison.top_matches_only_in_b
    if left:
        print("Left the top neighborhood:")
        for trial_id in left:
            print(f"  {trial_id}")
    else:
        print("No trials left the top neighborhood.")
    if entered:
        print("Entered the top neighborhood:")
        for trial_id in entered:
            print(f"  {trial_id}")
    else:
        print("No new trials entered the top neighborhood.")
    if comparison.changed_rankings:
        print()
        print("Rank position changes:")
        for change in comparison.changed_rankings:
            print(f"  {change.trial_id}: {change.rank_a} → {change.rank_b}")


if __name__ == "__main__":
    main()
