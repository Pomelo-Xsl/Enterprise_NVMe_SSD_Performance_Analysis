import json
import subprocess
import unittest
from types import SimpleNamespace

from device_discovery import (
    collect_device_details,
    discover_system_devices,
    merge_devices,
    parse_lsblk_json,
    parse_nvme_list_json,
)


class DeviceDiscoveryTests(unittest.TestCase):
    def test_flat_nvme_list_keeps_all_three_namespaces(self):
        payload = {
            "Devices": [
                {
                    "DevicePath": "/dev/nvme0n1",
                    "SerialNumber": "P02028500119",
                    "ModelNumber": "PLEXTOR PX-1TM9PGN +",
                    "PhysicalSize": 1_020_000_000_000,
                    "SectorSize": 512,
                    "Firmware": "1.03",
                },
                {
                    "DevicePath": "/dev/nvme1n1",
                    "SerialNumber": "PL2409AFES66410017P",
                    "ModelNumber": "PENGLAI ESSD V1.0.3 3.84TB",
                    "PhysicalSize": 3_840_000_000_000,
                    "SectorSize": 512,
                    "Firmware": "1LZ19AVQ",
                },
                {
                    "DevicePath": "/dev/nvme2n1",
                    "SerialNumber": "TE512303T826040791",
                    "ModelNumber": "TU2E3T803311",
                    "PhysicalSize": 3_840_000_000_000,
                    "SectorSize": 4096,
                    "Firmware": "00030",
                },
            ]
        }

        devices = parse_nvme_list_json(payload)

        self.assertEqual(
            [device["path"] for device in devices],
            ["/dev/nvme0n1", "/dev/nvme1n1", "/dev/nvme2n1"],
        )
        self.assertEqual(devices[2]["model"], "TU2E3T803311")
        self.assertEqual(devices[2]["sector_size"], 4096)

    def test_nested_schema_inherits_controller_identity(self):
        payload = {
            "Subsystems": [
                {
                    "Controllers": [
                        {
                            "ModelNumber": "Enterprise NVMe",
                            "SerialNumber": "SERIAL-2",
                            "Firmware": "FW2",
                            "Namespaces": [
                                {
                                    "NameSpace": "nvme2n1",
                                    "PhysicalSize": 3_840_000_000_000,
                                }
                            ],
                        }
                    ]
                }
            ]
        }

        [device] = parse_nvme_list_json(payload)

        self.assertEqual(device["path"], "/dev/nvme2n1")
        self.assertEqual(device["model"], "Enterprise NVMe")
        self.assertEqual(device["serial"], "SERIAL-2")

    def test_lsblk_supplements_namespace_missing_from_nvme_json(self):
        nvme_devices = parse_nvme_list_json(
            {
                "Devices": [
                    {"DevicePath": "/dev/nvme0n1", "ModelNumber": "SSD 0"},
                    {"DevicePath": "/dev/nvme1n1", "ModelNumber": "SSD 1"},
                ]
            }
        )
        lsblk_devices = parse_lsblk_json(
            {
                "blockdevices": [
                    {
                        "name": "nvme0n1",
                        "path": "/dev/nvme0n1",
                        "model": "SSD 0",
                        "size": 1_000_000_000_000,
                        "tran": "nvme",
                        "type": "disk",
                    },
                    {
                        "name": "nvme1n1",
                        "path": "/dev/nvme1n1",
                        "model": "SSD 1",
                        "size": 2_000_000_000_000,
                        "tran": "nvme",
                        "type": "disk",
                    },
                    {
                        "name": "nvme2n1",
                        "path": "/dev/nvme2n1",
                        "model": "TU2E3T803311",
                        "serial": "TE512303T826040791",
                        "size": 3_840_000_000_000,
                        "tran": "nvme",
                        "type": "disk",
                        "log-sec": 4096,
                    },
                ]
            }
        )

        devices = merge_devices(nvme_devices, lsblk_devices)

        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[2]["path"], "/dev/nvme2n1")
        self.assertIn("lsblk", devices[2]["source"])

    def test_non_nvme_block_device_is_ignored(self):
        devices = parse_lsblk_json(
            {
                "blockdevices": [
                    {
                        "name": "sda",
                        "path": "/dev/sda",
                        "model": "SATA SSD",
                        "size": 500_000_000_000,
                        "tran": "sata",
                        "type": "disk",
                    }
                ]
            }
        )
        self.assertEqual(devices, [])

    def test_lsblk_still_runs_when_nvme_cli_fails(self):
        lsblk_payload = {
            "blockdevices": [
                {
                    "path": "/dev/nvme2n1",
                    "model": "TU2E3T803311",
                    "size": 3_840_000_000_000,
                    "tran": "nvme",
                    "log-sec": 4096,
                }
            ]
        }

        def which(command):
            return f"/usr/bin/{command}"

        def runner(command, **_kwargs):
            if command[0].endswith("/nvme"):
                raise subprocess.CalledProcessError(2, command)
            return SimpleNamespace(stdout=json.dumps(lsblk_payload))

        devices = discover_system_devices(runner=runner, which=which)

        self.assertEqual([device["path"] for device in devices], ["/dev/nvme2n1"])
        self.assertEqual(devices[0]["sector_size"], 4096)

    def test_device_details_collects_smart_identity_and_namespace_data(self):
        responses = {
            "smart-log": {
                "temperature": 44,
                "avail_spare": 98,
                "spare_thresh": 10,
                "percentage_used": 6,
                "data_units_read": 100,
                "data_units_written": 80,
                "power_on_hours": 1200,
                "media_errors": 0,
            },
            "id-ctrl": {"vid": 5197, "ver": 0x10400, "nn": 1, "vwc": 1},
            "id-ns": {
                "nsze": 1000,
                "ncap": 1000,
                "nuse": 400,
                "flbas": 0,
                "lbafs": [{"ds": 12}],
            },
            "error-log": [{"error_count": 0}],
        }

        def runner(command, **_kwargs):
            return SimpleNamespace(stdout=json.dumps(responses[command[1]]))

        result = collect_device_details(
            {
                "path": "/dev/nvme2n1",
                "namespace": "nvme2n1",
                "model": "TU2E3T803311",
            },
            runner=runner,
            which=lambda _command: "/usr/bin/nvme",
        )

        self.assertEqual(result["health"]["level"], "healthy")
        self.assertEqual(result["smart"]["temperature_c"], 44)
        self.assertEqual(result["smart"]["life_remaining_percent"], 94)
        self.assertEqual(result["controller"]["nvme_version"], "1.4.0")
        self.assertEqual(result["namespace"]["lba_size_bytes"], 4096)
        self.assertEqual(result["namespace"]["utilized_bytes"], 400 * 4096)

    def test_device_details_remains_available_when_smart_requires_permission(self):
        def runner(command, **_kwargs):
            if command[1] == "smart-log":
                raise subprocess.CalledProcessError(13, command)
            return SimpleNamespace(stdout="{}" if command[1] != "error-log" else "[]")

        result = collect_device_details(
            {"path": "/dev/nvme2n1", "namespace": "nvme2n1"},
            runner=runner,
            which=lambda _command: "/usr/bin/nvme",
        )

        self.assertEqual(result["health"]["level"], "unknown")
        self.assertIn("unavailable", result["collection"]["command_status"]["smart"])
        self.assertEqual(result["collection"]["command_status"]["controller"], "ok")


if __name__ == "__main__":
    unittest.main()
