import unittest

from ingestion import ingest_result


class IngestionTests(unittest.TestCase):
    def test_normalized_samples_run_full_cache_analysis(self):
        payload = {
            "samples": [
                {
                    "timestamp_ms": index * 10,
                    "lba": index % 3,
                    "size_bytes": 4096,
                    "operation": "write" if index % 4 == 0 else "read",
                    "latency_us": 10 + index,
                    "queue_depth": 4,
                }
                for index in range(12)
            ]
        }
        report = ingest_result(payload, name="benchmark-import", cache_pages=2)
        self.assertEqual(report["mode"], "imported-analysis")
        self.assertEqual(report["sample_count"], 12)
        self.assertEqual(set(report["cache_results"]), {"lru2", "arc", "lirs"})
        self.assertIn("latency", report["io_statistics"])

    def test_performance_points_are_analysed_without_cache_fabrication(self):
        payload = {
            "points": [
                {
                    "minute": index,
                    "bandwidth": 100 - index,
                    "iops": 1000,
                    "latency": 10 + index,
                    "temperature": 40 + index,
                }
                for index in range(8)
            ],
            "smart": {"temperature": 68},
        }
        report = ingest_result(payload, name="pressure-import")
        self.assertEqual(report["source_format"], "performance-points")
        self.assertIn("bandwidth", report["performance"])
        self.assertNotIn("cache_results", report)

    def test_fio_json_is_recognised(self):
        payload = {
            "fio version": "fio-3.38",
            "jobs": [
                {
                    "jobname": "read-job",
                    "read": {
                        "io_bytes": 8192,
                        "total_ios": 2,
                        "bw": 1024,
                        "iops": 2,
                    },
                    "write": {},
                    "trim": {},
                }
            ],
        }
        report = ingest_result(payload, name="fio-import")
        self.assertEqual(report["source_format"], "fio-json")
        self.assertEqual(report["sample_count"], 2)
        self.assertEqual(report["fio"]["job_count"], 1)
        self.assertEqual(report["io_statistics"]["read_bytes"], 8192)

    def test_nested_legacy_result_is_supported(self):
        payload = {
            "result": {
                "points": [
                    {"bandwidth": 100, "latency": 10, "temperature": 40},
                    {"bandwidth": 90, "latency": 12, "temperature": 41},
                ]
            }
        }
        report = ingest_result(payload)
        self.assertEqual(report["sample_count"], 2)

    def test_unknown_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            ingest_result({"summary": {"bandwidth": 1}})


if __name__ == "__main__":
    unittest.main()
