"""
Patch Installer Capability
Installs and rolls back OS patches on this host.

Windows: the Windows Update Agent (WUA) COM API through PowerShell, matching
         offered updates by KB number.
Linux:   apt-get / dnf / yum, upgrading only packages that are already installed.

Rollback never removes a package: Windows uninstalls the KB through WUA, Linux
downgrades to the version this agent recorded before it upgraded the package.
"""
from .base import BaseCapability
import json
import os
import platform
import re
import shutil
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime

_KB_RE = re.compile(r"^KB\d{4,8}$", re.IGNORECASE)
# Advisory ids (CVE-…) and KB-shaped ids of the wrong length are never treated as package names.
_NOT_PKG_RE = re.compile(r"^(CVE-\d{4}-\d+|KB\d+)$", re.IGNORECASE)
# Same rule as the backend (patch_core_endpoints.installable_patch_id): no spaces,
# quotes, shell metacharacters or leading "-", so an id never becomes an option.
_PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_:-]{0,127}$")

WINDOWS_TIMEOUT = 3600   # WUA downloads cumulative updates of several GB
LINUX_TIMEOUT = 1800
STATE_FILE = os.environ.get(
    "OMNI_PATCH_STATE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patch_state.json"),
)

_WUA_INSTALL = r"""
$ErrorActionPreference = 'Stop'
try {
    $wanted = @($env:OMNI_KBS -split ',' | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'Omni-Agent'
    $offered = $session.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Software' and IsHidden=0").Updates
    $coll = New-Object -ComObject Microsoft.Update.UpdateColl
    $index = @{}; $added = @{}
    foreach ($u in $offered) {
        foreach ($kb in $u.KBArticleIDs) {
            $id = "KB$kb"
            if ($wanted -contains $id -and -not $index.ContainsKey($id)) {
                $uid = $u.Identity.UpdateID
                if (-not $added.ContainsKey($uid)) {
                    if (-not $u.EulaAccepted) { $u.AcceptEula() }
                    $added[$uid] = $coll.Add($u)
                }
                $index[$id] = $added[$uid]
            }
        }
    }
    $results = @()
    foreach ($id in $wanted) {
        if (-not $index.ContainsKey($id)) {
            $results += @{ patch_id = $id; status = 'skipped'; reboot_required = $false;
                           message = 'Not offered by Windows Update (already installed or not applicable)' }
        }
    }
    if ($coll.Count -gt 0) {
        $dl = $session.CreateUpdateDownloader(); $dl.Updates = $coll; [void]$dl.Download()
        $inst = $session.CreateUpdateInstaller(); $inst.Updates = $coll
        $res = $inst.Install()
        foreach ($id in $index.Keys) {
            $ur = $res.GetUpdateResult($index[$id])
            # OperationResultCode: 2 = succeeded, 3 = succeeded with errors
            $ok = ($ur.ResultCode -eq 2) -or ($ur.ResultCode -eq 3)
            $status = 'failed'; $msg = 'Install failed (result code ' + $ur.ResultCode + ', HRESULT 0x' + ('{0:X8}' -f $ur.HResult) + ')'
            if ($ok) { $status = 'success'; $msg = 'Installed' }
            $results += @{ patch_id = $id; status = $status; message = $msg; reboot_required = [bool]$ur.RebootRequired }
        }
    }
    @{ results = $results } | ConvertTo-Json -Depth 4 -Compress
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 1
}
"""

_WUA_UNINSTALL = r"""
$ErrorActionPreference = 'Stop'
try {
    $wanted = @($env:OMNI_KBS -split ',' | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'Omni-Agent'
    $installed = $session.CreateUpdateSearcher().Search("IsInstalled=1 and Type='Software'").Updates
    $results = @()
    foreach ($id in $wanted) {
        $match = $null
        foreach ($u in $installed) { if ($u.KBArticleIDs | Where-Object { "KB$_" -eq $id }) { $match = $u; break } }
        if (-not $match) {
            $results += @{ patch_id = $id; status = 'failed'; reboot_required = $false; message = 'Not installed on this host' }
        } elseif (-not $match.IsUninstallable) {
            $results += @{ patch_id = $id; status = 'failed'; reboot_required = $false;
                           message = 'Windows marks this update as not uninstallable' }
        } else {
            $coll = New-Object -ComObject Microsoft.Update.UpdateColl; [void]$coll.Add($match)
            $inst = $session.CreateUpdateInstaller(); $inst.Updates = $coll
            $ur = $inst.Uninstall().GetUpdateResult(0)
            $ok = ($ur.ResultCode -eq 2) -or ($ur.ResultCode -eq 3)
            $status = 'failed'; $msg = 'Uninstall failed (result code ' + $ur.ResultCode + ')'
            if ($ok) { $status = 'success'; $msg = 'Uninstalled' }
            $results += @{ patch_id = $id; status = $status; message = $msg; reboot_required = [bool]$ur.RebootRequired }
        }
    }
    @{ results = $results } | ConvertTo-Json -Depth 4 -Compress
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 1
}
"""


def normalize_patch_id(value) -> Optional[str]:
    """A KB number (as "KB1234567") or a package name; None for anything else, CVE ids included."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if _KB_RE.match(v):
        return v.upper()
    if _NOT_PKG_RE.match(v) or not _PKG_RE.match(v):
        return None
    return v


def _result(patch_id: str, status: str, message: str, reboot: bool = False) -> Dict[str, Any]:
    return {"patch_id": patch_id, "status": status, "message": message,
            "reboot_required": reboot, "timestamp": datetime.now().isoformat()}


def _summary(results: List[Dict[str, Any]], job_id: str, error: Optional[str] = None) -> Dict[str, Any]:
    successful = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    if error or (failed and not successful):
        status = "failed"
    elif failed:
        status = "partial"
    else:
        status = "completed"
    out = {"status": status, "job_id": job_id, "total": len(results), "successful": successful,
           "failed": failed, "results": results, "timestamp": datetime.now().isoformat()}
    if error:
        out["error"] = error
    return out


class PatchInstallerCapability(BaseCapability):

    @property
    def capability_id(self) -> str:
        return "patch_installer"

    @property
    def capability_name(self) -> str:
        return "Patch Installer"

    def collect(self) -> Dict[str, Any]:
        """Not used - this capability is for execution, not collection"""
        return {}

    def execute_deployment(self, patch_ids: List[str], job_id: str) -> Dict[str, Any]:
        """Install the given KBs (Windows) or package upgrades (Linux)."""
        return self._run(patch_ids, job_id, rollback=False)

    def execute_rollback(self, patch_ids: List[str], job_id: str) -> Dict[str, Any]:
        """Uninstall the given KBs (Windows) or downgrade packages to their pre-patch version (Linux)."""
        return self._run(patch_ids, job_id, rollback=True)

    # ── shared ─────────────────────────────────────────────────────────────

    def _run(self, patch_ids: List[str], job_id: str, rollback: bool) -> Dict[str, Any]:
        system = platform.system()
        if system not in ("Windows", "Linux"):
            return _summary([], job_id, error=f"Unsupported OS: {system}")
        results, valid = [], []
        for raw in patch_ids or []:
            pid = normalize_patch_id(raw)
            if not pid:
                results.append(_result(str(raw)[:80], "failed", "Not an installable KB number or package name"))
            elif system == "Windows" and not pid.startswith("KB"):
                results.append(_result(pid, "failed", "Only Windows KB updates can be installed on Windows"))
            elif system == "Linux" and _KB_RE.match(pid):
                results.append(_result(pid, "failed", "Windows KB updates do not apply to Linux"))
            elif pid not in valid:
                valid.append(pid)
        print(f"[PatchInstaller] {'Rollback' if rollback else 'Deployment'} of {len(valid)} patch(es), job {job_id}")
        if valid:
            if system == "Windows":
                results.extend(self._windows(valid, rollback))
            else:
                results.extend(self._linux_rollback(valid) if rollback else self._linux_install(valid))
        return _summary(results, job_id)

    # ── Windows ────────────────────────────────────────────────────────────

    def _windows(self, kbs: List[str], rollback: bool) -> List[Dict[str, Any]]:
        script = _WUA_UNINSTALL if rollback else _WUA_INSTALL
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True, text=True, timeout=WINDOWS_TIMEOUT,
                env={**os.environ, "OMNI_KBS": ",".join(kbs)},
            )
        except subprocess.TimeoutExpired:
            return [_result(kb, "failed", f"Windows Update did not finish within {WINDOWS_TIMEOUT // 60} minutes") for kb in kbs]
        except Exception as e:
            return [_result(kb, "failed", f"Could not run Windows Update: {e}") for kb in kbs]
        lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
        try:
            data = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            data = {}
        if data.get("error") or not isinstance(data.get("results"), (list, dict)):
            reason = data.get("error") or (proc.stderr or proc.stdout or "no output").strip()[:300]
            return [_result(kb, "failed", f"Windows Update error: {reason}") for kb in kbs]
        raw = data["results"] if isinstance(data["results"], list) else [data["results"]]
        now = datetime.now().isoformat()
        return [{"patch_id": r.get("patch_id"), "status": r.get("status", "failed"),
                 "message": r.get("message", ""), "reboot_required": bool(r.get("reboot_required")),
                 "timestamp": now} for r in raw if isinstance(r, dict)]

    # ── Linux ──────────────────────────────────────────────────────────────

    @staticmethod
    def _manager() -> Optional[str]:
        for m in ("apt-get", "dnf", "yum"):
            if shutil.which(m):
                return m
        return None

    @staticmethod
    def _is_root() -> bool:
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def _privileged(self, cmd: List[str]) -> List[str]:
        """cmd as root: directly when the agent is root, else through passwordless sudo."""
        return cmd if self._is_root() else ["sudo", "-n"] + cmd

    def _can_escalate(self) -> bool:
        if self._is_root():
            return True
        if not shutil.which("sudo"):
            return False
        try:
            return subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=15).returncode == 0
        except Exception:
            return False

    @staticmethod
    def _installed_version(manager: str, pkg: str) -> Optional[str]:
        cmd = (["dpkg-query", "-W", "-f=${Version}", pkg] if manager == "apt-get"
               else ["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", pkg])
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception:
            return None
        version = out.stdout.strip()
        return version if out.returncode == 0 and version and "not installed" not in version else None

    @staticmethod
    def _reboot_required() -> bool:
        if os.path.exists("/var/run/reboot-required"):
            return True
        if shutil.which("needs-restarting"):
            try:
                return subprocess.run(["needs-restarting", "-r"], capture_output=True, timeout=60).returncode == 1
            except Exception:
                return False
        return False

    @staticmethod
    def _env() -> Dict[str, str]:
        return {**os.environ, "DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "a"}

    def _pm(self, cmd: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=LINUX_TIMEOUT, env=self._env())

    @staticmethod
    def _load_state() -> Dict[str, str]:
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _save_state(state: Dict[str, str]) -> None:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
        os.replace(tmp, STATE_FILE)

    def _linux_install(self, packages: List[str]) -> List[Dict[str, Any]]:
        manager = self._manager()
        if not manager:
            return [_result(p, "failed", "No supported package manager (apt-get, dnf, yum)") for p in packages]
        if not self._can_escalate():
            return [_result(p, "failed", "The agent needs root or passwordless sudo to install updates") for p in packages]
        results, state = [], self._load_state()
        if manager == "apt-get":
            try:
                self._pm(self._privileged(["apt-get", "update", "-q"]))
            except Exception as e:
                print(f"[PatchInstaller] apt-get update failed: {e}")
        for pkg in packages:
            before = self._installed_version(manager, pkg)
            if not before:
                results.append(_result(pkg, "failed", "Package is not installed; patching only upgrades installed packages"))
                continue
            if manager == "apt-get":
                cmd = ["apt-get", "install", "-y", "-q", "--only-upgrade",
                       "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold", "--", pkg]
            else:
                cmd = [manager, "upgrade", "-y", "-q", pkg]
            try:
                proc = self._pm(self._privileged(cmd))
            except subprocess.TimeoutExpired:
                results.append(_result(pkg, "failed", f"{manager} did not finish within {LINUX_TIMEOUT // 60} minutes"))
                continue
            after = self._installed_version(manager, pkg)
            if proc.returncode != 0:
                results.append(_result(pkg, "failed", f"{manager} failed: {(proc.stderr or proc.stdout).strip()[-400:]}"))
            elif after == before:
                results.append(_result(pkg, "skipped", f"Already at the newest available version ({before})"))
            else:
                state.setdefault(pkg, before)  # keep the oldest pre-patch version for rollback
                results.append(_result(pkg, "success", f"Upgraded {before} -> {after}", self._reboot_required()))
        try:
            self._save_state(state)
        except OSError as e:
            print(f"[PatchInstaller] Could not record pre-patch versions: {e}")
        return results

    def _linux_rollback(self, packages: List[str]) -> List[Dict[str, Any]]:
        manager = self._manager()
        if not manager:
            return [_result(p, "failed", "No supported package manager (apt-get, dnf, yum)") for p in packages]
        if not self._can_escalate():
            return [_result(p, "failed", "The agent needs root or passwordless sudo to roll back updates") for p in packages]
        results, state = [], self._load_state()
        for pkg in packages:
            previous = state.get(pkg)
            if not previous:
                results.append(_result(pkg, "failed",
                                       "No pre-patch version recorded by this agent; refusing to remove the package"))
                continue
            if manager == "apt-get":
                cmd = ["apt-get", "install", "-y", "-q", "--allow-downgrades",
                       "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold", "--",
                       f"{pkg}={previous}"]
            else:
                cmd = [manager, "downgrade", "-y", "-q", f"{pkg}-{previous}"]
            try:
                proc = self._pm(self._privileged(cmd))
            except subprocess.TimeoutExpired:
                results.append(_result(pkg, "failed", f"{manager} did not finish within {LINUX_TIMEOUT // 60} minutes"))
                continue
            if proc.returncode == 0 and self._installed_version(manager, pkg) == previous:
                state.pop(pkg, None)
                results.append(_result(pkg, "success", f"Downgraded to {previous}", self._reboot_required()))
            else:
                results.append(_result(pkg, "failed",
                                       f"Downgrade to {previous} failed: {(proc.stderr or proc.stdout).strip()[-400:]}"))
        try:
            self._save_state(state)
        except OSError as e:
            print(f"[PatchInstaller] Could not update pre-patch versions: {e}")
        return results
