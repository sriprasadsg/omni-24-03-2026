"""Spec C2: the agent's hardware identity block (PlatformUtils.get_hardware_identity).

Value: protects=the hostname-derived serial fallback is never sent as an identity,
Windows falls back to CIM when wmic is gone, Linux falls back to machine-id when the DMI
UUID is root-only, macOS reads IOPlatformUUID, and virtual NICs are skipped with
IP-bearing NICs first; fails_when=any of those regress; no_claim=real firmware/OS output
(commands, files and NICs are mocked).
"""
import os
import platform
import socket
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psutil
from platform_utils import PlatformUtils as P

LINK = psutil.AF_LINK


def _nic(mac, ipv4=False):
    entries = [SimpleNamespace(family=LINK, address=mac)]
    if ipv4:
        entries.append(SimpleNamespace(family=socket.AF_INET, address="10.0.0.4"))
    return entries


NICS = {"docker0": _nic("02:42:ac:11:00:01", ipv4=True), "eth1": _nic("3c:52:82:aa:bb:01"),
        "eth0": _nic("3C-52-82-AA-BB-00", ipv4=True), "lo": _nic("00:00:00:00:00:00", ipv4=True)}


class HardwareIdentityTest(unittest.TestCase):
    def _common(self, system):
        return [patch("platform_utils.platform.system", return_value=system),
                patch("platform_utils.psutil.net_if_addrs", return_value=NICS),
                patch("platform_utils.psutil.users", return_value=[SimpleNamespace(name="jdoe")]),
                patch.object(P, "detect_device_type", return_value={"device_type": "laptop"})]

    def _run_with(self, patches):
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return P.get_hardware_identity()

    def test_windows_uses_cim_when_wmic_is_gone_and_skips_hostname_serial(self):
        cim = {"(Get-CimInstance Win32_BIOS).SerialNumber": "PF3ABC12",
               "(Get-CimInstance Win32_ComputerSystemProduct).UUID": "4C4C4544-0042-3010-8051-B4C04F4D3132"}
        hw = self._run_with(self._common("Windows") + [
            patch.object(P, "get_serial_number", return_value="SN-host"),
            patch.object(P, "_run", side_effect=lambda cmd, timeout=15: cim.get(cmd[-1], ""))])
        self.assertEqual(hw["serialNumber"], "PF3ABC12")
        self.assertEqual(hw["smbiosUuid"], "4C4C4544-0042-3010-8051-B4C04F4D3132")
        self.assertEqual(hw["osFamily"], "windows")
        self.assertEqual((hw["deviceType"], hw["loggedInUser"]), ("laptop", "jdoe"))

    def test_linux_falls_back_to_machine_id_when_dmi_uuid_is_unreadable(self):
        files = {"/etc/machine-id": "0123456789abcdef0123456789abcdef"}
        hw = self._run_with(self._common("Linux") + [
            patch.object(P, "get_serial_number", return_value="SN-host"),
            patch.object(P, "_read", side_effect=lambda path: files.get(path, ""))])
        self.assertIsNone(hw["serialNumber"])
        self.assertEqual(hw["smbiosUuid"], "01234567-89ab-cdef-0123-456789abcdef")

    def test_macos_reads_ioplatformuuid(self):
        ioreg = '  "IOPlatformUUID" = "564D1234-ABCD-0000-1111-222233334444"\n'
        hw = self._run_with(self._common("Darwin") + [
            patch.object(P, "get_serial_number", return_value="C02XYZ"),
            patch.object(P, "_run", return_value=ioreg)])
        self.assertEqual(hw["smbiosUuid"], "564D1234-ABCD-0000-1111-222233334444")
        self.assertEqual((hw["serialNumber"], hw["osFamily"]), ("C02XYZ", "macos"))

    def test_virtual_nics_are_skipped_and_ip_bearing_nics_come_first(self):
        hw = self._run_with(self._common("Linux") + [
            patch.object(P, "get_serial_number", return_value="SN-host"),
            patch.object(P, "_read", return_value="")])
        self.assertEqual(hw["macAddresses"], ["3c:52:82:aa:bb:00", "3c:52:82:aa:bb:01"])


if __name__ == "__main__":
    unittest.main()


class OsNameTest(unittest.TestCase):
    """protects=the hardware block names the OS product so the platform can tell Windows
    Server from a workstation (spec C4 sub-limits); fails_when=the edition is lost."""

    def test_windows_server_edition_is_in_the_name(self):
        with patch.object(platform, "release", return_value="2022Server"), \
                patch.object(platform, "win32_edition", return_value="ServerDatacenter", create=True):
            self.assertIn("Server", P._os_name("Windows"))

    def test_linux_uses_os_release_pretty_name(self):
        with patch.object(P, "_read", return_value='NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 24.04.4 LTS"\n'):
            self.assertEqual(P._os_name("Linux"), "Ubuntu 24.04.4 LTS")
