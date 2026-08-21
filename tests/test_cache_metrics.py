import unittest

from cache_metrics import compare_results, decompose_events


class CacheMetricTests(unittest.TestCase):
    def test_hit_and_eviction_decomposition(self):
        metrics = decompose_events(
            [
                {"page": 1, "hit": False, "hot": False},
                {"page": 1, "hit": True, "hot": True},
                {
                    "page": 2,
                    "hit": False,
                    "hot": False,
                    "evicted": 1,
                    "dirty_eviction": True,
                },
            ]
        )
        self.assertEqual(metrics["hits"], 1)
        self.assertEqual(metrics["hot_hits"], 1)
        self.assertEqual(metrics["dirty_evictions"], 1)

    def test_algorithm_ranking_prefers_hit_ratio(self):
        result = compare_results(
            {
                "a": {
                    "events": [
                        {"page": 1, "hit": True, "hot": True},
                        {"page": 1, "hit": True, "hot": True},
                    ],
                    "state": {},
                },
                "b": {
                    "events": [
                        {"page": 1, "hit": False, "hot": False},
                        {"page": 2, "hit": False, "hot": False},
                    ],
                    "state": {},
                },
            }
        )
        self.assertEqual(result["best_algorithm"], "a")


if __name__ == "__main__":
    unittest.main()
