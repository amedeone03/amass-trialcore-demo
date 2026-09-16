"""Mocked tests for Amass adapter, normalizer, and local fallback."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from trialtwin.amass_client import (
    AmassClient,
    AmassConfigError,
    AmassHttpError,
    AmassResponseError,
    AmassTimeoutError,
    fetch_alzheimer_phase3_trials,
    get_historical_trials,
    load_local_trials,
)
from trialtwin.normalize import UNKNOWN, normalize_amass_record, normalize_amass_records


def _complete_record(**overrides: object) -> dict:
    record = {
        "amassId": "AMTC_demo_1",
        "nctId": "NCT00000001",
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
        self.assertEqual(trial.target, "lecanemab")
        self.assertEqual(trial.disease_stage, UNKNOWN)
        self.assertIsNone(trial.biomarker_strategy)
        self.assertEqual(trial.sample_size, 1800)
        self.assertEqual(trial.duration_months, 18)
        self.assertEqual(trial.primary_endpoint, "CDR-SB")
        self.assertEqual(trial.outcome_class, "unknown")
        self.assertEqual(trial.why_stopped, UNKNOWN)

    def test_missing_fields_use_unknown_not_invented_values(self) -> None:
        trial = normalize_amass_record({"amassId": "AMTC_sparse"})
        self.assertEqual(trial.id, "AMTC_sparse")
        self.assertEqual(trial.title, UNKNOWN)
        self.assertEqual(trial.disease, UNKNOWN)
        self.assertEqual(trial.phase, UNKNOWN)
        self.assertEqual(trial.target, UNKNOWN)
        self.assertEqual(trial.disease_stage, UNKNOWN)
        self.assertIsNone(trial.biomarker_strategy)
        self.assertIsNone(trial.sample_size)
        self.assertIsNone(trial.duration_months)
        self.assertEqual(trial.primary_endpoint, UNKNOWN)
        self.assertEqual(trial.outcome_class, "unknown")
        self.assertEqual(trial.why_stopped, UNKNOWN)

    def test_malformed_records_are_skipped(self) -> None:
        trials, skipped = normalize_amass_records(
            ["not-an-object", {"briefTitle": "no id"}, _complete_record()]
        )
        self.assertEqual(len(trials), 1)
        self.assertEqual(len(skipped), 2)

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

    def test_does_not_infer_outcome_from_status(self) -> None:
        trial = normalize_amass_record(
            _complete_record(overallStatus="TERMINATED", whyStopped="Futility")
        )
        self.assertEqual(trial.outcome_class, "unknown")
        self.assertEqual(trial.why_stopped, "Futility")


class ClientTests(unittest.TestCase):
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
        session.get.assert_called_once()
        kwargs = session.get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer amass_test_key")
        self.assertIn(("phase", "PHASE3"), kwargs["params"])

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
        self.assertIn("Retry-After=8", str(ctx.exception))
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
        client = MagicMock()
        client.search_records.side_effect = AmassHttpError("TrialCore returned HTTP 500.")
        # fetch uses AmassClient methods; patch fetch path via a real client mock
        with patch(
            "trialtwin.amass_client.fetch_alzheimer_phase3_trials",
            side_effect=AmassHttpError("TrialCore returned HTTP 500."),
        ):
            result = get_historical_trials(use_live=True)
        self.assertEqual(result.source, "LOCAL DEMO DATA")
        self.assertEqual(len(result.trials), 6)
        self.assertIn("Amass unavailable", result.note)
        self.assertTrue(all(t.id.startswith("DEMO-") for t in result.trials))

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
