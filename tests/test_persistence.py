import tempfile
import unittest
from pathlib import Path

from persistence import Repository


def result_fixture():
    return {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "configuration": {
            "scenario": {"name": "test"},
            "workload": {"kind": "mixed"},
            "cache": {"algorithm": "compare"},
        },
        "sample_count": 10,
        "alerts": {
            "events": [
                {
                    "code": "test-warning",
                    "severity": "warning",
                    "message": "test",
                    "source": "unit",
                    "value": 2,
                    "threshold": 1,
                }
            ]
        },
    }


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repository = Repository(Path(self.directory.name) / "test.db")
        self.repository.initialize()

    def tearDown(self):
        self.directory.cleanup()

    def test_save_and_read_run(self):
        run_id = self.repository.save_run(result_fixture())
        self.assertGreater(run_id, 0)
        self.assertEqual(self.repository.get_run(run_id)["sample_count"], 10)
        self.assertEqual(self.repository.list_runs()[0]["scenario_name"], "test")

    def test_alert_is_persisted_and_acknowledged(self):
        run_id = self.repository.save_run(result_fixture())
        alerts = self.repository.list_alerts(run_id=run_id)
        self.assertEqual(len(alerts), 1)
        self.assertFalse(alerts[0]["acknowledged"])
        self.assertTrue(self.repository.acknowledge_alert(alerts[0]["id"]))
        self.assertTrue(self.repository.list_alerts(run_id=run_id)[0]["acknowledged"])

    def test_alert_filters(self):
        self.repository.save_run(result_fixture())
        self.assertEqual(len(self.repository.list_alerts(severity="warning")), 1)
        self.assertEqual(len(self.repository.list_alerts(severity="critical")), 0)

    def test_delete_cascades_alerts(self):
        run_id = self.repository.save_run(result_fixture())
        self.assertTrue(self.repository.delete_run(run_id))
        self.assertIsNone(self.repository.get_run(run_id))
        self.assertEqual(self.repository.list_alerts(run_id=run_id), [])


if __name__ == "__main__":
    unittest.main()
