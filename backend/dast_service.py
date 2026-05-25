"""
DAST (Dynamic Application Security Testing) Service
Runs lightweight HTTP-based security checks against target URLs:
  - Security header analysis (CSP, HSTS, X-Frame-Options, etc.)
  - TLS/HTTPS enforcement
  - Common sensitive path exposure
  - Cookie security flags
"""

import asyncio
import ipaddress
import os as _os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from authentication_service import get_current_user
from auth_types import TokenData

_SSL_VERIFY = not _os.getenv("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes")

router = APIRouter(prefix="/api/dast", tags=["Dynamic Application Security Testing"])


_BLOCKED_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_scan_target(url: str) -> None:
    """Reject internal/private hosts to prevent SSRF."""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        hostname = parsed.hostname or ""
        try:
            addr = ipaddress.ip_address(hostname)
            for net in _BLOCKED_RANGES:
                if addr in net:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Scan target {hostname} is a private/internal address and cannot be scanned.",
                    )
        except ValueError:
            # hostname is a domain name, not an IP — allow it
            pass
    except HTTPException:
        raise
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("URL validation failed for %s: %s", url, exc)


# ── Models ────────────────────────────────────────────────────────────────────

class ScanTarget(BaseModel):
    url: str
    authType: Optional[str] = "None"


class DastFinding(BaseModel):
    id: str
    scanId: str
    title: str
    severity: str
    description: str
    remediation: str
    url: str


class DastScan(BaseModel):
    id: str
    targetUrl: str
    status: str
    riskScore: int
    startTime: str
    endTime: Optional[str] = None
    findingsCount: int
    findings: List[DastFinding] = []


# ── Security scanner ──────────────────────────────────────────────────────────

_SECURITY_HEADERS = {
    "Strict-Transport-Security": {
        "severity": "High",
        "title": "Missing HSTS Header",
        "description": "HTTP Strict-Transport-Security is not set. Browsers may fall back to plain HTTP, enabling MITM attacks.",
        "remediation": "Add: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload",
    },
    "Content-Security-Policy": {
        "severity": "High",
        "title": "Missing Content-Security-Policy Header",
        "description": "No CSP header found. Cross-site scripting (XSS) attacks are easier without a restrictive CSP.",
        "remediation": "Define a strict CSP policy, e.g.: default-src 'self'; script-src 'self'",
    },
    "X-Frame-Options": {
        "severity": "Medium",
        "title": "Missing X-Frame-Options Header",
        "description": "Page can be embedded in an iframe, enabling clickjacking attacks.",
        "remediation": "Add: X-Frame-Options: DENY or SAMEORIGIN",
    },
    "X-Content-Type-Options": {
        "severity": "Medium",
        "title": "Missing X-Content-Type-Options Header",
        "description": "MIME sniffing is not disabled. Browsers may misinterpret content types.",
        "remediation": "Add: X-Content-Type-Options: nosniff",
    },
    "Referrer-Policy": {
        "severity": "Low",
        "title": "Missing Referrer-Policy Header",
        "description": "Referrer information may leak to third parties.",
        "remediation": "Add: Referrer-Policy: strict-origin-when-cross-origin",
    },
    "Permissions-Policy": {
        "severity": "Low",
        "title": "Missing Permissions-Policy Header",
        "description": "Browser feature access (camera, microphone, geolocation) is not restricted.",
        "remediation": "Add: Permissions-Policy: geolocation=(), microphone=(), camera=()",
    },
}

_SENSITIVE_PATHS = [
    ("/.env",               "High",   "Environment File Exposed",      "/.env file may contain credentials and API keys."),
    ("/.git/HEAD",          "Critical","Git Repository Exposed",        "Source code history is publicly accessible."),
    ("/admin",              "Medium", "Admin Panel Exposed",            "Admin interface is publicly accessible without authentication check."),
    ("/api/docs",           "Low",    "API Documentation Exposed",      "Swagger/OpenAPI docs are publicly accessible."),
    ("/server-status",      "Medium", "Server Status Page Exposed",     "Apache server-status reveals internal metrics."),
    ("/actuator/health",    "Medium", "Spring Actuator Exposed",        "Spring Boot actuator endpoints may leak sensitive info."),
    ("/phpinfo.php",        "High",   "PHP Info Page Exposed",          "PHP configuration details are publicly accessible."),
    ("/backup.zip",         "Critical","Backup Archive Exposed",         "Backup files may contain source code or credentials."),
]

_SEVERITY_SCORE = {"Critical": 40, "High": 25, "Medium": 10, "Low": 3}


async def _run_scan(scan_id: str, target_url: str) -> None:
    """Perform HTTP security checks and update the scan record in MongoDB."""
    from database import get_database
    db = get_database()

    findings: List[dict] = []

    try:
        import aiohttp

        # Normalise URL
        base = target_url.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = "https://" + base

        timeout = aiohttp.ClientTimeout(total=10)
        connector = aiohttp.TCPConnector(ssl=_SSL_VERIFY)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:

            # 1. Fetch root — inspect headers
            try:
                async with session.get(base, allow_redirects=True) as resp:
                    headers = {k.title(): v for k, v in resp.headers.items()}

                    # HTTPS enforcement
                    if base.startswith("http://"):
                        findings.append({
                            "id": f"f-{uuid.uuid4().hex[:8]}",
                            "scanId": scan_id,
                            "title": "HTTP (Unencrypted) Connection",
                            "severity": "Critical",
                            "description": "Target is served over plain HTTP. All traffic is unencrypted.",
                            "remediation": "Redirect all HTTP traffic to HTTPS and obtain a valid TLS certificate.",
                            "url": base,
                        })

                    # Security headers
                    for header, meta in _SECURITY_HEADERS.items():
                        if header not in headers:
                            findings.append({
                                "id": f"f-{uuid.uuid4().hex[:8]}",
                                "scanId": scan_id,
                                "title": meta["title"],
                                "severity": meta["severity"],
                                "description": meta["description"],
                                "remediation": meta["remediation"],
                                "url": base,
                            })

                    # Server banner disclosure
                    server = headers.get("Server", "")
                    if server and any(kw in server.lower() for kw in ("apache", "nginx", "iis", "php")):
                        findings.append({
                            "id": f"f-{uuid.uuid4().hex[:8]}",
                            "scanId": scan_id,
                            "title": "Server Version Disclosure",
                            "severity": "Low",
                            "description": f"Server header reveals version: '{server}'. Attackers can target known CVEs.",
                            "remediation": "Suppress server version in web server configuration.",
                            "url": base,
                        })

                    # Cookie flags
                    for set_cookie in resp.headers.getall("Set-Cookie", []):
                        sc_lower = set_cookie.lower()
                        if "secure" not in sc_lower:
                            findings.append({
                                "id": f"f-{uuid.uuid4().hex[:8]}",
                                "scanId": scan_id,
                                "title": "Cookie Missing Secure Flag",
                                "severity": "Medium",
                                "description": "A cookie is set without the Secure flag and may be transmitted over HTTP.",
                                "remediation": "Add the Secure attribute to all cookies.",
                                "url": base,
                            })
                            break
                        if "httponly" not in sc_lower:
                            findings.append({
                                "id": f"f-{uuid.uuid4().hex[:8]}",
                                "scanId": scan_id,
                                "title": "Cookie Missing HttpOnly Flag",
                                "severity": "Medium",
                                "description": "A cookie is set without the HttpOnly flag, accessible via JavaScript.",
                                "remediation": "Add the HttpOnly attribute to session cookies.",
                                "url": base,
                            })
                            break

            except aiohttp.ClientError as e:
                findings.append({
                    "id": f"f-{uuid.uuid4().hex[:8]}",
                    "scanId": scan_id,
                    "title": "Target Unreachable",
                    "severity": "High",
                    "description": f"Could not connect to target: {e}",
                    "remediation": "Verify the target URL is reachable and the scanner has network access.",
                    "url": base,
                })

            # 2. Sensitive path enumeration
            for path, severity, title, description in _SENSITIVE_PATHS:
                try:
                    async with session.get(base + path, allow_redirects=False) as pr:
                        if pr.status in (200, 403):
                            findings.append({
                                "id": f"f-{uuid.uuid4().hex[:8]}",
                                "scanId": scan_id,
                                "title": title,
                                "severity": severity,
                                "description": f"HTTP {pr.status} at {path}: {description}",
                                "remediation": f"Restrict access to {path} or remove the file.",
                                "url": base + path,
                            })
                except Exception:
                    pass

    except ImportError:
        findings.append({
            "id": f"f-{uuid.uuid4().hex[:8]}",
            "scanId": scan_id,
            "title": "Scanner Dependency Missing",
            "severity": "Low",
            "description": "aiohttp is not installed; HTTP scanning is unavailable.",
            "remediation": "Install aiohttp: pip install aiohttp",
            "url": target_url,
        })
    except Exception as exc:
        findings.append({
            "id": f"f-{uuid.uuid4().hex[:8]}",
            "scanId": scan_id,
            "title": "Scan Error",
            "severity": "Medium",
            "description": f"Unexpected scanner error: {exc}",
            "remediation": "Check target URL and scanner network access.",
            "url": target_url,
        })

    risk_score = min(100, sum(_SEVERITY_SCORE.get(f["severity"], 0) for f in findings))

    await db.dast_scans.update_one(
        {"id": scan_id},
        {"$set": {
            "status": "Completed",
            "endTime": datetime.now(timezone.utc).isoformat(),
            "findings": findings,
            "findingsCount": len(findings),
            "riskScore": risk_score,
        }},
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/scans", response_model=List[DastScan])
async def get_scans(_current_user: TokenData = Depends(get_current_user)):
    from database import get_database
    db = get_database()
    scans = await db.dast_scans.find({}, {"_id": 0}).to_list(length=100)
    return [DastScan(**s) for s in scans]


@router.post("/scans", response_model=DastScan)
async def start_scan(target: ScanTarget, _current_user: TokenData = Depends(get_current_user)):
    _validate_scan_target(target.url)
    from database import get_database
    db = get_database()

    scan_id = f"scan-{uuid.uuid4().hex[:8]}"
    new_scan = {
        "id": scan_id,
        "targetUrl": target.url,
        "status": "Running",
        "riskScore": 0,
        "startTime": datetime.now(timezone.utc).isoformat(),
        "endTime": None,
        "findingsCount": 0,
        "findings": [],
    }
    await db.dast_scans.insert_one(new_scan.copy())

    # Run scanner in background — does not block the response
    asyncio.create_task(_run_scan(scan_id, target.url))

    new_scan.pop("_id", None)
    return DastScan(**new_scan)


@router.get("/scans/{scan_id}", response_model=DastScan)
async def get_scan_details(scan_id: str, _current_user: TokenData = Depends(get_current_user)):
    from database import get_database
    db = get_database()
    scan = await db.dast_scans.find_one({"id": scan_id}, {"_id": 0})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return DastScan(**scan)


@router.get("/findings", response_model=List[DastFinding])
async def get_all_findings(_current_user: TokenData = Depends(get_current_user)):
    from database import get_database
    db = get_database()
    scans = await db.dast_scans.find({}, {"_id": 0}).to_list(length=100)
    all_findings = []
    for scan in scans:
        all_findings.extend([DastFinding(**f) for f in scan.get("findings", [])])
    return all_findings
