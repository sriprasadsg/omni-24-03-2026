"""
SSRF guard for outbound webhook delivery URLs (webhook/Slack/Teams channels).
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


def _is_disallowed_ip(ip_str: str) -> bool:
    """Return True for loopback/private/link-local/reserved/multicast addresses (SSRF surface)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparsable — fail closed
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


async def validate_webhook_url(url: str) -> None:
    """Raise ValueError unless url is https:// and resolves only to public addresses.

    Guards against SSRF via webhook/Slack/Teams delivery URLs pointed at internal
    services (cloud metadata endpoints, internal admin APIs, loopback, etc).
    """
    if not url:
        raise ValueError("Webhook URL must not be empty")
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise ValueError(f"Webhook URL must use https:// (got {parsed.scheme or 'no scheme'!r})")
    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL must include a hostname")
    try:
        ipaddress.ip_address(host)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False
    if is_literal_ip:
        if _is_disallowed_ip(host):
            raise ValueError(f"Webhook URL resolves to a disallowed address: {host}")
        return
    loop = asyncio.get_event_loop()
    try:
        infos = await loop.run_in_executor(None, socket.getaddrinfo, host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Webhook URL hostname could not be resolved: {host}") from exc
    for info in infos:
        addr = info[4][0]
        if _is_disallowed_ip(addr):
            raise ValueError(f"Webhook URL hostname '{host}' resolves to a disallowed address: {addr}")
