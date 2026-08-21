import unittest
from simulation import run_simulation


class SimulationTests(unittest.TestCase):
    def test_full_chain(self):
        result = run_simulation("mixed", 40, 8)
        self.assertEqual(result["mode"], "safe-simulation")
        self.assertEqual(set(result["cache_comparison"]), {"lru2", "arc", "lirs"})

    def test_bad_workload(self):
        with self.assertRaises(ValueError):
            run_simulation("bad")
