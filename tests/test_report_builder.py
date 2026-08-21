import unittest
from report_builder import build_report, executive_conclusion


class ReportTests(unittest.TestCase):
    def test_safe_report(self):
        report = build_report(
            {
                "id": 1,
                "name": "x",
                "result": {
                    "smart": {},
                    "analysis": {"bandwidth": {}},
                    "summary": {},
                    "points": [],
                },
            }
        )
        self.assertFalse(report["safety"]["writes_performed"])

    def test_conclusion(self):
        self.assertIsInstance(
            executive_conclusion(
                build_report(
                    {
                        "result": {
                            "smart": {},
                            "analysis": {"bandwidth": {}},
                            "summary": {},
                            "points": [],
                        }
                    }
                )
            ),
            str,
        )
