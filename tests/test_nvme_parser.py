import unittest

from models import DeviceInfo
from nvme_parser import (
    device_risk,
    parse_device_bundle,
    parse_error_log,
    parse_identify_controller,
    parse_identify_namespace,
    parse_list_device,
    parse_smart_log,
)


class NvmeParserTests(unittest.TestCase):
    def test_list_device(self):
        device = parse_list_device(
            {
                "DevicePath": "/dev/nvme0n1",
                "ModelNumber": " PM9A3 ",
                "SerialNumber": " SERIAL ",
                "Firmware": " FW1 ",
                "UsedBytes": 1000,
            }
        )
        self.assertEqual(device.model, "PM9A3")
        self.assertEqual(device.capacity_bytes, 1000)

    def test_smart_log_variants(self):
        device = parse_smart_log(
            {
                "temperature": "68 C",
                "percentage_used": 3,
                "media_errors": 1,
                "num_err_log_entries": 2,
            },
            DeviceInfo(path="/dev/nvme0n1"),
        )
        self.assertEqual(device.temperature_c, 68)
        self.assertEqual(device.media_errors, 1)

    def test_controller_write_cache(self):
        result = parse_identify_controller({"vwc": 1, "nn": 2, "mn": "SSD"})
        self.assertTrue(result["volatile_write_cache_supported"])
        self.assertEqual(result["namespace_count"], 2)

    def test_namespace_capacity(self):
        result = parse_identify_namespace(
            {
                "nsze": 100,
                "ncap": 90,
                "nuse": 50,
                "flbas": 0,
                "lbafs": [{"ds": 12}],
            }
        )
        self.assertEqual(result["lba_size_bytes"], 4096)
        self.assertEqual(result["size_bytes"], 409600)

    def test_error_log_summary(self):
        result = parse_error_log(
            [
                {"error_count": 0},
                {"error_count": 3, "status_field": "media", "lba": 5},
            ]
        )
        self.assertEqual(result["active_entry_count"], 1)
        self.assertEqual(result["total_error_count"], 3)

    def test_device_risk(self):
        events = device_risk(DeviceInfo(path="x", temperature_c=80, media_errors=1))
        self.assertTrue(any(item["code"] == "thermal-critical" for item in events))
        self.assertTrue(any(item["code"] == "media-error" for item in events))

    def test_bundle_contract(self):
        result = parse_device_bundle(
            {
                "list": {"DevicePath": "/dev/nvme0n1"},
                "smart": {"temperature": 40},
                "identify_controller": {"vwc": 1},
                "identify_namespace": {},
                "error_log": [],
            }
        )
        self.assertIn("controller", result)
        self.assertIn("namespace", result)


if __name__ == "__main__":
    unittest.main()
