import unittest
from workloads import hot_cold_alternating, mixed_io, random_io, sequential, to_points


class WorkloadTests(unittest.TestCase):
    def test_sequential_pages_increase(self):
        self.assertEqual([s.lba for s in sequential(3, 5)], [5, 6, 7])

    def test_random_seed_is_repeatable(self):
        self.assertEqual(
            [s.lba for s in random_io(5, 10)], [s.lba for s in random_io(5, 10)]
        )

    def test_mixed_has_reads_and_writes(self):
        self.assertEqual({s.operation for s in mixed_io(10, 8)}, {"read", "write"})

    def test_hot_cold_has_expected_size(self):
        self.assertEqual(len(hot_cold_alternating(3)), 60)

    def test_points_adapter(self):
        self.assertIn("bandwidth", to_points(sequential(1))[0])
