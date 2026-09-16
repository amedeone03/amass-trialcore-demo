"""Deterministic primary-endpoint canonicalization.

Rule-based only. No embeddings, fuzzy matching, or LLM. Unrecognized
strings become ``other: <original>``. Multiple distinct families stay
``ambiguous:``.
"""

from __future__ import annotations

UNKNOWN = "unknown"
AMBIGUOUS_PREFIX = "ambiguous: "


def _compact(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


def canonicalize_endpoint(value: str | None) -> str:
    """Map one outcome-measure string onto a small Alzheimer endpoint family."""
    if value is None:
        return UNKNOWN
    text = value.strip()
    if not text:
        return UNKNOWN
    lowered = text.casefold()
    if lowered == UNKNOWN or lowered.startswith(AMBIGUOUS_PREFIX.casefold()):
        return UNKNOWN if lowered == UNKNOWN else text

    compact = _compact(text)

    # CDR-SB only when Sum of Boxes (or CDRSB) is present. Plain CDR / CDR global
    # is a different instrument and must not be rewritten.
    if "cdrsb" in compact or "clinicaldementiaratingsumofboxes" in compact:
        return "CDR-SB"

    if "adas" in compact and "cog" in compact:
        return "ADAS-Cog"
    if "alzheimersdiseaseassessmentscalecognitive" in compact:
        return "ADAS-Cog"

    if "mmse" in compact or "minimentalstate" in compact:
        return "MMSE"

    if "adcsadl" in compact or "alzheimersdiseasecooperativestudyadl" in compact:
        return "ADCS-ADL"
    if "adcs" in compact and "adl" in compact:
        return "ADCS-ADL"

    return f"other: {text}"


def canonicalize_endpoint_list(values: list[str]) -> tuple[str, str]:
    """Return (canonical_or_ambiguous, raw_joined).

    Multiple distinct canonical families are marked ambiguous rather than
    picking a winner.
    """
    cleaned = [item.strip() for item in values if item and item.strip()]
    raw = " | ".join(cleaned) if cleaned else UNKNOWN
    if not cleaned:
        return UNKNOWN, UNKNOWN
    canonical = list(dict.fromkeys(canonicalize_endpoint(item) for item in cleaned))
    if len(canonical) == 1:
        return canonical[0], raw
    return AMBIGUOUS_PREFIX + " | ".join(canonical), raw
