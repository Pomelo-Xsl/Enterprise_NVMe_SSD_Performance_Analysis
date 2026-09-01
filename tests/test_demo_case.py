import unittest

from demo_case import DEMO_NAME, build_demo_payload
from ingestion import ingest_result


class DemoCaseTests(unittest.TestCase):
    def test_demo_is_deterministic(self):
        first = build_demo_payload()
        second = build_demo_payload()
        self.assertEqual(first, second)

    def test_demo_contains_four_business_phases(self):
        payload = build_demo_payload()
        phases = {sample["phase"] for sample in payload["samples"]}
        self.assertEqual(
            phases,
            {
                "hot-transaction",
                "mixed-reporting",
                "maintenance-scan",
                "traffic-recovery",
            },
        )
        self.assertEqual(len(payload["samples"]), 600)

    def test_demo_has_reads_writes_and_latency_spikes(self):
        samples = build_demo_payload()["samples"]
        operations = {sample["operation"] for sample in samples}
        self.assertEqual(operations, {"read", "write"})
        self.assertGreater(max(sample["latency_us"] for sample in samples), 900)

    def test_demo_runs_complete_analysis_chain(self):
        report = ingest_result(
            build_demo_payload(),
            name=DEMO_NAME,
            cache_pages=64,
        )
        self.assertEqual(report["sample_count"], 600)
        self.assertEqual(report["metadata"]["industry"], "电商订单数据库")
        self.assertEqual(set(report["cache_results"]), {"lru2", "arc", "lirs"})
        self.assertGreater(report["alerts"]["summary"]["warning"], 0)


if __name__ == "__main__":
    unittest.main()
