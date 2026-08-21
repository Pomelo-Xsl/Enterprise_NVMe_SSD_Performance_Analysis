import unittest
from alerts import evaluate_health, evaluate_result, summary


class AlertTests(unittest.TestCase):
    def test_critical_media_error(self):
        events = evaluate_health({"media_errors": 1})
        self.assertEqual(events[0].severity, "critical")

    def test_temperature_warning(self):
        self.assertTrue(
            any(
                e.code == "temperature-warning"
                for e in evaluate_health({"temperature": 70})
            )
        )

    def test_result_summary(self):
        events = evaluate_result(
            {
                "smart": {"temperature": 80},
                "analysis": {
                    "bandwidth": {"variation_percent": 0},
                    "trend": {"direction": "flat"},
                },
                "anomalies": [],
            }
        )
        self.assertEqual(summary(events)["critical"], 1)
