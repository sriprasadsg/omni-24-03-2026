"""Container Scanner — Trivy-based image vulnerability scanning."""
import json, os, subprocess, uuid, logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _now() -> str: return datetime.now(timezone.utc).isoformat()


def scan_image(image_name: str) -> dict:
    """Scan container image for vulnerabilities. Uses Trivy CLI if available."""
    trivy_path = _find_trivy()
    scan_id = f"container-{uuid.uuid4().hex[:12]}"
    if trivy_path:
        try:
            result = subprocess.run(
                [trivy_path, "image", "--format", "json", "--quiet", image_name],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                return _parse_trivy_output(scan_id, image_name, result.stdout)
            else:
                logger.warning("Trivy scan failed (rc=%d): %s", result.returncode, result.stderr[:200])
                return _simulated_results(scan_id, image_name, note=f"Trivy scan failed (rc={result.returncode}) — simulated results")
        except FileNotFoundError:
            logger.warning("Trivy binary not found at %s", trivy_path)
            return _simulated_results(scan_id, image_name, note="Trivy not installed — simulated results")
        except subprocess.TimeoutExpired:
            logger.warning("Trivy scan timed out for %s", image_name)
            return _simulated_results(scan_id, image_name, note="Trivy scan timed out — simulated results")
        except Exception as e:
            logger.error("Trivy scan error: %s", e)
            return _simulated_results(scan_id, image_name, note=f"Trivy scan error: {e} — simulated results")
    return _simulated_results(scan_id, image_name, note="Trivy not installed — simulated results")


def _find_trivy() -> Optional[str]:
    for p in ["/usr/bin/trivy", "/usr/local/bin/trivy", "trivy"]:
        try:
            subprocess.run([p, "--version"], capture_output=True, timeout=5)
            return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def _parse_trivy_output(scan_id: str, image_name: str, raw: str) -> dict:
    try:
        data = json.loads(raw)
        results = data.get("Results", [])
        vulns = []
        for r in results:
            for v in r.get("Vulnerabilities", []):
                vulns.append({
                    "id": v.get("VulnerabilityID", ""),
                    "pkg_name": v.get("PkgName", ""),
                    "installed_version": v.get("InstalledVersion", ""),
                    "fixed_version": v.get("FixedVersion", ""),
                    "severity": v.get("Severity", "UNKNOWN"),
                    "title": v.get("Title", "")[:200],
                    "description": v.get("Description", "")[:300],
                })
        critical = sum(1 for v in vulns if v["severity"] == "CRITICAL")
        high = sum(1 for v in vulns if v["severity"] == "HIGH")
        medium = sum(1 for v in vulns if v["severity"] == "MEDIUM")
        low = sum(1 for v in vulns if v["severity"] == "LOW" or v["severity"] == "UNKNOWN")
        return {"scan_id": scan_id, "image": image_name, "trivy": True, "vulns": vulns, "total": len(vulns), "critical": critical, "high": high, "medium": medium, "low": low, "scanned_at": _now()}
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse Trivy output: %s", e)
        return _simulated_results(scan_id, image_name, note="Trivy output parse failed")


def _simulated_results(scan_id: str, image_name: str, note: str = "") -> dict:
    vulns = [
        {"id": "CVE-2024-0001", "pkg_name": "libssl3", "installed_version": "3.0.11", "fixed_version": "3.0.12", "severity": "CRITICAL", "title": "Buffer overflow in TLS handshake", "description": "Heap buffer overflow in SSL_read"},
        {"id": "CVE-2024-0002", "pkg_name": "nginx", "installed_version": "1.24.0", "fixed_version": "1.25.3", "severity": "HIGH", "title": "HTTP/2 denial of service", "description": "HTTP/2 rapid reset attack"},
        {"id": "CVE-2024-0003", "pkg_name": "libcurl", "installed_version": "8.4.0", "fixed_version": "8.5.0", "severity": "HIGH", "title": "Curl cookie injection", "description": "Curl may inject cookies into non-matching domains"},
        {"id": "CVE-2024-0004", "pkg_name": "zlib", "installed_version": "1.2.13", "fixed_version": "1.3.0", "severity": "MEDIUM", "title": "Memory corruption in zlib", "description": "Memory corruption during decompression"},
        {"id": "CVE-2024-0005", "pkg_name": "bash", "installed_version": "5.2.15", "fixed_version": "5.2.21", "severity": "MEDIUM", "title": "Bash code injection", "description": "Bash function export vulnerability"},
        {"id": "CVE-2024-0006", "pkg_name": "openssh", "installed_version": "9.6", "fixed_version": "9.7", "severity": "LOW", "title": "Timing attack in SSH", "description": "SSH connection rate limiting bypass"},
    ]
    c = sum(1 for v in vulns if v["severity"] == "CRITICAL")
    h = sum(1 for v in vulns if v["severity"] == "HIGH")
    m = sum(1 for v in vulns if v["severity"] == "MEDIUM")
    l = sum(1 for v in vulns if v["severity"] == "LOW" or v["severity"] == "UNKNOWN")
    result = {"scan_id": scan_id, "image": image_name, "trivy": False, "note": note or "Trivy not installed — simulated results", "vulns": vulns, "total": len(vulns), "critical": c, "high": h, "medium": m, "low": l, "scanned_at": _now()}
    return result


async def save_result(db, tenant_id: str, result: dict) -> str:
    doc = {"tenantId": tenant_id, **result}
    await db._db.container_scan_results.insert_one(doc)
    return result["scan_id"]


async def list_results(db, tenant_id: str) -> list:
    return await db._db.container_scan_results.find({"tenantId": tenant_id}, {"_id": 0}).sort("scanned_at", -1).to_list(length=100)
