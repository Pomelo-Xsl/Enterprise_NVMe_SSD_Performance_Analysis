import unittest

from io_analysis import (
    analyze_io,
    block_size_breakdown,
    direction_breakdown,
    latency_distribution,
    queue_depth_distribution,
    time_windows,
)
from models import IOSample


def workload():
    return [
        IOSample(0, 0, 4096, "read", 10, 1),
        IOSample(100, 1, 4096, "read", 20, 4),
        IOSample(200, 2, 8192, "write", 30, 4),
        IOSample(1200, 3, 8192, "write", 40, 8),
    ]


class IOAnalysisTests(unittest.TestCase):
    def test_latency_percentiles(self):
        result = latency_distribution(workload())
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["p50_us"], 25)
        self.assertGreater(result["p999_us"], 39)

    def test_direction_breakdown(self):
        result = direction_breakdown(workload())
        self.assertEqual(result["read"]["operations"], 2)
        self.assertEqual(result["write"]["operations"], 2)
        self.assertEqual(result["read"]["ratio"], 0.5)

    def test_block_size_breakdown(self):
        result = block_size_breakdown(workload())
        self.assertEqual(result["4096"]["read_operations"], 2)
        self.assertEqual(result["8192"]["write_operations"], 2)

    def test_time_windows(self):
        result = time_windows(workload(), window_ms=1000)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["operations"], 3)
        self.assertEqual(result[1]["writes"], 1)

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            time_windows(workload(), window_ms=0)

    def test_queue_depth_distribution(self):
        result = queue_depth_distribution(workload())
        self.assertEqual(result["4"]["operations"], 2)
        self.assertAlmostEqual(sum(item["ratio"] for item in result.values()), 1)

    def test_complete_contract(self):
        result = analyze_io(workload())
        self.assertEqual(result["sample_count"], 4)
        self.assertEqual(result["unique_lbas"], 4)
        self.assertIn("time_windows", result)


if __name__ == "__main__":
    unittest.main()
