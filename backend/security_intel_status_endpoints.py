"""
Security Intelligence Connector Status & Configuration API

Endpoints:
  GET  /api/security-intel/status         — live connectivity + data stats for all providers
  POST /api/security-intel/config         — save API key for a provider
  POST /api/security-intel/test/{p}       — live ping test
  POST /api/security-intel/sync/{p}       — trigger background data sync
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import Optional

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from authentication_service import get_current_user
from database import get_database
from rate_limiter import limiter

router = APIRouter(prefix="/api/security-intel", tags=["Security Intelligence"])
logger = logging.getLogger(__name__)

_PROVIDERS_WITH_KEYS = ("virustotal", "nvd")


class ConfigUpdate(BaseModel):
    provider: str
    api_key: str


async def _vt_status(db, env_key: str) -> dict:
    setting = await db._db.security_intel_config.find_one({"provider": "virustotal"})
    api_key = (setting or {}).get("api_key") or env_key
    configured = bool(api_key)
    if not configured:
        return {"status": "unconfigured", "message": "API key not set"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8",
                headers={"x-apikey": api_key},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status == 200:
                    return {"status": "connected", "message": "Connected successfully"}
                if r.status == 401:
                    return {"status": "error", "message": "Invalid API key (401)"}
                if r.status == 429:
                    return {"status": "connected", "message": "Connected — quota reached (429)"}
                return {"status": "error", "message": f"API returned HTTP {r.status}"}
    except Exception as exc:
        return {"status": "error", "message": f"Connection failed: {str(exc)[:80]}"}


@router.get("/status")
@limiter.limit("30/minute")
async def get_intel_status(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
):
    db = get_database()
    vt_env_key = os.getenv("VIRUSTOTAL_API_KEY", "")
    nvd_env_key = os.getenv("NVD_API_KEY", "")

    vt_setting  = await db._db.security_intel_config.find_one({"provider": "virustotal"})
    nvd_setting = await db._db.security_intel_config.find_one({"provider": "nvd"})

    vt_key  = (vt_setting  or {}).get("api_key") or vt_env_key
    nvd_key = (nvd_setting or {}).get("api_key") or nvd_env_key

    # Counts
    nvd_count = await db._db.patches.count_documents({"source": "nvd"})
    osv_count = await db._db.patches.count_documents({"source": "osv"})

    vt_result = await _vt_status(db, vt_env_key)

    def _hint(key: str) -> Optional[str]:
        if key and len(key) > 12:
            return f"{key[:8]}···{key[-4:]}"
        return None

    connectors = [
        {
            "provider":     "virustotal",
            "name":         "VirusTotal",
            "category":     "Threat Intelligence",
            "description":  "Scan IPs, domains, URLs, and file hashes against 70+ antivirus engines and threat intel feeds.",
            "status":       vt_result["status"],
            "message":      vt_result["message"],
            "configured":   bool(vt_key),
            "api_key_hint": _hint(vt_key),
            "configured_at": (vt_setting or {}).get("configured_at"),
            "record_count": None,
            "last_sync":    None,
            "docs_url":     "https://developers.virustotal.com/",
            "free_tier":    "4 lookups/min · 500/day",
            "requires_key": True,
            "key_env_var":  "VIRUSTOTAL_API_KEY",
        },
        {
            "provider":     "nvd",
            "name":         "NIST NVD",
            "category":     "Vulnerability Database",
            "description":  "National Vulnerability Database — CVE data with CVSS v3 scores, CWE mappings, and EPSS exploitation probability.",
            "status":       "connected" if nvd_count > 0 else ("configured" if nvd_key else "unconfigured"),
            "message":      f"{nvd_count:,} CVEs synced" if nvd_count > 0 else (
                            "API key set — run first sync to load data" if nvd_key else
                            "No API key (public: 5 req/30s). Add key for 50 req/30s."
                            ),
            "configured":   True,
            "api_key_hint": _hint(nvd_key),
            "configured_at": (nvd_setting or {}).get("configured_at"),
            "record_count": nvd_count,
            "last_sync":    (nvd_setting or {}).get("last_sync"),
            "docs_url":     "https://nvd.nist.gov/developers",
            "free_tier":    "Free · API key optional (improves rate limits)",
            "requires_key": False,
            "key_env_var":  "NVD_API_KEY",
        },
        {
            "provider":     "osv",
            "name":         "OSV.dev",
            "category":     "Vulnerability Database",
            "description":  "Open Source Vulnerability database — package-level CVEs across npm, PyPI, Go, Maven, Cargo, and more.",
            "status":       "connected" if osv_count > 0 else "unconfigured",
            "message":      f"{osv_count:,} vulnerabilities synced" if osv_count > 0 else "No data yet — trigger sync to load",
            "configured":   True,
            "api_key_hint": None,
            "configured_at": None,
            "record_count": osv_count,
            "last_sync":    (await db._db.security_intel_config.find_one({"provider": "osv"}) or {}).get("last_sync"),
            "docs_url":     "https://osv.dev/docs/",
            "free_tier":    "Free · No API key required",
            "requires_key": False,
            "key_env_var":  None,
        },
        {
            "provider":     "epss",
            "name":         "FIRST EPSS",
            "category":     "Exploit Intelligence",
            "description":  "Exploit Prediction Scoring System — probability that a CVE will be exploited in the wild within 30 days.",
            "status":       "connected" if nvd_count > 0 else "unconfigured",
            "message":      "Scores attached to every NVD CVE" if nvd_count > 0 else "Enabled automatically when NVD syncs",
            "configured":   True,
            "api_key_hint": None,
            "configured_at": None,
            "record_count": nvd_count,
            "last_sync":    (nvd_setting or {}).get("last_sync"),
            "docs_url":     "https://www.first.org/epss/api",
            "free_tier":    "Free · No API key required",
            "requires_key": False,
            "key_env_var":  None,
        },
    ]

    connected = sum(1 for c in connectors if c["status"] == "connected")
    return {
        "connectors":  connectors,
        "total":       len(connectors),
        "connected":   connected,
        "unconfigured": sum(1 for c in connectors if c["status"] == "unconfigured"),
        "errors":      sum(1 for c in connectors if c["status"] == "error"),
    }


@router.post("/config")
@limiter.limit("10/minute")
async def save_intel_config(
    request: Request,
    response: Response,
    body: ConfigUpdate,
    current_user=Depends(get_current_user),
):
    if body.provider not in _PROVIDERS_WITH_KEYS:
        raise HTTPException(status_code=400, detail=f"'{body.provider}' does not accept API key config via this endpoint.")
    if not body.api_key or len(body.api_key.strip()) < 8:
        raise HTTPException(status_code=400, detail="API key is too short (minimum 8 characters).")

    db = get_database()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    actor = getattr(current_user, "username", str(current_user))

    await db._db.security_intel_config.update_one(
        {"provider": body.provider},
        {"$set": {
            "provider":       body.provider,
            "api_key":        body.api_key.strip(),
            "configured_at":  now,
            "configured_by":  actor,
        }},
        upsert=True,
    )

    env_map = {"virustotal": "VIRUSTOTAL_API_KEY", "nvd": "NVD_API_KEY"}
    os.environ[env_map[body.provider]] = body.api_key.strip()

    return {"success": True, "message": f"{body.provider} API key saved successfully"}


@router.post("/push-to-agents")
@limiter.limit("5/minute")
async def push_config_to_agents(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
):
    """
    Distribute the server-side VirusTotal API key to all registered agents.

    Stores the key in each agent's capabilityConfig.capabilitySettings.threat_intel
    so the threat_intel capability can use it without a separate env var on the endpoint.
    The key is delivered at the agent's next configuration refresh (each poll cycle).
    """
    db = get_database()
    setting = await db._db.security_intel_config.find_one({"provider": "virustotal"})
    api_key = (setting or {}).get("api_key") or os.getenv("VIRUSTOTAL_API_KEY", "")

    if not api_key:
        raise HTTPException(status_code=400, detail="No VirusTotal API key is configured on the server.")

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    actor = getattr(current_user, "username", str(current_user))

    result = await db._db.agents.update_many(
        {"status": {"$in": ["Online", "online", "Active", "active", "Idle", "idle"]}},
        {"$set": {
            "capabilityConfig.capabilitySettings.threat_intel.virustotal_api_key": api_key,
            "capabilityConfig.capabilitySettings.threat_intel.pushed_at": now,
            "capabilityConfig.capabilitySettings.threat_intel.pushed_by": actor,
        }},
    )

    # Also update offline agents so they get it on reconnect
    result_all = await db._db.agents.update_many(
        {},
        {"$set": {
            "capabilityConfig.capabilitySettings.threat_intel.virustotal_api_key": api_key,
            "capabilityConfig.capabilitySettings.threat_intel.pushed_at": now,
            "capabilityConfig.capabilitySettings.threat_intel.pushed_by": actor,
        }},
    )

    total = result_all.matched_count
    return {
        "success": True,
        "message": f"VirusTotal key distributed to {total} agent(s)",
        "agents_updated": total,
        "pushed_at": now,
        "key_hint": f"{api_key[:8]}···{api_key[-4:]}" if len(api_key) > 12 else None,
    }


@router.post("/test/{provider}")
@limiter.limit("5/minute")
async def test_intel_connection(
    request: Request,
    response: Response,
    provider: str,
    current_user=Depends(get_current_user),
):
    db = get_database()
    setting = await db._db.security_intel_config.find_one({"provider": provider})

    if provider == "virustotal":
        api_key = (setting or {}).get("api_key") or os.getenv("VIRUSTOTAL_API_KEY", "")
        if not api_key:
            return {"success": False, "message": "No API key configured for VirusTotal"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://www.virustotal.com/api/v3/ip_addresses/8.8.8.8",
                    headers={"x-apikey": api_key},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        stats = d.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                        return {"success": True, "message": "Connected to VirusTotal",
                                "detail": f"Test lookup: {stats.get('malicious', 0)} malicious / {stats.get('harmless', 0)} harmless for 8.8.8.8"}
                    if r.status == 401:
                        return {"success": False, "message": "Invalid API key (401 Unauthorized)"}
                    if r.status == 429:
                        return {"success": True, "message": "API key valid (rate limit reached)"}
                    return {"success": False, "message": f"Unexpected HTTP {r.status}"}
        except Exception as e:
            return {"success": False, "message": "Connection failed", "detail": str(e)[:120]}

    elif provider == "nvd":
        nvd_key = (setting or {}).get("api_key") or os.getenv("NVD_API_KEY", "")
        headers = {"apiKey": nvd_key} if nvd_key else {}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=1",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        total = d.get("totalResults", 0)
                        mode = "authenticated" if nvd_key else "unauthenticated"
                        return {"success": True, "message": f"Connected to NIST NVD ({mode})",
                                "detail": f"NVD contains {total:,} total CVEs"}
                    return {"success": False, "message": f"NVD returned HTTP {r.status}"}
        except Exception as e:
            return {"success": False, "message": "Connection failed", "detail": str(e)[:120]}

    elif provider == "osv":
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.osv.dev/v1/vulns?limit=1",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        return {"success": True, "message": "Connected to OSV.dev", "detail": "Public API is reachable"}
                    return {"success": False, "message": f"OSV returned HTTP {r.status}"}
        except Exception as e:
            return {"success": False, "message": "Connection failed", "detail": str(e)[:120]}

    elif provider == "epss":
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.first.org/data/v1/epss?cve=CVE-2021-44228",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        score = (d.get("data") or [{}])[0].get("epss", "n/a")
                        return {"success": True, "message": "Connected to FIRST EPSS",
                                "detail": f"Log4Shell EPSS score: {score}"}
                    return {"success": False, "message": f"EPSS returned HTTP {r.status}"}
        except Exception as e:
            return {"success": False, "message": "Connection failed", "detail": str(e)[:120]}

    raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")


@router.post("/sync/{provider}")
@limiter.limit("2/minute")
async def trigger_sync(
    request: Request,
    response: Response,
    provider: str,
    current_user=Depends(get_current_user),
):
    db = get_database()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if provider == "nvd":
        try:
            from nvd_sync import sync_nvd_cves
            asyncio.create_task(sync_nvd_cves(db._db))
            await db._db.security_intel_config.update_one(
                {"provider": "nvd"}, {"$set": {"last_sync": now}}, upsert=True
            )
            return {"success": True, "message": "NVD sync started in background — may take 1-2 minutes"}
        except Exception as e:
            return {"success": False, "message": f"Failed to start NVD sync: {e}"}

    elif provider == "osv":
        try:
            from osv_sync import sync_osv_vulns
            asyncio.create_task(sync_osv_vulns(db._db))
            await db._db.security_intel_config.update_one(
                {"provider": "osv"}, {"$set": {"last_sync": now}}, upsert=True
            )
            return {"success": True, "message": "OSV sync started in background — may take 1-2 minutes"}
        except Exception as e:
            return {"success": False, "message": f"Failed to start OSV sync: {e}"}

    raise HTTPException(status_code=400, detail=f"Manual sync not supported for '{provider}'")
