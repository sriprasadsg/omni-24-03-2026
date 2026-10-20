"""Tests for OS patch install/rollback (capabilities/patch_installer.py) and the
agent's install_patches dispatch (AgentCapabilityManager.start_patch_job).
No package manager or Windows Update runs: subprocess is mocked throughout."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from capabilities.patch_installer import PatchInstallerCapability, normalize_patch_id


def _done(cmd, rc=0, out="", err=""):
    return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)


class TestPatchIds(unittest.TestCase):
    def test_kb_numbers_and_package_names(self):
        self.assertEqual(normalize_patch_id("kb5034441"), "KB5034441")
        self.assertEqual(normalize_patch_id("openssl"), "openssl")
        self.assertEqual(normalize_patch_id("openssl.x86_64"), "openssl.x86_64")

    def test_cve_ids_and_injection_attempts_are_rejected(self):
        for bad in ("CVE-2026-40079", "CVE-2026-1", "KB12", "openssl; reboot", "-o x", "a b", "$(id)", "", None, 5):
            self.assertIsNone(normalize_patch_id(bad), bad)


class LinuxCase(unittest.TestCase):
    """A Linux host with apt-get, running the agent as a normal user with passwordless sudo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "patch_state.json")
        self.calls = []
        self.versions = {"openssl": ["3.0.1", "3.0.2"]}
        for target, value in (("patch_installer.STATE_FILE", self.state),
                              ("patch_installer.platform.system", MagicMock(return_value="Linux")),
                              ("patch_installer.shutil.which", MagicMock(side_effect=self._which)),
                              ("patch_installer.os.geteuid", MagicMock(return_value=1000)),
                              ("patch_installer.os.path.exists", MagicMock(return_value=False)),
                              ("patch_installer.subprocess.run", MagicMock(side_effect=self._run))):
            p = patch("capabilities." + target, value)
            p.start()
            self.addCleanup(p.stop)
        self.cap = PatchInstallerCapability()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _which(name):
        return f"/usr/bin/{name}" if name in ("apt-get", "sudo") else None

    def _run(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if cmd[0] == "dpkg-query":
            seq = self.versions.get(cmd[-1])
            if not seq:
                return _done(cmd, 1, "", "no packages found")
            return _done(cmd, 0, seq.pop(0) if len(seq) > 1 else seq[0])
        return _done(cmd)

    def pm_calls(self):
        return [c for c, _ in self.calls if c[:2] == ["sudo", "-n"] and c[2:3] != ["true"]]


class TestLinuxInstall(LinuxCase):
    def test_upgrades_an_installed_package_noninteractively_and_records_the_old_version(self):
        out = self.cap.execute_deployment(["openssl"], "job-1")
        self.assertEqual(out["status"], "completed", out)
        self.assertEqual(out["results"][0]["status"], "success")
        self.assertIn("3.0.1 -> 3.0.2", out["results"][0]["message"])
        install = next(c for c in self.pm_calls() if "install" in c)
        self.assertEqual(install[:3], ["sudo", "-n", "apt-get"])
        self.assertIn("--only-upgrade", install)
        self.assertEqual(install[-2:], ["--", "openssl"])
        env = next(kw["env"] for c, kw in self.calls if "install" in c)
        self.assertEqual(env["DEBIAN_FRONTEND"], "noninteractive")
        with open(self.state) as f:
            self.assertEqual(json.load(f), {"openssl": "3.0.1"})

    def test_a_package_that_is_not_installed_is_never_installed(self):
        out = self.cap.execute_deployment(["nginx"], "job-2")
        self.assertEqual(out["status"], "failed")
        self.assertIn("not installed", out["results"][0]["message"])
        self.assertFalse([c for c in self.pm_calls() if "install" in c])

    def test_windows_kbs_and_cve_ids_are_refused_on_linux(self):
        out = self.cap.execute_deployment(["KB5034441", "CVE-2026-40079"], "job-3")
        self.assertEqual(out["failed"], 2)
        self.assertFalse(self.pm_calls())

    def test_no_sudo_means_a_clear_failure(self):
        self.calls.clear()
        with patch("capabilities.patch_installer.subprocess.run",
                   MagicMock(side_effect=lambda cmd, **kw: _done(cmd, 1, "", "a password is required"))):
            out = self.cap.execute_deployment(["openssl"], "job-4")
        self.assertIn("passwordless sudo", out["results"][0]["message"])


class TestLinuxRollback(LinuxCase):
    def test_rollback_without_a_recorded_version_refuses_and_never_removes(self):
        out = self.cap.execute_rollback(["openssl"], "job-5")
        self.assertEqual(out["status"], "failed")
        self.assertIn("refusing to remove", out["results"][0]["message"])
        self.assertFalse([c for c, _ in self.calls if "remove" in c or "purge" in c])

    def test_rollback_downgrades_to_the_recorded_version(self):
        with open(self.state, "w") as f:
            json.dump({"openssl": "3.0.1"}, f)
        self.versions = {"openssl": ["3.0.1"]}
        out = self.cap.execute_rollback(["openssl"], "job-6")
        self.assertEqual(out["status"], "completed", out)
        cmd = next(c for c in self.pm_calls() if "install" in c)
        self.assertIn("--allow-downgrades", cmd)
        self.assertEqual(cmd[-1], "openssl=3.0.1")
        self.assertFalse([c for c, _ in self.calls if "remove" in c or "purge" in c])
        with open(self.state) as f:
            self.assertEqual(json.load(f), {})


class TestWindows(unittest.TestCase):
    def setUp(self):
        for target, value in (("patch_installer.platform.system", MagicMock(return_value="Windows")),):
            p = patch("capabilities." + target, value)
            p.start()
            self.addCleanup(p.stop)
        self.cap = PatchInstallerCapability()

    def test_kbs_reach_powershell_through_the_environment_not_the_script(self):
        stdout = json.dumps({"results": [
            {"patch_id": "KB5034441", "status": "success", "message": "Installed", "reboot_required": True},
            {"patch_id": "KB5035845", "status": "skipped", "message": "Not offered", "reboot_required": False}]})
        run = MagicMock(return_value=_done([], 0, "WARNING: noise\n" + stdout))
        with patch("capabilities.patch_installer.subprocess.run", run):
            out = self.cap.execute_deployment(["kb5034441", "KB5035845", "openssl"], "job-7")
        cmd, kw = run.call_args
        self.assertEqual(kw["env"]["OMNI_KBS"], "KB5034441,KB5035845")
        self.assertNotIn("KB5034441", cmd[0][-1])  # the script itself never contains the ids
        self.assertIn("KBArticleIDs", cmd[0][-1])
        self.assertEqual(out["successful"], 1)
        self.assertEqual(out["failed"], 1)  # "openssl" is not a Windows KB
        self.assertTrue(out["results"][1]["reboot_required"])

    def test_a_windows_update_error_fails_every_kb_with_the_reason(self):
        run = MagicMock(return_value=_done([], 1, json.dumps({"error": "0x8024402C"})))
        with patch("capabilities.patch_installer.subprocess.run", run):
            out = self.cap.execute_deployment(["KB5034441"], "job-8")
        self.assertEqual(out["status"], "failed")
        self.assertIn("0x8024402C", out["results"][0]["message"])

    def test_rollback_uses_the_wua_uninstall_script(self):
        run = MagicMock(return_value=_done([], 0, json.dumps({"results": {
            "patch_id": "KB5034441", "status": "success", "message": "Uninstalled"}})))
        with patch("capabilities.patch_installer.subprocess.run", run):
            out = self.cap.execute_rollback(["KB5034441"], "job-9")
        self.assertIn(".Uninstall()", run.call_args[0][0][-1])
        self.assertEqual(out["status"], "completed")


class TestStartPatchJob(unittest.TestCase):
    """AgentCapabilityManager.start_patch_job: payload parsing, background run, result report."""

    def setUp(self):
        import agent as agent_module
        self.agent_module = agent_module
        self.cap = MagicMock()
        self.cap.execute_deployment.return_value = {"status": "completed", "results": []}
        self.mgr = MagicMock()
        self.mgr.capability_instances = {"patch_installer": self.cap}
        self.mgr.cfg = {"api_base_url": "https://platform.example.test"}
        self.mgr._auth_headers.return_value = {"Authorization": "Bearer t"}
        del self.mgr._patch_lock  # let start_patch_job create the real lock

    def test_reads_patch_ids_from_the_payload_and_reports_the_result(self):
        posted = threading.Event()
        with patch.object(self.agent_module.requests, "post", side_effect=lambda *a, **k: posted.set()) as post:
            reply = self.agent_module.AgentCapabilityManager.start_patch_job(
                self.mgr, "install_patches", {"patch_ids": ["KB5034441"], "job_id": "job-10"})
            self.assertTrue(posted.wait(5), "the result was never reported")
        self.assertEqual(reply["status"], "accepted")
        self.cap.execute_deployment.assert_called_once_with(["KB5034441"], "job-10")
        self.assertEqual(post.call_args[0][0], "https://platform.example.test/api/deployments/job-10/result")

    def test_an_instruction_without_patch_ids_is_an_error(self):
        reply = self.agent_module.AgentCapabilityManager.start_patch_job(self.mgr, "install_patches", {})
        self.assertEqual(reply["status"], "error")
        self.cap.execute_deployment.assert_not_called()


if __name__ == "__main__":
    unittest.main()
