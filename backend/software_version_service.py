"""
Software Version Service — Phase 11: Real-Time Patch Validation
Queries PyPI, npm registry, and Ubuntu Security Notices to resolve
the latest available version for each software package detected by agents.
Results are cached in MongoDB (TTL: 24 hours) to avoid API rate limits.
"""

import asyncio
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

# ─────────────────────────────────────────────────────────────────────────────
# Version helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_semver(version: str) -> tuple:
    """Parse a version string into a comparable tuple, ignoring non-numeric parts."""
    parts = re.split(r"[.\-+]", str(version))
    result = []
    for p in parts[:4]:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 4:
        result.append(0)
    return tuple(result)


def compare_versions(current: str, latest: str) -> str:
    """
    Compare current vs latest version.
    Returns: 'major', 'minor', 'patch', 'up-to-date', or 'unknown'
    """
    try:
        c = _parse_semver(current)
        l = _parse_semver(latest)
        if l <= c:
            return "up-to-date"
        if l[0] > c[0]:
            return "major"
        if l[1] > c[1]:
            return "minor"
        return "patch"
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# SoftwareVersionService
# ─────────────────────────────────────────────────────────────────────────────

class SoftwareVersionService:
    """
    Resolves the latest available version for packages via public registries.

    Supported package types:
    - pip   → PyPI JSON API
    - npm   → npm registry
    - apt   → Ubuntu security notices (best-effort)
    - os    → Returns OS kernel version from agent metadata
    """

    PYPI_URL = "https://pypi.org/pypi/{name}/json"
    NPM_URL  = "https://registry.npmjs.org/{name}/latest"
    CACHE_COLLECTION = "software_version_cache"
    CACHE_TTL_HOURS  = 24

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "OmniAgent-Platform/2.0"}
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Cache helpers ────────────────────────────────────────────────────────

    async def _get_from_cache(self, db, name: str, pkg_type: str) -> Optional[str]:
        """Return cached latest version if still fresh (< 24 hours)."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.CACHE_TTL_HOURS)
            doc = await db[self.CACHE_COLLECTION].find_one(
                {"name": name, "pkg_type": pkg_type, "updated_at": {"$gt": cutoff.isoformat()}}
            )
            if doc:
                return doc.get("latest_version")
        except Exception:
            pass
        return None

    async def _save_to_cache(self, db, name: str, pkg_type: str, latest_version: str):
        """Upsert a version result into the cache collection."""
        try:
            await db[self.CACHE_COLLECTION].update_one(
                {"name": name, "pkg_type": pkg_type},
                {"$set": {
                    "latest_version": latest_version,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
        except Exception:
            pass

    # ── Registry lookups ──────────────────────────────────────────────────────

    async def _fetch_pypi_latest(self, name: str) -> Optional[str]:
        """Fetch latest stable version from PyPI."""
        try:
            session = await self._get_session()
            url = self.PYPI_URL.format(name=name.lower())
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("info", {}).get("version")
        except Exception as e:
            print(f"[SoftwareVersionService] PyPI lookup failed for '{name}': {e}")
        return None

    async def _fetch_npm_latest(self, name: str) -> Optional[str]:
        """Fetch latest version from npm registry."""
        try:
            session = await self._get_session()
            url = self.NPM_URL.format(name=name.lower())
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("version")
        except Exception as e:
            print(f"[SoftwareVersionService] npm lookup failed for '{name}': {e}")
        return None

    async def _fetch_apt_latest(self, name: str) -> Optional[str]:
        """
        For apt packages, we query the Ubuntu Packages API.
        Falls back to None if unavailable (offline agents still show current).
        """
        try:
            session = await self._get_session()
            url = f"https://packages.ubuntu.com/search?keywords={name}&searchon=names&suite=noble&section=all"
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # Parse version from HTML response
                    match = re.search(r'<strong>([^<]+)</strong>\s*\(([^)]+)\)', text)
                    if match:
                        return match.group(2).split("-")[0]  # strip epoch/revision
        except Exception:
            pass
        return None

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_latest_version(self, name: str, pkg_type: str, db=None) -> Optional[str]:
        """
        Resolve the latest available version for a package.
        Uses cache if available, otherwise queries the registry.
        """
        if db:
            cached = await self._get_from_cache(db, name, pkg_type)
            if cached:
                return cached

        latest = None
        if pkg_type == "pip":
            latest = await self._fetch_pypi_latest(name)
        elif pkg_type == "npm":
            latest = await self._fetch_npm_latest(name)
        elif pkg_type in ("apt", "deb"):
            latest = await self._fetch_apt_latest(name)
        # For 'os', 'winget', 'windows_update' — version comes from agent itself

        if latest and db:
            await self._save_to_cache(db, name, pkg_type, latest)

        return latest

    async def bulk_check(
        self,
        packages: List[Dict[str, Any]],
        db=None,
        concurrency: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Enrich a list of package dicts with `latest_version` and `update_status`.

        Each package dict should have at minimum:
          { "name": str, "current_version": str, "pkg_type": str }

        Returns same list with added fields:
          latest_version, update_status ('major'|'minor'|'patch'|'up-to-date'|'unknown')
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def enrich_one(pkg: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                name     = pkg.get("name", "")
                current  = pkg.get("current_version", pkg.get("currentVersion", ""))
                pkg_type = pkg.get("pkg_type", pkg.get("type", "pip")).lower()

                latest = await self.get_latest_version(name, pkg_type, db)

                result = {**pkg}
                result["latest_version"] = latest or current
                result["update_status"]  = compare_versions(current, latest) if latest else "unknown"
                result["is_outdated"]    = result["update_status"] not in ("up-to-date", "unknown")
                return result

        tasks = [enrich_one(pkg) for pkg in packages]
        return await asyncio.gather(*tasks)

    async def get_outdated_packages(
        self,
        packages: List[Dict[str, Any]],
        db=None
    ) -> List[Dict[str, Any]]:
        """Return only packages where a newer version is available."""
        enriched = await self.bulk_check(packages, db)
        return [p for p in enriched if p.get("is_outdated")]


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_version_service: Optional[SoftwareVersionService] = None


def get_version_service() -> SoftwareVersionService:
    global _version_service
    if _version_service is None:
        _version_service = SoftwareVersionService()
    return _version_service
