"""Partner second wall (Phase 87, D-01 and D-04).

A partner token (``partner_admin`` or ``partner_viewer``) may use only the Partner portal
(``/api/partner``), its own sign-in, MFA and passkey routes, and the one shell read the sidebar needs
(``GET`` or ``HEAD /api/platform/features``). Every other ``/api/`` route is refused here, whatever the
handler does: many routes in non-enforced sidebar groups authenticate with ``get_current_user`` alone and
``tenants`` is exempt from the tenant wrapper, so an allowlist at the edge closes "through any route"
without auditing each handler. This is the second wall; the catalogue guards are the first.

D-04: a partner viewer may not write under ``/api/partner`` at all. D-02: the allowlist is one constant
for every partner and every customer, with no per-partner or per-customer widening.

HTTP only. Socket.IO and ``/api/stream/live`` deliver per connected tenant and a partner organization has
no emitters (assumption A-87-A5, flagged for a live check).
"""
import json
import logging
import re
from typing import Optional

import rbac_defaults
from tenant_middleware import _SAFE_METHODS, _bearer_role

logger = logging.getLogger(__name__)

_PARTNER_PREFIX = re.compile(r"^/api/partner(/|$)")
_SELF_SERVICE = re.compile(r"^/api/(auth|mfa|passkey)/")
_SHELL_READS = (re.compile(r"^/api/platform/features$"),)
_SHELL_READ_METHODS = frozenset({"GET", "HEAD"})

PARTNER_REFUSAL = "Partner accounts can use only the Partner portal"
VIEWER_REFUSAL = "Partner viewers have read-only access"


def partner_request_refusal(role: Optional[str], method: str, path: str) -> Optional[str]:
    """Why this request is refused to a partner role, or None when it may proceed.

    Roles that are not partner roles, and paths outside ``/api/``, are never refused here.
    """
    if not rbac_defaults.is_partner_role(role) or not path.startswith("/api/"):
        return None
    verb = (method or "").upper()
    if _PARTNER_PREFIX.match(path):
        viewer = rbac_defaults.canonical_key(rbac_defaults.normalize_role(role)) == rbac_defaults.PARTNER_VIEWER_KEY
        return VIEWER_REFUSAL if viewer and verb not in _SAFE_METHODS else None
    if _SELF_SERVICE.match(path):
        return None
    if verb in _SHELL_READ_METHODS and any(p.match(path) for p in _SHELL_READS):
        return None
    return PARTNER_REFUSAL


class PartnerScopeMiddleware:
    """Pure ASGI middleware applying partner_request_refusal to every HTTP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        role = _bearer_role(scope)
        reason = partner_request_refusal(role, scope.get("method", ""), scope.get("path", "")) if role else None
        if not reason:
            return await self.app(scope, receive, send)
        logger.info("Refused %s %s to partner role", scope.get("method"), scope.get("path"))
        body = json.dumps({"error": reason, "status_code": 403}).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
