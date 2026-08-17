"""Lightweight domain/subdomain scanner — passive DNS, TLS, port checks."""
import socket, ssl, json, uuid, logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

COMMON_PORTS = [80, 443, 8080, 8443, 8888]


async def scan_domain(db, tenant_id: str, domain: str) -> dict:
    subdomains = _passive_discover(domain)
    ports = _check_ports(subdomains[0] if subdomains else domain)
    tls = _check_tls(domain)
    dns = _get_dns(domain)
    result = {"domain": domain, "scanned_at": datetime.now(timezone.utc).isoformat(), "subdomains": subdomains, "open_ports": ports, "tls": tls, "dns": dns}
    await db._db.domain_scans.insert_one({"tenantId": tenant_id, **result})
    return result


async def schedule_domain(db, tenant_id: str, domain: str) -> dict:
    doc = {"id": f"sd-{uuid.uuid4().hex[:12]}", "tenantId": tenant_id, "domain": domain, "created_at": datetime.now(timezone.utc).isoformat(), "status": "active"}
    await db._db.scheduled_domains.insert_one(doc)
    return doc


async def list_scheduled(db, tenant_id: str) -> list:
    return await db._db.scheduled_domains.find({"tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(length=100)


def _passive_discover(domain: str) -> list:
    results = set()
    for prefix in ["www", "api", "mail", "admin", "app", "dev", "staging", "blog", "cdn", "docs", "support", "status", "portal", "login", "sso", "webmail", "remote", "vpn", "ftp", "git", "jenkins", "grafana", "prometheus"]:
        try:
            socket.getaddrinfo(f"{prefix}.{domain}", 80, socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            results.add(f"{prefix}.{domain}")
        except (socket.gaierror, OSError):
            pass
    if not results:
        try:
            socket.getaddrinfo(domain, 80)
            results.add(domain)
        except socket.gaierror:
            pass
    return sorted(results)


def _check_ports(host: str) -> dict:
    results = {}
    for port in COMMON_PORTS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            r = s.connect_ex((host, port))
            results[str(port)] = r == 0
            s.close()
        except OSError:
            results[str(port)] = False
    return results


def _check_tls(domain: str) -> dict:
    try:
        ctx = ssl.create_default_context()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((domain, 443))
        ss = ctx.wrap_socket(s, server_hostname=domain)
        cert = ss.getpeercert()
        s.close()
        return {
            "expiry": cert.get("notAfter", "unknown"),
            "issuer": dict(cert.get("issuer", [])).get("organizationName", "unknown"),
            "san": [v for _, v in cert.get("subjectAltName", [])],
        }
    except Exception as e:
        logger.debug("TLS check failed for %s: %s", domain, e)
        return {"expiry": None, "issuer": None, "san": [], "error": str(e)}


def _get_dns(domain: str) -> dict:
    results = {}
    for qtype in ["A", "AAAA", "MX", "TXT", "NS"]:
        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, qtype, lifetime=5)
            results[qtype] = [str(r) for r in answers]
        except ImportError:
            results[qtype] = ["dnspython not installed"]
        except Exception:
            results[qtype] = []
    return results
