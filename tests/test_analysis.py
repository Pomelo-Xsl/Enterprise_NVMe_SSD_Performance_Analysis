import unittest

from analysis import analyse, describe, detect_knee, latency_qos, percentile, recovery_rate, stability_grade, temperature_correlation


def samples():
    return [
        {"bandwidth": 100, "iops": 1000, "latency": 10, "temperature": 40},
        {"bandwidth": 102, "iops": 1010, "latency": 12, "temperature": 41},
        {"bandwidth": 99, "iops": 990, "latency": 11, "temperature": 42},
        {"bandwidth": 60, "iops": 600, "latency": 35, "temperature": 50},
        {"bandwidth": 61, "iops": 610, "latency": 37, "temperature": 52},
        {"bandwidth": 59, "iops": 590, "latency": 36, "temperature": 53},
    ]


class StatisticsTests(unittest.TestCase):
    def test_describe_empty(self):
        self.assertEqual(describe([]).count, 0)

    def test_describe_variation(self):
        stats = describe([10, 10, 10])
        self.assertEqual(stats.average, 10)
        self.assertEqual(stats.variation_percent, 0)
        self.assertEqual(stability_grade(stats), "优秀")

    def test_percentile_bounds_and_interpolation(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([1, 2], 0), 1)
        self.assertEqual(percentile([1, 2], 100), 2)
        with self.assertRaises(ValueError):
            percentile([1], 101)

    def test_qos_percentiles(self):
        qos = latency_qos(samples())
        self.assertGreater(qos["p99"], qos["p50"])
        self.assertGreater(qos["p9999"], 0)


class BehaviourTests(unittest.TestCase):
    def test_detect_sustained_knee(self):
        knee = detect_knee([item["bandwidth"] for item in samples()], window=3, threshold_percent=20)
        self.assertIsNotNone(knee)
        self.assertEqual(knee.index, 3)
        self.assertGreater(knee.drop_percent, 20)

    def test_no_knee_for_short_series(self):
        self.assertIsNone(detect_knee([100, 90, 80], window=2))

    def test_recovery_rate(self):
        self.assertEqual(recovery_rate(100, 94.2), 94.2)
        self.assertEqual(recovery_rate(0, 100), 0)

    def test_temperature_correlation(self):
        self.assertLess(temperature_correlation(samples()), 0)

    def test_full_analysis_contract(self):
        result = analyse(samples())
        self.assertIn("bandwidth", result)
        self.assertIn("latency", result)
        self.assertIn("stability", result)
        self.assertIsNotNone(result["knee"])


if __name__ == "__main__":
    unittest.main()
