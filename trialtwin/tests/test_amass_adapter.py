"""Mocked tests for Amass adapter, normalizer, and local fallback."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from trialtwin.amass_client import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AmassClient,
    AmassConfigError,
    AmassHttpError,
    AmassResponseError,
    AmassTimeoutError,
    fetch_alzheimer_phase3_trials,
    get_historical_trials,
    load_local_trials,
    resolve_candidate_limit,
)
from trialtwin.normalize import UNKNOWN, normalize_amass_record, normalize_amass_records


def _complete_record(**overrides: object) -> dict:
    record = {
        "amassId": "AMTC_demo_1",
        "nctId": "NCT00000001",
        "registryId": "NCT00000001",
        "sourceRegistry": "clinicaltrials_gov",
        "sourceUrl": "https://clinicaltrials.gov/study/NCT00000001",
        "briefTitle": "Demo Alzheimer Phase 3 study",
        "phase": "PHASE3",
        "conditions": ["Alzheimer's Disease"],
        "interventionNames": ["lecanemab"],
        "enrollment": 1800,
        "startDate": "2020-01-01",
        "completionDate": "2021-07-01",
        "primaryOutcomeMeasures": ["CDR-SB"],
        "whyStopped": None,
        "overallStatus": "COMPLETED",
    }
    record.update(overrides)
    return record


class NormalizeTests(unittest.TestCase):
    def test_successful_normalization(self) -> None:
        trial = normalize_amass_record(_complete_record())
        self.assertEqual(trial.id, "AMTC_demo_1")
        self.assertEqual(trial.title, "Demo Alzheimer Phase 3 study")
        self.assertEqual(trial.disease, "Alzheimer's disease")
        self.assertEqual(trial.phase, "Phase III")
        self.assertEqual(trial.intervention, "lecanemab")
        self.assertFalse(hasattr(trial, "target") and trial.__dataclass_fields__.get("target"))
        self.assertEqual(trial.disease_stage, UNKNOWN)
        self.assertIsNone(trial.biomarker_strategy)
        self.assertEqual(trial.sample_size, 1800)
        self.assertIsNone(trial.duration_months)
        self.assertEqual(trial.study_span_months, 18)
        self.assertEqual(trial.primary_endpoint, "CDR-SB")
        self.assertEqual(trial.primary_endpoint_raw, "CDR-SB")
        self.assertEqual(trial.outcome_class, "unknown")
        self.assertEqual(trial.why_stopped, UNKNOWN)
        self.assertEqual(trial.amass_id, "AMTC_demo_1")
        self.assertEqual(trial.registry_id, "NCT00000001")
        self.assertEqual(trial.source_registry, "clinicaltrials_gov")
        self.assertEqual(trial.source_url, "https://clinicaltrials.gov/study/NCT00000001")

    def test_dates_do_not_populate_duration(self) -> None:
        trial = normalize_amass_record(_complete_record())
        self.assertIsNone(trial.duration_months)
        self.assertEqual(trial.study_span_months, 18)

    def test_intervention_names_preferred(self) -> None:
        trial = normalize_amass_record(
            _complete_record(
                interventionNames=["dimebon"],
                interventionMeshTerms=["Other"],
            )
        )
        self.assertEqual(trial.intervention, "dimebon")

    def test_multiple_interventions_ambiguous(self) -> None:
        trial = normalize_amass_record(
            _complete_record(interventionNames=["lecanemab", "donanemab"])
        )
        self.assertTrue(trial.intervention.startswith("ambiguous:"))

    def test_no_intervention_unknown(self) -> None:
        trial = normalize_amass_record(
            _complete_record(interventionNames=[], interventionMeshTerms=[])
        )
        self.assertEqual(trial.intervention, UNKNOWN)

    def test_endpoint_canonicalization_from_amass(self) -> None:
        trial = normalize_amass_record(
            _complete_record(
                primaryOutcomeMeasures=["Clinical Dementia Rating Sum of Boxes"]
            )
        )
        self.assertEqual(trial.primary_endpoint, "CDR-SB")
        self.assertEqual(
            trial.primary_endpoint_raw, "Clinical Dementia Rating Sum of Boxes"
        )

    def test_provenance_extraction(self) -> None:
        trial = normalize_amass_record(
            _complete_record(sourceUrl="not-a-url", nctId="NCT9", registryId=None)
        )
        self.assertIsNone(trial.source_url)
        self.assertEqual(trial.registry_id, "NCT9")
        self.assertEqual(trial.amass_id, "AMTC_demo_1")

    def test_does_not_invent_source_url(self) -> None:
        trial = normalize_amass_record(_complete_record(sourceUrl=None))
        self.assertIsNone(trial.source_url)

    def test_missing_fields_use_unknown_not_invented_values(self) -> None:
        trial = normalize_amass_record({"amassId": "AMTC_sparse"})
        self.assertEqual(trial.id, "AMTC_sparse")
        self.assertEqual(trial.intervention, UNKNOWN)
        self.assertIsNone(trial.duration_months)
        self.assertIsNone(trial.study_span_months)
        self.assertEqual(trial.primary_endpoint, UNKNOWN)
        self.assertEqual(trial.outcome_class, "unknown")

    def test_malformed_records_are_skipped(self) -> None:
        trials, skipped = normalize_amass_records(
            ["not-an-object", {"briefTitle": "no id"}, _complete_record()]
        )
        self.assertEqual(len(trials), 1)
        self.assertEqual(len(skipped), 2)

    def test_duplicates_are_skipped(self) -> None:
        trials, skipped = normalize_amass_records(
            [_complete_record(), _complete_record()]
        )
        self.assertEqual(len(trials), 1)
        self.assertEqual(len(skipped), 1)

    def test_malformed_payload_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_amass_records({"data": []})

    def test_does_not_infer_biomarker_from_free_text(self) -> None:
        trial = normalize_amass_record(
            _complete_record(
                briefSummary="Participants must have a positive amyloid PET scan."
            )
        )
        self.assertIsNone(trial.biomarker_strategy)
        self.assertEqual(trial.disease_stage, UNKNOWN)

    def test_does_not_infer_outcome_from_status(self) -> None:
        trial = normalize_amass_record(
            _complete_record(overallStatus="TERMINATED", whyStopped="Futility")
        )
        self.assertEqual(trial.outcome_class, "unknown")
        self.assertEqual(trial.why_stopped, "Futility")


class ClientTests(unittest.TestCase):
    def test_default_limit_is_not_fifty(self) -> None:
        self.assertEqual(DEFAULT_LIMIT, 100)
        self.assertEqual(MAX_LIMIT, 300)
        self.assertNotEqual(DEFAULT_LIMIT, 50)

    def test_resolve_candidate_limit(self) -> None:
        self.assertEqual(resolve_candidate_limit("100"), 100)
        self.assertEqual(resolve_candidate_limit("300"), 300)
        with self.assertRaises(AmassConfigError):
            resolve_candidate_limit("0")
        with self.assertRaises(AmassConfigError):
            resolve_candidate_limit("301")
        with self.assertRaises(AmassConfigError):
            resolve_candidate_limit("abc")

    def test_missing_api_key(self) -> None:
        with patch.dict("os.environ", {"AMASS_API_KEY": ""}, clear=False):
            with patch("trialtwin.amass_client.load_dotenv"):
                with patch("trialtwin.amass_client.os.path.isfile", return_value=False):
                    with self.assertRaises(AmassConfigError):
                        AmassClient(api_key="")

        with patch("trialtwin.amass_client.get_amass_api_key") as getter:
            getter.side_effect = AmassConfigError("AMASS_API_KEY is missing.")
            with self.assertRaises(AmassConfigError):
                AmassClient()

    def test_search_records_success(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": [_complete_record()]}
        session.get.return_value = response

        client = AmassClient(api_key="amass_test_key", session=session)
        rows = client.search_records("Alzheimer's disease", extra_params=[("phase", "PHASE3")])
        self.assertEqual(len(rows), 1)
        kwargs = session.get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer amass_test_key")
        self.assertIn(("phase", "PHASE3"), kwargs["params"])
        self.assertIn(("limit", "100"), kwargs["params"])

    def test_configured_limit_is_sent(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": []}
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        client.search_records("Alzheimer's disease", limit=25)
        self.assertIn(("limit", "25"), session.get.call_args.kwargs["params"])

    def test_http_429(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "8"}
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        with self.assertRaises(AmassHttpError) as ctx:
            client.search_records("Alzheimer's disease")
        self.assertIn("429", str(ctx.exception))
        self.assertNotIn("amass_test_key", str(ctx.exception))

    def test_timeout(self) -> None:
        session = MagicMock()
        session.get.side_effect = requests.Timeout()
        client = AmassClient(api_key="amass_test_key", session=session)
        with self.assertRaises(AmassTimeoutError):
            client.search_records("Alzheimer's disease")

    def test_malformed_json(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        with self.assertRaises(AmassResponseError):
            client.search_records("Alzheimer's disease")

    def test_unexpected_schema(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": []}
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        with self.assertRaises(AmassResponseError):
            client.search_records("Alzheimer's disease")


class FallbackTests(unittest.TestCase):
    def test_load_local_trials(self) -> None:
        trials = load_local_trials()
        self.assertEqual(len(trials), 6)
        self.assertTrue(all(t.disease == "Alzheimer's disease" for t in trials))

    def test_use_live_false_returns_local_source(self) -> None:
        result = get_historical_trials(use_live=False)
        self.assertEqual(result.source, "LOCAL DEMO DATA")
        self.assertEqual(len(result.trials), 6)

    def test_fallback_when_amass_unavailable(self) -> None:
        with patch(
            "trialtwin.amass_client.fetch_alzheimer_phase3_trials",
            side_effect=AmassHttpError("TrialCore returned HTTP 500."),
        ):
            result = get_historical_trials(use_live=True)
        self.assertEqual(result.source, "LOCAL DEMO DATA")
        self.assertEqual(len(result.trials), 6)

    def test_programming_error_is_not_fallback(self) -> None:
        with patch(
            "trialtwin.amass_client.fetch_alzheimer_phase3_trials",
            side_effect=TypeError("unexpected bug"),
        ):
            with self.assertRaises(TypeError):
                get_historical_trials(use_live=True)

    def test_live_success_does_not_mix_in_demo_rows(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": [_complete_record()]}
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        result = get_historical_trials(use_live=True, client=client)
        self.assertEqual(result.source, "LIVE AMASS")
        self.assertEqual([t.id for t in result.trials], ["AMTC_demo_1"])

    def test_live_empty_is_not_replaced_with_demo(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": []}
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        result = get_historical_trials(use_live=True, client=client)
        self.assertEqual(result.source, "LIVE AMASS")
        self.assertEqual(result.trials, [])

    def test_non_pool_records_filtered(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "data": [_complete_record(phase="PHASE2", amassId="AMTC_p2")]
        }
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        result = get_historical_trials(use_live=True, client=client)
        self.assertEqual(result.trials, [])
        self.assertEqual(result.source, "LIVE AMASS")

    def test_fetch_never_calls_network_in_this_suite(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data": [_complete_record()]}
        session.get.return_value = response
        client = AmassClient(api_key="amass_test_key", session=session)
        trials = fetch_alzheimer_phase3_trials(client=client)
        self.assertEqual(len(trials), 1)
        self.assertTrue(str(session.get.call_args.args[0]).endswith("/trialcore/records"))


if __name__ == "__main__":
    unittest.main()
