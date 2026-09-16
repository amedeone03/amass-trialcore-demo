"""Map Amass TrialCore records onto HistoricalTrial.

This layer is the only place that may read Amass camelCase JSON.
Callers receive HistoricalTrial objects and never Amass field names.

Normalization is conservative: missing or conflicting values become
``unknown``, ``ambiguous: ...``, or ``None``. Clinical facts are never invented.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from trialtwin.models import HistoricalTrial

UNKNOWN = "unknown"
AMBIGUOUS_PREFIX = "ambiguous: "

# Official TrialCore phase enums → display labels used by TrialTwin.
PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase I",
    "PHASE1": "Phase I",
    "PHASE1/PHASE2": "Phase I/II",
    "PHASE2": "Phase II",
    "PHASE2/PHASE3": "Phase II/III",
    "PHASE3": "Phase III",
    "PHASE4": "Phase IV",
    "NA": "N/A",
}


class NormalizationSkip(Exception):
    """Record cannot be identified and must be dropped."""


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _as_str(item)
        if text is not None:
            items.append(text)
    return items


def _one_or_ambiguous(values: list[str]) -> str:
    unique = list(dict.fromkeys(values))
    if not unique:
        return UNKNOWN
    if len(unique) == 1:
        return unique[0]
    return AMBIGUOUS_PREFIX + " | ".join(unique)


def _parse_iso_date(value: Any) -> date | None:
    text = _as_str(value)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _duration_months(record: dict[str, Any]) -> int | None:
    """Calendar span from startDate to completionDate, if both parse.

    This is not treatment-duration. TrialCore has no dedicated duration field.
    """
    start = _parse_iso_date(record.get("startDate"))
    end = _parse_iso_date(record.get("completionDate"))
    if start is None or end is None:
        return None
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if months < 0:
        return None
    return months


def _sample_size(record: dict[str, Any]) -> int | None:
    value = record.get("enrollment")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return int(value)


def _phase(record: dict[str, Any]) -> str:
    raw = _as_str(record.get("phase"))
    if raw is None:
        return UNKNOWN
    if raw in PHASE_LABELS:
        return PHASE_LABELS[raw]
    return UNKNOWN


def _title(record: dict[str, Any]) -> str:
    for key in ("briefTitle", "officialTitle", "acronym"):
        text = _as_str(record.get(key))
        if text is not None:
            return text
    return UNKNOWN


def _trial_id(record: dict[str, Any]) -> str:
    for key in ("amassId", "nctId", "registryId"):
        text = _as_str(record.get(key))
        if text is not None:
            return text
    raise NormalizationSkip("record has no amassId, nctId, or registryId")


def _disease(record: dict[str, Any]) -> str:
    """Use Alzheimer's disease only when a condition/MeSH term names it.

    No other disease is rewritten. Multiple non-Alzheimer conditions are
    marked ambiguous rather than picking a winner.
    """
    terms = _string_list(record.get("conditions")) + _string_list(
        record.get("conditionMeshTerms")
    )
    alzheimer = [term for term in terms if "alzheimer" in term.lower()]
    if alzheimer:
        return "Alzheimer's disease"
    return _one_or_ambiguous(_string_list(record.get("conditions")))


def _target(record: dict[str, Any]) -> str:
    """Map intervention names when present; otherwise intervention MeSH terms.

    Multiple names are ambiguous. A biomarker mention in free text is ignored.
    """
    names = _string_list(record.get("interventionNames"))
    if names:
        return _one_or_ambiguous(names)
    return _one_or_ambiguous(_string_list(record.get("interventionMeshTerms")))


def _primary_endpoint(record: dict[str, Any]) -> str:
    return _one_or_ambiguous(_string_list(record.get("primaryOutcomeMeasures")))


def _why_stopped(record: dict[str, Any]) -> str:
    text = _as_str(record.get("whyStopped"))
    return text if text is not None else UNKNOWN


def _outcome_class() -> str:
    """TrialCore has no success/failure classification. Always unknown."""
    return "unknown"


def normalize_amass_record(record: Any) -> HistoricalTrial:
    """Convert one TrialCore record dict into a HistoricalTrial.

    Raises NormalizationSkip if the record is not an object or has no id.
    """
    if not isinstance(record, dict):
        raise NormalizationSkip("record is not a JSON object")

    return HistoricalTrial(
        id=_trial_id(record),
        title=_title(record),
        disease=_disease(record),
        phase=_phase(record),
        target=_target(record),
        disease_stage=UNKNOWN,
        biomarker_strategy=None,
        sample_size=_sample_size(record),
        duration_months=_duration_months(record),
        primary_endpoint=_primary_endpoint(record),
        outcome_class=_outcome_class(),  # type: ignore[arg-type]
        why_stopped=_why_stopped(record),
    )


def normalize_amass_records(records: Any) -> tuple[list[HistoricalTrial], list[str]]:
    """Normalize a sequence of raw records. Invalid items are skipped."""
    if not isinstance(records, list):
        raise ValueError("Amass 'data' must be a JSON array of trial objects.")

    trials: list[HistoricalTrial] = []
    skipped: list[str] = []
    for index, record in enumerate(records):
        try:
            trials.append(normalize_amass_record(record))
        except NormalizationSkip as exc:
            skipped.append(f"index {index}: {exc}")
    return trials, skipped
