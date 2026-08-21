import unittest

from hot_cold import HotColdClassifier, classify_workload
from models import IOSample


def sample(timestamp, page, operation="read"):
    return IOSample(timestamp, page, 4096, operation, 100)


class HotColdClassifierTests(unittest.TestCase):
    def test_repeated_reads_promote_page(self):
        classifier = HotColdClassifier(
            window_ms=1000,
            hot_threshold=3,
            cold_threshold=1,
        )
        classifier.observe(sample(0, 10))
        classifier.observe(sample(100, 10))
        heat = classifier.observe(sample(200, 10))
        self.assertEqual(heat.tier, "hot")

    def test_writes_have_configurable_weight(self):
        classifier = HotColdClassifier(
            hot_threshold=3,
            cold_threshold=1,
            write_weight=2,
        )
        classifier.observe(sample(0, 1, "write"))
        heat = classifier.observe(sample(1, 1, "write"))
        self.assertEqual(heat.score, 4)
        self.assertEqual(heat.tier, "hot")

    def test_old_accesses_are_pruned(self):
        classifier = HotColdClassifier(
            window_ms=100,
            hot_threshold=3,
            cold_threshold=1,
        )
        classifier.observe(sample(0, 1))
        classifier.observe(sample(10, 1))
        classifier.observe(sample(20, 1))
        heat = classifier.classify(1, timestamp_ms=1000)
        self.assertEqual(heat.accesses, 0)
        self.assertEqual(heat.tier, "cold")

    def test_summary_contains_transitions(self):
        result = classify_workload(
            [sample(0, 2), sample(1, 2), sample(2, 2), sample(3, 3)],
            hot_threshold=3,
            cold_threshold=1,
        )
        self.assertEqual(result["hot_pages"], 1)
        self.assertEqual(result["promotions"], 1)


if __name__ == "__main__":
    unittest.main()
