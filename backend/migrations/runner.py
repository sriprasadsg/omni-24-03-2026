"""
Simple MongoDB migration runner.

Migrations are Python modules in this package named NNN_description.py.
Each must expose:
  - VERSION: str  (e.g. "001")
  - DESCRIPTION: str
  - async def up(db) -> None   # apply migration
  - async def down(db) -> None # (optional) rollback

The runner tracks applied migrations in the `_migrations` collection.
"""
import importlib
import logging
import pkgutil
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATION_RE = re.compile(r"^(\d{3})_.+$")


async def run_migrations(db) -> None:
    """Apply all pending migrations in version order."""
    applied = await _get_applied(db)
    pending = _discover_pending(applied)

    if not pending:
        logger.info("migrations: all up to date (%d applied)", len(applied))
        return

    for version, module_name in pending:
        mod = importlib.import_module(f"migrations.{module_name}")
        logger.info("migrations: applying %s — %s", version, getattr(mod, "DESCRIPTION", ""))
        await mod.up(db)
        await db["_migrations"].insert_one({
            "version": version,
            "module": module_name,
            "appliedAt": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("migrations: %s applied successfully", version)


async def _get_applied(db) -> set[str]:
    docs = await db["_migrations"].find({}, {"version": 1}).to_list(length=1000)
    return {d["version"] for d in docs}


def _discover_pending(applied: set[str]) -> list[tuple[str, str]]:
    here = Path(__file__).parent
    pending = []
    for _, name, _ in pkgutil.iter_modules([str(here)]):
        m = _MIGRATION_RE.match(name)
        if m and m.group(1) not in applied:
            pending.append((m.group(1), name))
    return sorted(pending)
