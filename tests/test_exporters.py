import unittest
from exporters import (
    cache_comparison_csv,
    flatten_mapping,
    io_samples_csv,
    report_json,
    report_summary_csv,
    samples_csv,
    task_json,
)


class ExportTests(unittest.TestCase):
    def test_csv_has_headers_and_values(self):
        text = samples_csv(
            [
                {
                    "minute": 1,
                    "bandwidth": 100,
                    "iops": 5,
                    "latency": 9,
                    "temperature": 40,
                }
            ]
        )
        self.assertIn("bandwidth", text)
        self.assertIn("100", text)

    def test_json_preserves_chinese(self):
        self.assertIn("测试", task_json({"name": "测试"}))

    def test_flatten_mapping(self):
        result = flatten_mapping({"a": {"b": 1}, "items": [1, 2]})
        self.assertEqual(result["a.b"], 1)
        self.assertIn("[1, 2]", result["items"])

    def test_report_summary_csv(self):
        text = report_summary_csv({"summary": {"peak": 10}, "samples": []})
        self.assertIn("summary.peak", text)
        self.assertNotIn("samples", text)

    def test_io_samples_csv(self):
        text = io_samples_csv(
            [
                {
                    "timestamp_ms": 1,
                    "lba": 2,
                    "size_bytes": 4096,
                    "operation": "read",
                    "latency_us": 10,
                    "queue_depth": 1,
                }
            ]
        )
        self.assertIn("latency_us", text)
        self.assertIn("4096", text)

    def test_cache_comparison_csv(self):
        text = cache_comparison_csv({"algorithms": {"arc": {"hits": 1, "misses": 2}}})
        self.assertIn("algorithm", text)
        self.assertIn("arc", text)

    def test_report_json(self):
        self.assertIn("测试", report_json({"name": "测试"}))


if __name__ == "__main__":
    unittest.main()
