"""Tests for Protocol, HistoricalTrial, and the local JSON loader."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trialtwin.models import (
    Protocol,
    historical_trial_from_dict,
    load_historical_trials,
)


class ProtocolModelTests(unittest.TestCase):
    def test_construct_protocol(self) -> None:
        protocol = Protocol(
            disease="Alzheimer's disease",
            phase="Phase III",
            target="amyloid-beta",
            disease_stage="Early",
            biomarker_strategy=True,
            sample_size=1200,
            duration_months=18,
            primary_endpoint="CDR-SB",
        )
        self.assertEqual(protocol.sample_size, 1200)
        self.assertTrue(protocol.biomarker_strategy)


class HistoricalTrialLoaderTests(unittest.TestCase):
    def test_load_bundled_mock_dataset(self) -> None:
        trials = load_historical_trials()
        self.assertEqual(len(trials), 6)
        self.assertTrue(all("[DEMO/MOCK]" in trial.title for trial in trials))
        self.assertTrue(all(trial.id.startswith("DEMO-") for trial in trials))

    def test_rejects_unknown_outcome_class(self) -> None:
        record = {
            "id": "X",
            "title": "t",
            "disease": "Alzheimer's disease",
            "phase": "Phase III",
            "target": "amyloid-beta",
            "disease_stage": "early",
            "biomarker_strategy": True,
            "sample_size": 10,
            "duration_months": 12,
            "primary_endpoint": "CDR-SB",
            "outcome_class": "success",
            "why_stopped": "n/a",
        }
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
