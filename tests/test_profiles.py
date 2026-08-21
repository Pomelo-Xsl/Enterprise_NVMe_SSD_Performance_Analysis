import unittest

from profiles import apply_profile, get_profile, list_profiles, safe_fio_preview, validate_parameters


class ProfileTests(unittest.TestCase):
    def test_catalogue_has_standard_profiles(self):
        self.assertGreaterEqual(len(list_profiles()), 5)
        self.assertEqual(get_profile("random-write").block_size, "4K")

    def test_profile_overrides_are_validated(self):
        result = apply_profile("sustained-write", {"runtime": 600, "io_depth": 64})
        self.assertEqual(result["runtime"], 600)
        with self.assertRaises(ValueError):
            apply_profile("sustained-write", {"block_size": "3K"})

    def test_preview_contains_no_execution(self):
        profile = apply_profile("burst-write")
        preview = safe_fio_preview(profile, "/dev/nvme0n1")
        self.assertIn("--filename=/dev/nvme0n1", preview)
        self.assertNotIn("--run", preview)

    def test_invalid_numeric_values_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_parameters({"block_size": "4K", "rw": "write", "io_depth": 0, "jobs": 1, "runtime": 30, "ramp_time": 0})


if __name__ == "__main__":
    unittest.main()
