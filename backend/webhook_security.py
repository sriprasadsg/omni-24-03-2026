"""Shared SSRF guard for outbound webhook URLs.

Previously duplicated only in webhook_endpoints.py, and only checked at
registration time (never re-checked on update, never re-checked
immediately before dispatch). ticket_webhook_service.py had no check at
all. See the 2026-08-25 audit's SSRF findings.
"""
import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_webhook_url(url: str) -> bool:
    """Reject webhook URLs that resolve to private/internal addresses (SSRF guard).

    Note: this resolves DNS once, at validation time — it does not pin the
    connection to the validated IP, so a DNS-rebinding attacker who controls
    the target hostname could still change its resolution between this check
    and the actual outbound request. Re-validating immediately before every
    dispatch (as both callers of this function now do, not just at
    registration) substantially narrows that window without requiring a
    custom connection-pinning HTTP transport.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
        return True
    except Exception:
        return False
