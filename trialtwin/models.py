"""Domain models for ProtocolNeighbor protocol and historical-trial comparison."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

OutcomeClass = Literal["favorable", "unfavorable", "unclear", "unknown"]

REQUIRED_TRIAL_FIELDS = (
    "id",
    "title",
    "disease",
    "phase",
    "intervention",
    "disease_stage",
    "biomarker_strategy",
    "sample_size",
    "duration_months",
    "primary_endpoint",
    "outcome_class",
    "why_stopped",
)

OPTIONAL_TRIAL_FIELDS = (
    "primary_endpoint_raw",
    "study_span_months",
    "amass_id",
    "registry_id",
    "source_registry",
    "source_url",
)

VALID_OUTCOME_CLASSES = frozenset({"favorable", "unfavorable", "unclear", "unknown"})

DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data" / "alzheimer_trials.json"


@dataclass
class Protocol:
    """Hypothetical protocol used only for historical design comparison.

    ``intervention`` is the named product/compound/tracer, not a biological
    target. ``duration_months`` is the intended protocol/follow-up duration
    chosen by the user.
    """

    disease: str = "Alzheimer's disease"
    phase: str = "Phase III"
    intervention: str = ""
    disease_stage: str = ""
    biomarker_strategy: bool = False
    sample_size: int = 0
    duration_months: int = 0
    primary_endpoint: str = ""


@dataclass
class HistoricalTrial:
    """Normalized historical trial used as a comparison neighbor.

    ``outcome_class`` is a descriptive label only. It does not mean the
    protocol design caused success or failure.

    ``duration_months`` is protocol/follow-up duration when a semantically
    equivalent value exists (local mock data). Live TrialCore records leave
    this ``None``. ``study_span_months`` is calendar start→completion only
    and is never scored.

    ``intervention`` is intervention name/MeSH, not a mapped biological target.
    """

    id: str
    title: str
    disease: str
    phase: str
    intervention: str
    disease_stage: str
    biomarker_strategy: bool | None
    sample_size: int | None
    duration_months: int | None
    primary_endpoint: str
    outcome_class: OutcomeClass
    why_stopped: str
    primary_endpoint_raw: str = ""
    study_span_months: int | None = None
    amass_id: str | None = None
    registry_id: str | None = None
    source_registry: str | None = None
    source_url: str | None = None


def _require(record: dict[str, Any], field: str, index: int) -> Any:
    if field not in record:
        raise ValueError(f"Trial at index {index} is missing required field '{field}'.")
    return record[field]


def _require_str(record: dict[str, Any], field: str, index: int) -> str:
    value = _require(record, field, index)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Trial at index {index} field '{field}' must be a non-empty string."
        )
    return value


def _require_bool(record: dict[str, Any], field: str, index: int) -> bool:
    value = _require(record, field, index)
    if not isinstance(value, bool):
        raise ValueError(f"Trial at index {index} field '{field}' must be a boolean.")
    return value


def _require_int(record: dict[str, Any], field: str, index: int) -> int:
    value = _require(record, field, index)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"Trial at index {index} field '{field}' must be a non-negative integer."
        )
    return value


def _optional_str(record: dict[str, Any], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _optional_int(record: dict[str, Any], field: str, index: int) -> int | None:
    if field not in record or record[field] is None:
        return None
    return _require_int(record, field, index)


def historical_trial_from_dict(record: dict[str, Any], index: int = 0) -> HistoricalTrial:
    """Validate a local JSON record and construct a HistoricalTrial."""
    if not isinstance(record, dict):
        raise ValueError(f"Trial at index {index} must be an object.")

    allowed = set(REQUIRED_TRIAL_FIELDS) | set(OPTIONAL_TRIAL_FIELDS)
    extra = set(record) - allowed
    if extra:
        raise ValueError(
            f"Trial at index {index} has unexpected fields: {sorted(extra)}."
        )

    outcome_class = _require_str(record, "outcome_class", index)
    if outcome_class not in VALID_OUTCOME_CLASSES:
        raise ValueError(
            f"Trial at index {index} field 'outcome_class' must be one of "
            f"{sorted(VALID_OUTCOME_CLASSES)}; got {outcome_class!r}."
        )

    endpoint = _require_str(record, "primary_endpoint", index)
    raw = _optional_str(record, "primary_endpoint_raw") or endpoint

    return HistoricalTrial(
        id=_require_str(record, "id", index),
        title=_require_str(record, "title", index),
        disease=_require_str(record, "disease", index),
        phase=_require_str(record, "phase", index),
        intervention=_require_str(record, "intervention", index),
        disease_stage=_require_str(record, "disease_stage", index),
        biomarker_strategy=_require_bool(record, "biomarker_strategy", index),
        sample_size=_require_int(record, "sample_size", index),
        duration_months=_require_int(record, "duration_months", index),
        primary_endpoint=endpoint,
        outcome_class=outcome_class,  # type: ignore[arg-type]
        why_stopped=_require_str(record, "why_stopped", index),
        primary_endpoint_raw=raw,
        study_span_months=_optional_int(record, "study_span_months", index),
        amass_id=_optional_str(record, "amass_id"),
        registry_id=_optional_str(record, "registry_id"),
        source_registry=_optional_str(record, "source_registry"),
        source_url=_optional_str(record, "source_url"),
    )


def load_historical_trials(path: Path | str | None = None) -> list[HistoricalTrial]:
    """Load HistoricalTrial records from a local JSON array.

    Raises ValueError if the file is not a JSON array of valid trial objects.
    """
    data_path = Path(path) if path is not None else DEFAULT_DATA_PATH
    try:
        raw = data_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read trial dataset at {data_path}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Trial dataset at {data_path} is not valid JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise ValueError(f"Trial dataset at {data_path} must be a JSON array.")

    return [historical_trial_from_dict(record, index) for index, record in enumerate(payload)]
