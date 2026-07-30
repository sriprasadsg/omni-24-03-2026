"""
Agent Security Feed Service — Phase 50 (NSCAN-02/03)

Builds a self-contained SQLite feed bundle (malware hash signatures, YARA
rules, URL/IP threat-intel feeds + a manifest) and signs it with an ed25519
detached signature. The agent fetches this via GET /api/agents/security/
feed-bundle (agent_security_feed_endpoints), verifies the signature with an
embedded public key, and scans offline against it — no live lookup (NSCAN-02).

Signing key: the ed25519 private key is generated once and persisted to a
gitignored local path (AGENT_FEED_SIGNING_KEY_PATH), NEVER committed and NEVER
returned by any endpoint. Only the 32-byte public key is exported (embedded in
the agent). Seed data is vendored/local — no network at build time. The only
"malware" shipped is the standard EICAR test hash (not real malware).
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# EICAR test-file SHA256 (safe standard AV test artifact — NOT real malware).
_EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
_EICAR_MD5 = "44d88612fea8a8f36de82e1278abb02f"

# --- Vendored seed data (local, sample/documented; grow over time) -----------
# hash_sigs: (sha256, md5, verdict, name)
_HASH_SIGS: List[Tuple[str, str, str, str]] = [
    (_EICAR_SHA256, _EICAR_MD5, "Malicious", "EICAR-Test-File"),
    ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "d41d8cd98f00b204e9800998ecf8427e", "Suspicious", "Sample-EmptyFile-Marker"),
]
# yara_rules: (name, severity, source)
_YARA_RULES: List[Tuple[str, str, str]] = [
    ("Sample_Eicar_String", "high",
     'rule Sample_Eicar_String { strings: $e = "EICAR-STANDARD-ANTIVIRUS-TEST-FILE" condition: $e }'),
]
# url_feed: (pattern, kind, verdict)  kind in {url, domain}
_URL_FEED: List[Tuple[str, str, str]] = [
    ("malware.example.test", "domain", "Malicious"),
    ("http://c2.example.test/gate.php", "url", "Malicious"),
]
# ip_feed: (cidr, verdict)  — sample documented C2 ranges
_IP_FEED: List[Tuple[str, str]] = [
    ("198.51.100.0/24", "Malicious"),
    ("203.0.113.66/32", "Malicious"),
]
# cve_feed (VULN-02): (package, version_range, cve_id, cvss, severity,
# remediation_hint, playbook_ref). Seeded from the agent's former hardcoded
# CVE_PATTERNS, enriched; grow with a vendored NVD subset over time.
_CVE_FEED: List[Tuple[str, str, str, float, str, str, str]] = [
    ("openssl", "<1.0.2", "CVE-2022-0778", 7.5, "HIGH", "Upgrade OpenSSL to >=1.1.1n", "patch_package"),
    ("openssl", "1.1.1", "CVE-2023-0286", 7.4, "HIGH", "Upgrade OpenSSL to >=1.1.1t", "patch_package"),
    ("log4j", "2.0-2.14", "CVE-2021-44228", 10.0, "CRITICAL", "Upgrade log4j to >=2.17.1", "patch_package"),
    ("log4j", "2.15", "CVE-2021-45046", 9.0, "CRITICAL", "Upgrade log4j to >=2.17.1", "patch_package"),
    ("python", "<3.0", "CVE-2022-45061", 7.5, "MEDIUM", "Upgrade Python to a supported 3.x", "patch_package"),
    ("putty", "<0.81", "CVE-2024-31497", 7.4, "HIGH", "Upgrade PuTTY to >=0.81", "patch_package"),
    ("7-zip", "21", "CVE-2022-29072", 7.8, "HIGH", "Upgrade 7-Zip to >=21.07", "patch_package"),
    ("winscp", "5", "CVE-2022-39369", 5.3, "MEDIUM", "Upgrade WinSCP to >=5.21.5", "patch_package"),
    ("notepad++", "7", "CVE-2023-40031", 7.8, "HIGH", "Upgrade Notepad++ to >=8.5.7", "patch_package"),
    ("zoom", "5.1", "CVE-2022-28762", 7.3, "HIGH", "Upgrade Zoom to the latest release", "patch_package"),
    ("vlc", "3.0", "CVE-2022-41325", 8.8, "HIGH", "Upgrade VLC to >=3.0.18", "patch_package"),
    ("apache", "2.4.49", "CVE-2021-41773", 7.5, "HIGH", "Upgrade Apache httpd to >=2.4.51", "patch_package"),
    ("sudo", "<1.9.5p2", "CVE-2021-3156", 7.8, "HIGH", "Upgrade sudo to >=1.9.5p2", "patch_package"),
    ("curl", "<7.87.0", "CVE-2022-42916", 6.5, "MEDIUM", "Upgrade curl to >=7.87.0", "patch_package"),
]


def _key_path() -> str:
    return os.getenv(
        "AGENT_FEED_SIGNING_KEY_PATH",
        os.path.join(_BACKEND_DIR, "data", "agent_feed_signing.key"),
    )


_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_or_create_keypair() -> Ed25519PrivateKey:
    path = _key_path()
    if os.path.exists(path):
        with open(path, "rb") as f:
            return Ed25519PrivateKey.from_private_bytes(f.read())
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Write 0600 so the private key is not world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes_raw())
    return key


def get_public_key() -> bytes:
    """The 32-byte ed25519 public key (embedded in the agent). Never the private key."""
    return _load_or_create_keypair().public_key().public_bytes_raw()


def sign_bundle(data: bytes) -> bytes:
    """Detached ed25519 signature over the bundle bytes."""
    return _load_or_create_keypair().sign(data)


def _seed_rows() -> Dict[str, Any]:
    """The full seed content — the version is derived from this (stable)."""
    return {
        "hash_sigs": _HASH_SIGS,
        "yara_rules": _YARA_RULES,
        "url_feed": _URL_FEED,
        "ip_feed": _IP_FEED,
        "cve_feed": _CVE_FEED,
    }


def bundle_version() -> str:
    """Content-derived version (stable for identical seed content)."""
    blob = json.dumps(_seed_rows(), sort_keys=True, default=list).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def build_bundle() -> bytes:
    """Build the signed-feed SQLite database and return its raw bytes."""
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE TABLE hash_sigs (sha256 TEXT, md5 TEXT, verdict TEXT, name TEXT)")
        con.execute("CREATE TABLE yara_rules (name TEXT, severity TEXT, source TEXT)")
        con.execute("CREATE TABLE url_feed (pattern TEXT, kind TEXT, verdict TEXT)")
        con.execute("CREATE TABLE ip_feed (cidr TEXT, verdict TEXT)")
        con.execute("CREATE TABLE cve_feed (package TEXT, version_range TEXT, cve_id TEXT, cvss REAL, severity TEXT, remediation_hint TEXT, playbook_ref TEXT)")
        con.execute("CREATE TABLE manifest (version TEXT, created_at TEXT)")
        con.executemany("INSERT INTO hash_sigs VALUES (?,?,?,?)", _HASH_SIGS)
        con.executemany("INSERT INTO yara_rules VALUES (?,?,?)", _YARA_RULES)
        con.executemany("INSERT INTO url_feed VALUES (?,?,?)", _URL_FEED)
        con.executemany("INSERT INTO ip_feed VALUES (?,?)", _IP_FEED)
        con.executemany("INSERT INTO cve_feed VALUES (?,?,?,?,?,?,?)", _CVE_FEED)
        con.execute(
            "INSERT INTO manifest VALUES (?,?)",
            (bundle_version(), datetime.now(timezone.utc).isoformat()),
        )
        con.commit()
        return bytes(con.serialize())  # SQLite file image (Python 3.11+)
    finally:
        con.close()
