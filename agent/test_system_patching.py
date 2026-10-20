"""Tests for the System Information block of system_patching on Linux: BIOS
fields come from world-readable sysfs (dmidecode needs root, which the agent
usually lacks) and the boot time is ISO-8601 UTC."""
import datetime
import os
import subprocess
import sys
import unittest
from unittest.mock import mock_open, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from capabilities.system_patching import SystemPatchingCapability

SYSFS = {
    "/sys/class/dmi/id/bios_version": "Hyper-V UEFI Release v4.1\n",
    "/sys/class/dmi/id/bios_vendor": "Microsoft Corporation\n",
    "/sys/class/dmi/id/bios_date": "04/22/2026\n",
}

DMIDECODE = """# dmidecode 3.5
BIOS Information
\tVendor: American Megatrends Inc.
\tVersion: F.20
\tRelease Date: 03/01/2024
\tBIOS Revision: 5.17
"""


def _sysfs(files):
    def fake_open(path, *args, **kwargs):
        if path not in files:
            raise PermissionError(path)
        return mock_open(read_data=files[path])()
    return fake_open


class TestLinuxBios(unittest.TestCase):
    def setUp(self):
        self.cap = SystemPatchingCapability()

    def test_reads_sysfs_without_running_dmidecode(self):
        with patch("builtins.open", _sysfs(SYSFS)), patch("subprocess.run") as run:
            info = self.cap._get_linux_bios()
        self.assertEqual(info, {"version": "Hyper-V UEFI Release v4.1",
                                "manufacturer": "Microsoft Corporation",
                                "release_date": "04/22/2026"})
        run.assert_not_called()

    def test_falls_back_to_dmidecode_fields(self):
        done = subprocess.CompletedProcess([], 0, stdout=DMIDECODE, stderr="")
        with patch("builtins.open", _sysfs({})), patch("subprocess.run", return_value=done):
            info = self.cap._get_linux_bios()
        self.assertEqual(info, {"version": "F.20", "manufacturer": "American Megatrends Inc.",
                                "release_date": "03/01/2024"})

    def test_unknown_when_nothing_is_readable(self):
        with patch("builtins.open", _sysfs({})), patch("subprocess.run", side_effect=PermissionError):
            info = self.cap._get_linux_bios()
        self.assertEqual(set(info.values()), {"Unknown"})


class TestLinuxUptime(unittest.TestCase):
    def test_boot_time_is_iso_utc(self):
        with patch("builtins.open", mock_open(read_data="3600.00 100.00")):
            info = SystemPatchingCapability()._get_linux_uptime()
        boot = datetime.datetime.fromisoformat(info["boot_time"])
        self.assertEqual(boot.utcoffset(), datetime.timedelta(0))
        expected = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        self.assertLess(abs((boot - expected).total_seconds()), 5)


if __name__ == "__main__":
    unittest.main()
