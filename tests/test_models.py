import unittest

from models import IOSample


class IOSampleModelTests(unittest.TestCase):
    def test_round_trip(self):
        original = IOSample(10, 20, 4096, "read", 12.5, 4)
        self.assertEqual(IOSample.from_dict(original.to_dict()), original)

    def test_default_queue_depth(self):
        sample = IOSample.from_dict(
            {
                "timestamp_ms": 1,
                "lba": 2,
                "size_bytes": 4096,
                "operation": "write",
                "latency_us": 8,
            }
        )
        self.assertEqual(sample.queue_depth, 1)

    def test_invalid_operation(self):
        with self.assertRaises(ValueError):
            IOSample.from_dict(
                {
                    "timestamp_ms": 1,
                    "lba": 2,
                    "size_bytes": 4096,
                    "operation": "trim",
                    "latency_us": 8,
                }
            )

    def test_invalid_numeric_ranges(self):
        values = {
            "timestamp_ms": 1,
            "lba": 2,
            "size_bytes": 0,
            "operation": "read",
            "latency_us": 8,
        }
        with self.assertRaises(ValueError):
            IOSample.from_dict(values)


if __name__ == "__main__":
    unittest.main()
