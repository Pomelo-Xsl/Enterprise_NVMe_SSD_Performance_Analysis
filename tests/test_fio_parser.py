import unittest

from fio_parser import (
    parse_direction,
    parse_fio_json,
    parse_fio_log_lines,
    summarize_jobs,
)


class FioParserTests(unittest.TestCase):
    def test_direction_converts_nanoseconds(self):
        result = parse_direction(
            "read",
            {
                "io_bytes": 4096,
                "bw": 1024,
                "iops": 250,
                "runtime": 1000,
                "clat_ns": {
                    "mean": 12000,
                    "percentile": {"99.000000": 30000},
                },
            },
        )
        self.assertEqual(result.latency_mean_us, 12)
        self.assertEqual(result.latency_percentiles_us["99.000000"], 30)

    def test_parse_complete_json(self):
        result = parse_fio_json(
            {
                "fio version": "fio-3.35",
                "jobs": [
                    {
                        "jobname": "mixed",
                        "read": {"io_bytes": 100, "iops": 10},
                        "write": {"io_bytes": 300, "iops": 20},
                    }
                ],
            }
        )
        self.assertEqual(result["job_count"], 1)
        summary = summarize_jobs(result)
        self.assertEqual(summary["write_ratio"], 0.75)

    def test_log_parser(self):
        samples = parse_fio_log_lines(
            ["0, 1000, 0, 4096", "1000, 800, 1, 4096"],
            "bandwidth_kib_s",
        )
        self.assertEqual(samples[0]["operation"], "read")
        self.assertEqual(samples[1]["operation"], "write")

    def test_log_parser_skips_comments(self):
        result = parse_fio_log_lines(["# fio log", "", "1,2"], "iops")
        self.assertEqual(len(result), 1)

    def test_invalid_log_row(self):
        with self.assertRaises(ValueError):
            parse_fio_log_lines(["broken"], "iops")


if __name__ == "__main__":
    unittest.main()
