"""
Ticket Reporter Capability
Raises internal platform tickets automatically when the agent detects issues
(critical vulnerabilities, security events, failed compliance controls, etc.).

Primary path: writes directly to MongoDB — no HTTP round-trip, works even
when the backend is restarting.
Fallback path: POST /api/tickets (used if MongoDB is unavailable).
"""
import logging
import os
import platform
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseCapability

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_endpoint_info() -> Dict[str, Any]:
    """Gather basic endpoint context to attach to every ticket."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    try:
        ip_address = socket.gethostbyname(hostname)
    except Exception:
        ip_address = "unknown"
    username = (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "unknown"
    )
    return {
        "hostname":   hostname,
        "ip_address": ip_address,
        "os_name":    platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "machine":    platform.machine(),
        "username":   username,
    }


class TicketReporterCapability(BaseCapability):
    """Auto-raises internal tickets, writing directly to MongoDB (HTTP fallback)."""

    # Lazy-initialised pymongo client shared across all raise_* calls
    _mongo_client = None
    _mongo_db = None

    @property
    def capability_id(self) -> str:
        return "ticket_reporter"

    @property
    def capability_name(self) -> str:
        return "Ticket Reporter"

    def collect(self) -> Dict[str, Any]:
        return {"status": "passive", "info": "Call raise_ticket() directly to create tickets."}

    # ── MongoDB connection (lazy, synchronous pymongo) ─────────────────────────

    def _get_mongo_collection(self):
        """Return the synchronous pymongo tickets collection, or None on error."""
        if TicketReporterCapability._mongo_db is not None:
            return TicketReporterCapability._mongo_db["tickets"]

        try:
            from pymongo import MongoClient

            mongo_url = (
                self.config.get("mongodb_url")
                or os.environ.get("MONGODB_URL")
                or "mongodb://localhost:27017"
            )
            db_name = (
                self.config.get("database_name")
                or os.environ.get("DATABASE_NAME")
                or "omni_agent_platform"
            )

            client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
            # Ping to verify connection before caching
            client.admin.command("ping")
            TicketReporterCapability._mongo_client = client
            TicketReporterCapability._mongo_db = client[db_name]
            logger.info("[TicketReporter] MongoDB connection established (%s / %s)", mongo_url, db_name)
            return TicketReporterCapability._mongo_db["tickets"]
        except Exception as exc:
            logger.warning("[TicketReporter] MongoDB unavailable (%s) — will use HTTP fallback", exc)
            return None

    # ── Direct MongoDB write ───────────────────────────────────────────────────

    def _write_ticket_direct(
        self,
        title: str,
        description: str,
        ticket_type: str,
        priority: str,
        assignee: str,
        tags: List[str],
        endpoint_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Insert ticket document directly into MongoDB tickets collection."""
        col = self._get_mongo_collection()
        if col is None:
            return None

        try:
            count = col.count_documents({})
            tenant_id = (
                self.config.get("tenant_id")
                or os.environ.get("TENANT_ID")
                or ""
            )
            ticket = {
                "id": str(uuid.uuid4()),
                "ticket_number": f"TKT-{count + 1:04d}",
                "title": title,
                "description": description,
                "type": ticket_type,
                "priority": priority,
                "status": "open",
                "assignee": assignee,
                "reporter": "agent",
                "tenantId": tenant_id,
                "tags": tags,
                "endpoint_info": endpoint_info or _collect_endpoint_info(),
                "linked_assets": [],
                "linked_vulnerabilities": [],
                "comments": [],
                "created_at": _now(),
                "updated_at": _now(),
            }
            col.insert_one(ticket)
            ticket.pop("_id", None)
            logger.info(
                "[TicketReporter] Ticket created (direct): %s — %s",
                ticket["ticket_number"], title,
            )
            return ticket
        except Exception as exc:
            logger.error("[TicketReporter] Direct write failed: %s", exc)
            # Reset cached client so next call retries
            TicketReporterCapability._mongo_client = None
            TicketReporterCapability._mongo_db = None
            return None

    # ── HTTP fallback ──────────────────────────────────────────────────────────

    def _write_ticket_http(
        self,
        title: str,
        description: str,
        ticket_type: str,
        priority: str,
        assignee: str,
        tags: List[str],
        endpoint_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """POST ticket to backend API — used only when MongoDB is unavailable."""
        try:
            import requests

            base_url = self.config.get("api_base_url", "http://localhost:5000").rstrip("/")
            agent_token = self.config.get("agent_token", "")
            headers = (
                {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"}
                if agent_token
                else {"Content-Type": "application/json"}
            )
            payload = {
                "title": title,
                "description": description,
                "type": ticket_type,
                "priority": priority,
                "assignee": assignee,
                "tags": tags,
                "endpoint_info": endpoint_info or _collect_endpoint_info(),
            }
            resp = requests.post(
                f"{base_url}/api/tickets",
                json=payload,
                headers=headers,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                ticket = resp.json()
                logger.info(
                    "[TicketReporter] Ticket created (HTTP): %s — %s",
                    ticket.get("ticket_number"), title,
                )
                return ticket
            else:
                logger.warning(
                    "[TicketReporter] HTTP ticket failed (%s): %s",
                    resp.status_code, resp.text[:200],
                )
                return None
        except Exception as exc:
            logger.error("[TicketReporter] HTTP fallback error: %s", exc)
            return None

    # ── Public API ─────────────────────────────────────────────────────────────

    def raise_ticket(
        self,
        title: str,
        description: str = "",
        ticket_type: str = "task",
        priority: str = "medium",
        assignee: str = "",
        tags: Optional[List[str]] = None,
        endpoint_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a ticket. Tries MongoDB directly first; falls back to HTTP API.
        Returns the created ticket dict, or None on failure.
        """
        resolved_tags = tags or ["agent-raised"]
        resolved_info = endpoint_info or _collect_endpoint_info()

        ticket = self._write_ticket_direct(title, description, ticket_type, priority, assignee, resolved_tags, resolved_info)
        if ticket is not None:
            return ticket

        logger.info("[TicketReporter] Retrying via HTTP fallback...")
        return self._write_ticket_http(title, description, ticket_type, priority, assignee, resolved_tags, resolved_info)

    def raise_vulnerability_ticket(self, vuln: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convenience wrapper for vulnerability findings."""
        severity = vuln.get("severity", "medium").lower()
        priority_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
        return self.raise_ticket(
            title=f"Vulnerability: {vuln.get('name', 'Unknown')} on {vuln.get('asset', 'unknown asset')}",
            description=(
                f"CVE: {vuln.get('cve', 'N/A')}\n"
                f"Severity: {vuln.get('severity', 'N/A')}\n"
                f"Asset: {vuln.get('asset', 'N/A')}\n"
                f"Description: {vuln.get('description', 'No details available.')}"
            ),
            ticket_type="security",
            priority=priority_map.get(severity, "medium"),
            tags=["vulnerability", "agent-raised", f"severity:{severity}"],
        )

    def raise_compliance_ticket(self, control: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convenience wrapper for failed compliance controls."""
        return self.raise_ticket(
            title=f"Compliance Failure: {control.get('control_id', 'Unknown')} — {control.get('name', '')}",
            description=(
                f"Framework: {control.get('framework', 'N/A')}\n"
                f"Control: {control.get('control_id', 'N/A')}\n"
                f"Requirement: {control.get('description', 'N/A')}\n"
                f"Finding: {control.get('finding', 'Control did not pass.')}"
            ),
            ticket_type="incident",
            priority="high",
            tags=["compliance", "agent-raised"],
        )

    def raise_security_event_ticket(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convenience wrapper for security events / alerts."""
        severity = event.get("severity", "medium").lower()
        priority_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
        return self.raise_ticket(
            title=f"Security Event: {event.get('title', event.get('type', 'Unknown Event'))}",
            description=(
                f"Type: {event.get('type', 'N/A')}\n"
                f"Severity: {event.get('severity', 'N/A')}\n"
                f"Source: {event.get('source', 'N/A')}\n"
                f"Details: {event.get('description', event.get('message', 'No details.'))}"
            ),
            ticket_type="security",
            priority=priority_map.get(severity, "medium"),
            tags=["security-event", "agent-raised", f"severity:{severity}"],
        )
