"""Pure display helpers for TrialTwin. No Streamlit dependency."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from trialtwin.engine import LOW_COVERAGE_THRESHOLD, SimilarityResult, is_low_coverage
from trialtwin.models import HistoricalTrial, Protocol
from trialtwin.normalize import registry_display_name

LIVE_SOURCE = "LIVE AMASS"
DEMO_SOURCE = "LOCAL DEMO DATA"

# Bump APP_STATE_VERSION after session-owned Protocol / widget schema changes.
# Bump DATA_CACHE_VERSION after HistoricalTrial field migrations so Streamlit
# cache_data cannot serve pre-migration objects (the target→intervention crash).
APP_STATE_VERSION = 2
DATA_CACHE_VERSION = "historical-trials-v2-intervention"
STATE_VERSION_KEY = "_trialtwin_state_version"

OWNED_SESSION_KEYS = frozenset(
    {
        "scenario_a",
        "matches_requested",
        "demo_pending",
        "apply_demo",
        "capture_scenario_a",
        "protocol_target",
        "protocol_intervention",
        "protocol_stage",
        "protocol_biomarker",
        "protocol_duration",
        "protocol_endpoint",
        "protocol_n",
        "current_mode",
    }
)

LOCKED_DISEASE = "Alzheimer's disease"
LOCKED_PHASE = "Phase III"

DEMO_PROTOCOL_A = Protocol(
    disease=LOCKED_DISEASE,
    phase=LOCKED_PHASE,
    intervention="amyloid-beta",
    disease_stage="Early",
    biomarker_strategy=True,
    sample_size=1200,
    duration_months=18,
    primary_endpoint="CDR-SB",
)

DEMO_PROTOCOL_B = Protocol(
    disease=LOCKED_DISEASE,
    phase=LOCKED_PHASE,
    intervention="amyloid-beta",
    disease_stage="Early",
    biomarker_strategy=False,
    sample_size=1200,
    duration_months=18,
    primary_endpoint="CDR-SB",
)

FEATURE_LABEL = {
    "intervention": "Intervention",
    "disease_stage": "Disease stage",
    "biomarker_strategy": "Biomarker",
    "primary_endpoint": "Endpoint",
    "duration_months": "Duration",
    "sample_size": "Sample size",
}

PARAM_TITLES = {
    "disease_stage": "Disease stage",
    "biomarker_strategy": "Biomarker confirmation",
    "duration_months": "Duration",
    "primary_endpoint": "Primary endpoint",
    "sample_size": "Sample size",
    "intervention": "Intervention",
}


def migrate_owned_session_state(
    state: MutableMapping[str, Any],
    current_version: int = APP_STATE_VERSION,
) -> bool:
    """Clear TrialTwin-owned keys when the schema version changes.

    Does not delete Streamlit-internal keys. Returns True if a migration ran.
    """
    if state.get(STATE_VERSION_KEY) == current_version:
        return False
    for key in list(state.keys()):
        if key in OWNED_SESSION_KEYS:
            del state[key]
    state[STATE_VERSION_KEY] = current_version
    return True


def source_is_live(source: str) -> bool:
    return source == LIVE_SOURCE


def should_show_demo_outcomes(source: str) -> bool:
    """Live TrialCore has no validated outcome class; hide the profile."""
    return not source_is_live(source)


def source_badge(source: str) -> tuple[str, str]:
    if source_is_live(source):
        return "AMASS TRIALCORE", "blue"
    return "LOCAL SYNTHETIC DEMO", "gray"


def evidence_source_label(source: str) -> str:
    if source_is_live(source):
        return "historical TrialCore records"
    return "synthetic demonstration records"


def candidate_set_caption(n: int) -> str:
    return f"Closest matches among {n} retrieved historical candidates"


def ranking_against_caption(n: int) -> str:
    return f"Ranking against {n} retrieved Phase III Alzheimer trials"


def coverage_line(result: SimilarityResult) -> str:
    percent = result.comparison_coverage * 100.0
    return (
        f"{percent:.0f}% · "
        f"{result.comparable_feature_count}/{result.total_feature_count} features available"
    )


def low_coverage_warning(result: SimilarityResult) -> str | None:
    if is_low_coverage(result.comparison_coverage, LOW_COVERAGE_THRESHOLD):
        return "Similarity is based on limited comparable data."
    return None


def format_why_value(feature_name: str, raw: str) -> str:
    if raw in {"unknown", "true", "false"} or raw.startswith("ambiguous:"):
        if raw == "true":
            return "Required"
        if raw == "false":
            return "Not required"
        return "Unknown in source data"
    if feature_name == "duration_months" and raw.isdigit():
        return f"{raw} months"
    return raw


def intervention_choices(trials: list[HistoricalTrial]) -> list[str]:
    options: list[str] = []
    seen: set[str] = set()
    for trial in trials:
        value = trial.intervention
        if not value or value.casefold() == "unknown" or value.startswith("ambiguous:"):
            continue
        if value not in seen:
            seen.add(value)
            options.append(value)
    return options


def provenance_rows(trial: HistoricalTrial) -> list[tuple[str, str]]:
    registry = registry_display_name(trial.source_registry)
    rows = [
        ("Registry", registry if trial.source_registry else "Unknown in source data"),
        ("Registry ID", trial.registry_id or "Unknown in source data"),
        ("Amass ID", trial.amass_id or "Unknown in source data"),
    ]
    if trial.source_url:
        rows.append(("Source URL", trial.source_url))
    else:
        rows.append(("Source URL", "Source URL unavailable"))
    return rows
