import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from cli import analyze_result, parser


class CLITests(unittest.TestCase):
    def test_required_business_commands_exist(self):
        command_parser = parser()
        for command in (
            "analyze-result",
            "show-cache-stat",
            "export-report",
            "run-scenario",
            "validate-config",
            "export-full-report",
        ):
            args = command_parser.parse_args(self._minimum_arguments(command))
            self.assertEqual(args.command, command)

    @staticmethod
    def _minimum_arguments(command):
        arguments = {
            "analyze-result": ["input.json"],
            "show-cache-stat": ["--pages", "1,2,1"],
            "export-report": ["input.json", "--output", "out.json"],
            "export-full-report": ["input.json", "--output", "out.json"],
        }
        return [command, *arguments.get(command, [])]

    def test_analyze_normalized_samples(self):
        payload = {
            "samples": [
                {
                    "timestamp_ms": 0,
                    "lba": 1,
                    "size_bytes": 4096,
                    "operation": "read",
                    "latency_us": 10,
                    "queue_depth": 1,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samples.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                analyze_result(argparse.Namespace(input=str(path)))
        result = json.loads(output.getvalue())
        self.assertEqual(result["sample_count"], 1)
        self.assertIn("latency", result)

    def test_analyze_fio_json(self):
        payload = {
            "jobs": [
                {
                    "jobname": "read-job",
                    "read": {
                        "io_bytes": 4096,
                        "bw_bytes": 1024,
                        "iops": 2,
                        "total_ios": 2,
                        "clat_ns": {
                            "mean": 1000,
                            "percentile": {"99.000000": 2000},
                        },
                    },
                    "write": {},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fio.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                analyze_result(argparse.Namespace(input=str(path)))
        result = json.loads(output.getvalue())
        self.assertEqual(result["job_count"], 1)
        self.assertIn("aggregate", result)


if __name__ == "__main__":
    unittest.main()
