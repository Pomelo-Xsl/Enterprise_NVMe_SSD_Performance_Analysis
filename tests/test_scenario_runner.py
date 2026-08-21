import unittest

from config import parse_application_config
from scenario_runner import build_workload, run_configured_scenario


def configuration(kind="mixed", algorithm="compare"):
    return parse_application_config(
        {
            "scenario": {"name": "integration", "safe_simulation": True},
            "workload": {
                "kind": kind,
                "count": 40,
                "page_count": 64,
                "seed": 3,
            },
            "cache": {
                "algorithm": algorithm,
                "capacity_pages": 8,
                "hot_threshold": 3,
                "cold_threshold": 1,
            },
        }
    )


class ScenarioRunnerTests(unittest.TestCase):
    def test_all_workloads_generate_samples(self):
        for kind in ("sequential", "random", "mixed", "hot-cold"):
            with self.subTest(kind=kind):
                samples = build_workload(configuration(kind))
                self.assertEqual(len(samples), 40)

    def test_compare_runs_all_algorithms(self):
        result = run_configured_scenario(configuration())
        self.assertEqual(
            set(result["cache_results"]),
            {"lru2", "arc", "lirs"},
        )
        self.assertEqual(result["mode"], "safe-simulation")
        self.assertFalse(result.get("writes_performed", False))

    def test_single_algorithm(self):
        result = run_configured_scenario(configuration(algorithm="arc"))
        self.assertEqual(set(result["cache_results"]), {"arc"})

    def test_result_has_complete_layers(self):
        result = run_configured_scenario(configuration())
        self.assertIn("io_statistics", result)
        self.assertIn("page_heat", result)
        self.assertIn("cache_comparison", result)
        self.assertIn("alerts", result)


if __name__ == "__main__":
    unittest.main()
