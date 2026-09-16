"""Tests for Protocol, HistoricalTrial, and the local JSON loader."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from trialtwin.models import (
    HistoricalTrial,
    Protocol,
    historical_trial_from_dict,
    load_historical_trials,
)


def _demo_record(**overrides: object) -> dict:
    record = {
        "id": "X",
        "title": "t",
        "disease": "Alzheimer's disease",
        "phase": "Phase III",
        "intervention": "amyloid-beta",
        "disease_stage": "early",
        "biomarker_strategy": True,
        "sample_size": 10,
        "duration_months": 12,
        "primary_endpoint": "CDR-SB",
        "outcome_class": "favorable",
        "why_stopped": "n/a",
    }
    record.update(overrides)
    return record


class ProtocolModelTests(unittest.TestCase):
    def test_construct_protocol_uses_intervention(self) -> None:
        protocol = Protocol(
            disease="Alzheimer's disease",
            phase="Phase III",
            intervention="amyloid-beta",
            disease_stage="Early",
            biomarker_strategy=True,
            sample_size=1200,
            duration_months=18,
            primary_endpoint="CDR-SB",
        )
        self.assertEqual(protocol.intervention, "amyloid-beta")
        self.assertFalse(hasattr(protocol, "target") and "target" in protocol.__dataclass_fields__)
        self.assertIn("intervention", Protocol.__dataclass_fields__)
        self.assertNotIn("target", Protocol.__dataclass_fields__)

    def test_historical_trial_has_no_target_field(self) -> None:
        names = {item.name for item in fields(HistoricalTrial)}
        self.assertIn("intervention", names)
        self.assertNotIn("target", names)
        self.assertIn("study_span_months", names)
        self.assertIn("amass_id", names)
        self.assertIn("registry_id", names)
        self.assertIn("source_registry", names)
        self.assertIn("source_url", names)
        self.assertIn("primary_endpoint_raw", names)


class HistoricalTrialLoaderTests(unittest.TestCase):
    def test_load_bundled_mock_dataset(self) -> None:
        trials = load_historical_trials()
        self.assertEqual(len(trials), 6)
        self.assertTrue(all("[DEMO/MOCK]" in trial.title for trial in trials))
        self.assertTrue(all(trial.id.startswith("DEMO-") for trial in trials))
        self.assertTrue(all(trial.duration_months is not None for trial in trials))
        self.assertTrue(all(trial.intervention for trial in trials))
        self.assertTrue(all(trial.source_url is None for trial in trials))

    def test_provenance_fields_accepted(self) -> None:
        trial = historical_trial_from_dict(
            _demo_record(
                amass_id="AMTC_x",
                registry_id="NCT1",
                source_registry="clinicaltrials_gov",
                study_span_months=18,
                primary_endpoint_raw="Clinical Dementia Rating-Sum of Boxes",
            )
        )
        self.assertEqual(trial.amass_id, "AMTC_x")
        self.assertEqual(trial.registry_id, "NCT1")
        self.assertEqual(trial.study_span_months, 18)
        self.assertEqual(trial.primary_endpoint_raw, "Clinical Dementia Rating-Sum of Boxes")

    def test_live_duration_can_be_none_on_dataclass(self) -> None:
        trial = HistoricalTrial(
            id="L",
            title="live",
            disease="Alzheimer's disease",
            phase="Phase III",
            intervention="lecanemab",
            disease_stage="unknown",
            biomarker_strategy=None,
            sample_size=100,
            duration_months=None,
            primary_endpoint="CDR-SB",
            outcome_class="unknown",
            why_stopped="unknown",
        )
        self.assertIsNone(trial.duration_months)

    def test_demo_duration_validated(self) -> None:
        with self.assertRaises(ValueError):
            historical_trial_from_dict(_demo_record(duration_months=-1))

    def test_rejects_unknown_outcome_class(self) -> None:
        with self.assertRaises(ValueError):
            historical_trial_from_dict(_demo_record(outcome_class="success"))

    def test_rejects_legacy_target_field(self) -> None:
        record = _demo_record()
        record["target"] = "amyloid-beta"
        del record["intervention"]
        with self.assertRaises(ValueError):
            historical_trial_from_dict(record)

    def test_invalid_json_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_historical_trials(path)
            path.write_text(json.dumps({"id": "not-an-array"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_historical_trials(path)


if __name__ == "__main__":
    unittest.main()
