import tempfile
import unittest
from pathlib import Path

from config import (
    load_application_config,
    parse_application_config,
    parse_cache,
    parse_logging,
    parse_thresholds,
    parse_workload,
)


class ConfigurationTests(unittest.TestCase):
    def test_default_application_config(self):
        result = parse_application_config({"scenario": {"name": "test"}})
        self.assertEqual(result.scenario.name, "test")
        self.assertTrue(result.scenario.safe_simulation)
        self.assertEqual(result.cache.algorithm, "compare")

    def test_rejects_real_execution(self):
        with self.assertRaises(ValueError):
            parse_application_config(
                {"scenario": {"name": "unsafe", "safe_simulation": False}}
            )

    def test_cache_validation(self):
        with self.assertRaises(ValueError):
            parse_cache({"cache": {"algorithm": "fifo"}})
        with self.assertRaises(ValueError):
            parse_cache({"cache": {"hot_threshold": 1, "cold_threshold": 2}})

    def test_workload_validation(self):
        with self.assertRaises(ValueError):
            parse_workload({"workload": {"kind": "invalid"}})
        with self.assertRaises(ValueError):
            parse_workload({"workload": {"read_ratio": 2}})

    def test_alert_validation(self):
        with self.assertRaises(ValueError):
            parse_thresholds(
                {
                    "alerts": {
                        "temperature_warning": 80,
                        "temperature_critical": 70,
                    }
                }
            )

    def test_logging_validation(self):
        self.assertEqual(parse_logging({}).level, "INFO")
        with self.assertRaises(ValueError):
            parse_logging({"logging": {"level": "TRACE"}})

    def test_load_yaml_file(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML is not installed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.yaml"
            path.write_text(
                "scenario:\n  name: yaml-test\n  safe_simulation: true\n",
                encoding="utf-8",
            )
            result = load_application_config(path)
            self.assertEqual(result.scenario.name, "yaml-test")


if __name__ == "__main__":
    unittest.main()
