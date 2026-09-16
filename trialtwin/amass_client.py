"""Amass TrialCore HTTP adapter and historical-trial data access.

TrialCore search has no documented offset/cursor pagination. Each request
returns at most 300 records via ``limit`` (documented range 1–300).
TrialTwin therefore retrieves a single capped page and ranks inside
that retrieved candidate set — not the full TrialCore corpus.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal

import requests
from dotenv import load_dotenv

from trialtwin.engine import matches_candidate_pool
from trialtwin.models import DEFAULT_DATA_PATH, HistoricalTrial, load_historical_trials
from trialtwin.normalize import normalize_amass_records

TRIALCORE_SEARCH_URL = "https://api.amass.tech/api/v1/cores/trialcore/records"
DEFAULT_TIMEOUT_SECONDS = 30
# Documented TrialCore search default is 20; documented maximum is 300.
# Spec default: 100 when that value is within documented support.
DEFAULT_LIMIT = 100
MAX_LIMIT = 300
MIN_LIMIT = 1
ALZHEIMER_QUERY = "Alzheimer's disease"
ALZHEIMER_PHASE = "PHASE3"

SourceLabel = Literal["LIVE AMASS", "LOCAL DEMO DATA"]


class AmassError(Exception):
    """Developer-facing Amass failure. Messages never include API keys."""


class AmassConfigError(AmassError):
    """Missing or invalid local configuration."""


class AmassTimeoutError(AmassError):
    """Request exceeded the configured timeout."""


class AmassHttpError(AmassError):
    """Non-success HTTP status from TrialCore."""


class AmassResponseError(AmassError):
    """Response body was not the expected TrialCore JSON envelope."""


def _load_env_files() -> None:
    """Load `.env` / `.ENV` from the repo root and the current directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    for directory in (repo_root, os.getcwd()):
        for name in (".env", ".ENV"):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                load_dotenv(path, override=False)


def _redact(message: str, secret: str | None) -> str:
    if secret and secret in message:
        return message.replace(secret, "[REDACTED]")
    return message


def get_amass_api_key() -> str:
    """Return AMASS_API_KEY from the environment after loading local env files."""
    _load_env_files()
    key = os.getenv("AMASS_API_KEY", "").strip()
    if not key:
        raise AmassConfigError(
            "AMASS_API_KEY is missing. Set it in the environment or a local "
            ".env file (see .env.example). Do not hardcode the key."
        )
    return key


def resolve_candidate_limit(raw: str | None = None) -> int:
    """Clamp a configured retrieval cap to the documented TrialCore range.

    Documented variable: ``TRIALTWIN_CANDIDATE_LIMIT``.
    ``PROTOCOL_NEIGHBOR_CANDIDATE_LIMIT`` is a deprecated alias.
    """
    if raw is None:
        _load_env_files()
        raw = os.getenv("TRIALTWIN_CANDIDATE_LIMIT") or os.getenv(
            "PROTOCOL_NEIGHBOR_CANDIDATE_LIMIT"  # deprecated alias
        )
    if raw is None or not str(raw).strip():
        return DEFAULT_LIMIT
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise AmassConfigError(
            "TRIALTWIN_CANDIDATE_LIMIT must be an integer."
        ) from exc
    if value < MIN_LIMIT or value > MAX_LIMIT:
        raise AmassConfigError(
            f"Candidate limit must be between {MIN_LIMIT} and {MAX_LIMIT} "
            f"(TrialCore documented search range)."
        )
    return value


@dataclass(frozen=True)
class HistoricalTrialSet:
    """Normalized trials plus provenance for a later UI source banner."""

    trials: list[HistoricalTrial]
    source: SourceLabel
    note: str = ""


class AmassClient:
    """Synchronous TrialCore HTTP client. Returns raw record dicts only."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = TRIALCORE_SEARCH_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        resolved = api_key if api_key is not None else get_amass_api_key()
        if not resolved.strip():
            raise AmassConfigError(
                "AMASS_API_KEY is missing. Set it in the environment or a local "
                ".env file (see .env.example). Do not hardcode the key."
            )
        self._api_key = resolved.strip()
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    def search_records(
        self,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        extra_params: list[tuple[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """GET /v1/cores/trialcore/records and return the `data` array.

        Pagination is not implemented because TrialCore search does not
        document offset or cursor parameters.
        """
        resolved_limit = resolve_candidate_limit(str(limit))
        params: list[tuple[str, str]] = [
            ("query", query),
            ("limit", str(resolved_limit)),
        ]
        if extra_params:
            params.extend(extra_params)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = self._session.get(
                self._base_url,
                params=params,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as exc:
            raise AmassTimeoutError(
                f"TrialCore request timed out after {self._timeout_seconds}s."
            ) from exc
        except requests.RequestException as exc:
            raise AmassHttpError(
                _redact(f"TrialCore request failed: {exc}", self._api_key)
            ) from exc

        if response.status_code == 401:
            raise AmassHttpError(
                "TrialCore returned HTTP 401 (UNAUTHORIZED). Check AMASS_API_KEY."
            )
        if response.status_code == 403:
            raise AmassHttpError(
                "TrialCore returned HTTP 403 (FORBIDDEN). This key cannot access TrialCore."
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            extra = f" Retry-After={retry_after}." if retry_after else ""
            raise AmassHttpError(
                "TrialCore returned HTTP 429 (TOO_MANY_REQUESTS)." + extra
            )
        if response.status_code >= 400:
            raise AmassHttpError(
                f"TrialCore returned HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise AmassResponseError("TrialCore response was not valid JSON.") from exc
        except ValueError as exc:
            raise AmassResponseError("TrialCore response was not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise AmassResponseError("TrialCore JSON envelope must be an object.")
        data = payload.get("data")
        if not isinstance(data, list):
            raise AmassResponseError(
                "TrialCore search response must contain a JSON array at 'data'."
            )
        return data


def fetch_alzheimer_phase3_trials(
    *,
    client: AmassClient | None = None,
    limit: int | None = None,
) -> list[HistoricalTrial]:
    """Fetch Alzheimer's Phase III trials from TrialCore and normalize them."""
    amass = client or AmassClient()
    resolved = resolve_candidate_limit(str(limit) if limit is not None else None)
    raw = amass.search_records(
        ALZHEIMER_QUERY,
        limit=resolved,
        extra_params=[("phase", ALZHEIMER_PHASE)],
    )
    trials, skipped = normalize_amass_records(raw)
    if skipped and not trials:
        raise AmassResponseError(
            "TrialCore returned records but none could be normalized: "
            + "; ".join(skipped)
        )
    return [trial for trial in trials if matches_candidate_pool(trial)]


def load_local_trials(path: str | None = None) -> list[HistoricalTrial]:
    """Load the bundled demo dataset. Never presented as live Amass data."""
    return load_historical_trials(path or DEFAULT_DATA_PATH)


def get_historical_trials(
    use_live: bool = True,
    *,
    client: AmassClient | None = None,
    limit: int | None = None,
) -> HistoricalTrialSet:
    """Return historical trials from Amass, or the local demo file on AmassError.

    Empty live results are not replaced with demo rows. Fallback is only used
    for expected Amass access failures. Programming errors propagate.
    """
    if not use_live:
        return HistoricalTrialSet(
            trials=load_local_trials(),
            source="LOCAL DEMO DATA",
            note="Live Amass was not requested.",
        )

    try:
        trials = fetch_alzheimer_phase3_trials(client=client, limit=limit)
    except AmassError as exc:
        return HistoricalTrialSet(
            trials=load_local_trials(),
            source="LOCAL DEMO DATA",
            note=f"Amass unavailable; using local demo data. Reason: {exc}",
        )

    note = ""
    if not trials:
        note = (
            "Amass returned no Alzheimer's Phase III records. "
            "This is a live empty result, not demo data."
        )
    return HistoricalTrialSet(trials=trials, source="LIVE AMASS", note=note)
