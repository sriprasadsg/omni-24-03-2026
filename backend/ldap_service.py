"""LDAP/Active Directory integration service (ITAM-USR-03).

Provides:
 - LDAPConfig: configuration resolved from environment variables or an
   admin-saved MongoDB document (POST /api/admin/ldap/config).
 - LDAPConnectionManager: TLS/StartTLS-aware connection handling with a
   small bounded pool of reusable service-account connections, retry with
   backoff on transient failures, and single-use (never pooled) connections
   for interactive user credential binds.
 - LDAPAuthenticator: verifies a user's directory credentials by binding as
   that user (their password is never read/stored — the bind itself IS the
   verification). T-64-07.
 - LDAPUserSyncer: searches LDAP for users, maps directory attributes onto
   the `users` MongoDB collection shape, and upserts with `source="ldap"`
   (Pitfall 4 / T-64-12 — local password changes must be blocked for these
   users; enforced in user_endpoints.py / auth_password_reset_endpoints.py).
 - LDAPGroupMapper: maps LDAP group DNs to ITAM roles via an admin-managed
   `ldap_group_mappings` collection (T-64-09).
 - authenticate_ldap(): the full LDAP bind -> sync -> mint-JWT flow, reusing
   authentication_service.create_access_token/create_refresh_token rather
   than duplicating token-minting logic.

All LDAP wire operations are synchronous (ldap3 has no native asyncio
support); every call site that runs inside an async endpoint wraps the
synchronous call with asyncio.to_thread().
"""
import asyncio
import logging
import os
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from ldap3 import ALL, SUBTREE, Server, Connection, Tls
from ldap3.core.exceptions import (
    LDAPException,
    LDAPBindError,
    LDAPSocketOpenError,
    LDAPSocketReceiveError,
)
from ldap3.utils.conv import escape_filter_chars

from database import get_database

logger = logging.getLogger(__name__)


# ─── Exceptions ──────────────────────────────────────────────────────────────

class LDAPConfigError(Exception):
    """LDAP configuration is missing or invalid."""


class LDAPConnectionError(Exception):
    """The LDAP server could not be reached (network, TLS, timeout)."""


class LDAPAuthError(Exception):
    """An LDAP bind (credential check) failed."""


class LDAPSyncError(Exception):
    """User/group sync from LDAP failed after a successful bind."""


# ─── Config ──────────────────────────────────────────────────────────────────

@dataclass
class LDAPConfig:
    uri: str
    bind_dn: str
    bind_password: str
    user_base_dn: str
    group_base_dn: str = ""
    user_filter: str = "(objectClass=user)"
    group_filter: str = "(objectClass=group)"
    user_id_attr: str = "sAMAccountName"
    user_email_attr: str = "mail"
    user_name_attr: str = "displayName"
    group_member_attr: str = "member"
    tls_ca_cert: Optional[str] = None

    @classmethod
    def from_env(cls) -> "LDAPConfig":
        uri = os.getenv("LDAP_URI", "")
        bind_dn = os.getenv("LDAP_BIND_DN", "")
        user_base_dn = os.getenv("LDAP_USER_BASE_DN", "")
        if not uri or not bind_dn or not user_base_dn:
            raise LDAPConfigError(
                "LDAP is not configured: LDAP_URI, LDAP_BIND_DN, and "
                "LDAP_USER_BASE_DN are required (set env vars, or configure "
                "via POST /api/admin/ldap/config)."
            )
        return cls(
            uri=uri,
            bind_dn=bind_dn,
            bind_password=os.getenv("LDAP_BIND_PASSWORD", ""),
            user_base_dn=user_base_dn,
            group_base_dn=os.getenv("LDAP_GROUP_BASE_DN", ""),
            user_filter=os.getenv("LDAP_USER_FILTER", "(objectClass=user)"),
            group_filter=os.getenv("LDAP_GROUP_FILTER", "(objectClass=group)"),
            user_id_attr=os.getenv("LDAP_USER_ID_ATTR", "sAMAccountName"),
            user_email_attr=os.getenv("LDAP_USER_EMAIL_ATTR", "mail"),
            user_name_attr=os.getenv("LDAP_USER_NAME_ATTR", "displayName"),
            group_member_attr=os.getenv("LDAP_GROUP_MEMBER_ATTR", "member"),
            tls_ca_cert=os.getenv("LDAP_TLS_CA_CERT") or None,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "LDAPConfig":
        return cls(
            uri=d.get("uri", ""),
            bind_dn=d.get("bind_dn", ""),
            bind_password=d.get("bind_password", ""),
            user_base_dn=d.get("user_base_dn", ""),
            group_base_dn=d.get("group_base_dn") or "",
            user_filter=d.get("user_filter") or "(objectClass=user)",
            group_filter=d.get("group_filter") or "(objectClass=group)",
            user_id_attr=d.get("user_id_attr") or "sAMAccountName",
            user_email_attr=d.get("user_email_attr") or "mail",
            user_name_attr=d.get("user_name_attr") or "displayName",
            group_member_attr=d.get("group_member_attr") or "member",
            tls_ca_cert=d.get("tls_ca_cert") or None,
        )


async def get_ldap_config(tenant_id: Optional[str] = None) -> LDAPConfig:
    """Resolve LDAP config: an admin-saved MongoDB document takes precedence
    over environment variables, so operators can (re)configure LDAP at
    runtime via POST /api/admin/ldap/config without a redeploy.

    `tenant_id=None` looks up the platform-wide default config (the shape
    saved by a super-admin, and the one the unauthenticated /api/auth/ldap/login
    route uses, since there is no tenant context before a caller is
    authenticated). A tenant-scoped lookup that finds nothing falls back to
    the platform-wide default before finally falling back to env vars.
    """
    db = get_database()
    doc = await db.ldap_configs.find_one({"tenant_id": tenant_id})
    if not doc and tenant_id is not None:
        doc = await db.ldap_configs.find_one({"tenant_id": None})
    if doc:
        bind_password = doc.get("bind_password", "")
        if doc.get("bind_password_encrypted"):
            from encryption_service import get_encryption_service
            bind_password = get_encryption_service().decrypt(doc["bind_password_encrypted"])
        return LDAPConfig.from_dict({**doc, "bind_password": bind_password})
    return LDAPConfig.from_env()


def _user_search_filter(config: LDAPConfig, username: str) -> str:
    """Build an LDAP search filter for a username, escaping it per RFC 4515
    to prevent LDAP injection (T-64-11) — never interpolate raw user input
    into a filter string."""
    safe_username = escape_filter_chars(username)
    return f"(&{config.user_filter}({config.user_id_attr}={safe_username}))"


# ─── Connection management ───────────────────────────────────────────────────

class LDAPConnectionManager:
    """TLS/StartTLS-aware connection handling with:
     - a small bounded pool of reusable, service-account-bound connections
       (search/sync operations acquire/release from this pool instead of
       binding fresh every call), and
     - single-use connections for interactive user credential checks, which
       are never pooled and are unbound immediately after the check so a
       user's password is never held in a reusable resource.
    Retries transient connection failures with a short bounded loop.
    """

    def __init__(self, config: LDAPConfig, pool_size: int = 3, retries: int = 2, timeout: int = 5):
        self.config = config
        self.pool_size = pool_size
        self.retries = retries
        self.timeout = timeout
        self._pool: list[Connection] = []
        self._server: Optional[Server] = None

    def _get_server(self) -> Server:
        if self._server is None:
            use_ssl = self.config.uri.lower().startswith("ldaps://")
            tls = None
            if use_ssl or self.config.tls_ca_cert:
                # Always verify the server certificate when TLS is used at
                # all (T-64-07). ca_certs_file=None falls back to the
                # system trust store; set LDAP_TLS_CA_CERT for a private CA
                # or self-signed cert.
                tls = Tls(
                    validate=ssl.CERT_REQUIRED,
                    ca_certs_file=self.config.tls_ca_cert,
                )
            self._server = Server(
                self.config.uri,
                use_ssl=use_ssl,
                tls=tls,
                get_info=ALL,
                connect_timeout=self.timeout,
            )
        return self._server

    def _open(self, user: str, password: str, allow_starttls: bool) -> Connection:
        server = self._get_server()
        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                conn = Connection(
                    server,
                    user=user,
                    password=password,
                    auto_bind=False,
                    receive_timeout=self.timeout,
                )
                conn.open()
                if (
                    allow_starttls
                    and not getattr(server, "ssl", False)
                    and self.config.uri.lower().startswith("ldap://")
                    and self.config.tls_ca_cert
                ):
                    if not conn.start_tls():
                        raise LDAPConnectionError("StartTLS negotiation failed")
                if not conn.bind():
                    detail = (conn.result or {}).get("description", "bind failed")
                    raise LDAPBindError(detail)
                return conn
            except LDAPBindError:
                raise
            except (LDAPSocketOpenError, LDAPSocketReceiveError, LDAPException) as exc:
                last_exc = exc
                logger.warning(
                    "LDAP connection attempt %d/%d to %s failed: %s",
                    attempt + 1, self.retries + 1, self.config.uri, exc,
                )
        raise LDAPConnectionError(f"Could not connect to LDAP server {self.config.uri}: {last_exc}")

    def _acquire_service_connection(self) -> Connection:
        while self._pool:
            conn = self._pool.pop()
            if getattr(conn, "bound", False):
                return conn
        return self._open(self.config.bind_dn, self.config.bind_password, allow_starttls=True)

    def _release_service_connection(self, conn: Connection) -> None:
        if len(self._pool) < self.pool_size and getattr(conn, "bound", False):
            self._pool.append(conn)
        else:
            try:
                conn.unbind()
            except Exception:
                pass

    def service_connection(self) -> "_PooledConnectionContext":
        """Context manager yielding a bound service-account Connection,
        reused from the pool when available."""
        return _PooledConnectionContext(self)

    def user_connection(self, user_dn: str, password: str) -> "_SingleUseConnectionContext":
        """Context manager yielding a single-use Connection bound as the
        given user DN — used only to verify credentials, never pooled."""
        return _SingleUseConnectionContext(self, user_dn, password)


class _PooledConnectionContext:
    def __init__(self, manager: LDAPConnectionManager):
        self._manager = manager
        self._conn: Optional[Connection] = None

    def __enter__(self) -> Connection:
        self._conn = self._manager._acquire_service_connection()
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        if self._conn is not None:
            self._manager._release_service_connection(self._conn)
        return False


class _SingleUseConnectionContext:
    def __init__(self, manager: LDAPConnectionManager, user_dn: str, password: str):
        self._manager = manager
        self._user_dn = user_dn
        self._password = password
        self._conn: Optional[Connection] = None

    def __enter__(self) -> Connection:
        self._conn = self._manager._open(self._user_dn, self._password, allow_starttls=True)
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        if self._conn is not None:
            try:
                self._conn.unbind()
            except Exception:
                pass
        return False


# ─── Authentication ───────────────────────────────────────────────────────────

class LDAPAuthenticator:
    """Verifies end-user credentials by binding to LDAP as that user (never
    the service account) — the only way to check a password without ever
    storing or even seeing it in plaintext beyond the single bind call."""

    def __init__(self, config: LDAPConfig):
        self.config = config
        self._conn_mgr = LDAPConnectionManager(config)

    def _search_user_dn(self, conn: Connection, username: str) -> Optional[str]:
        conn.search(
            search_base=self.config.user_base_dn,
            search_filter=_user_search_filter(self.config, username),
            search_scope=SUBTREE,
            attributes=[self.config.user_id_attr],
        )
        if not conn.entries:
            return None
        return conn.entries[0].entry_dn

    def authenticate(self, username: str, password: str) -> dict:
        """Resolve the user's DN (via the service account) then bind as
        that user to verify credentials.

        Raises LDAPAuthError for "no such user" / "bad credentials",
        LDAPConnectionError for connectivity/TLS failures.
        """
        if not password:
            raise LDAPAuthError("Password required")

        with self._conn_mgr.service_connection() as service_conn:
            user_dn = self._search_user_dn(service_conn, username)
        if not user_dn:
            raise LDAPAuthError(f"No LDAP user found for '{username}'")

        try:
            with self._conn_mgr.user_connection(user_dn, password):
                return {"dn": user_dn, "bound": True}
        except LDAPBindError as exc:
            raise LDAPAuthError(f"Invalid LDAP credentials for '{username}'") from exc


# ─── User sync ────────────────────────────────────────────────────────────────

class LDAPUserSyncer:
    """Searches LDAP for users, maps directory attributes, and upserts into
    MongoDB with source="ldap" (Pitfall 4 / T-64-12)."""

    def __init__(self, config: LDAPConfig):
        self.config = config
        self._conn_mgr = LDAPConnectionManager(config)

    def _map_entry(self, entry: Any) -> Optional[dict]:
        attrs = entry.entry_attributes_as_dict

        def _first(attr_name: str) -> Optional[str]:
            vals = attrs.get(attr_name) or []
            return vals[0] if vals else None

        user_id = _first(self.config.user_id_attr)
        email = _first(self.config.user_email_attr)
        name = _first(self.config.user_name_attr) or user_id
        if not user_id or not email:
            return None
        groups = attrs.get("memberOf") or []
        return {
            "ldap_dn": entry.entry_dn,
            "ldap_user_id": user_id,
            "email": email,
            "full_name": name,
            "groups": list(groups),
        }

    def search_users(self) -> list[dict]:
        """Synchronous LDAP search — run via asyncio.to_thread from async callers."""
        results: list[dict] = []
        with self._conn_mgr.service_connection() as conn:
            conn.search(
                search_base=self.config.user_base_dn,
                search_filter=self.config.user_filter,
                search_scope=SUBTREE,
                attributes=[
                    self.config.user_id_attr,
                    self.config.user_email_attr,
                    self.config.user_name_attr,
                    "memberOf",
                ],
            )
            for entry in conn.entries:
                mapped = self._map_entry(entry)
                if mapped:
                    results.append(mapped)
        return results

    def search_single_user(self, username: str) -> Optional[dict]:
        """Synchronous single-user lookup by username (post-authentication
        re-fetch) — run via asyncio.to_thread from async callers."""
        with self._conn_mgr.service_connection() as conn:
            conn.search(
                search_base=self.config.user_base_dn,
                search_filter=_user_search_filter(self.config, username),
                search_scope=SUBTREE,
                attributes=[
                    self.config.user_id_attr,
                    self.config.user_email_attr,
                    self.config.user_name_attr,
                    "memberOf",
                ],
            )
            if not conn.entries:
                return None
            return self._map_entry(conn.entries[0])

    async def sync_user(
        self,
        mapped: dict,
        tenant_id: str,
        role: Optional[str] = None,
        default_role: str = "itam_viewer",
    ) -> dict:
        """Upsert a single mapped LDAP user into MongoDB with source="ldap".

        `role` should only be passed when a group mapping actually resolved
        one — on update, an existing user's role is left untouched when
        `role` is None, so a re-sync (or every LDAP login) never silently
        downgrades an admin-assigned elevated role back to the default.
        `default_role` is only applied when creating a brand-new user.
        """
        db = get_database()
        now = datetime.now(timezone.utc).isoformat()
        existing = await db.users.find_one({"email": mapped["email"], "tenantId": tenant_id})
        doc = {
            "email": mapped["email"],
            "full_name": mapped["full_name"],
            "tenantId": tenant_id,
            "source": "ldap",
            "ldap_dn": mapped["ldap_dn"],
            "ldap_groups": mapped["groups"],
            "status": "Active",
            "updatedAt": now,
        }
        if existing:
            if role:
                doc["role"] = role
            await db.users.update_one({"_id": existing["_id"]}, {"$set": doc})
            doc["_id"] = existing["_id"]
            doc["role"] = doc.get("role", existing.get("role", default_role))
        else:
            doc["role"] = role or default_role
            doc["createdAt"] = now
            result = await db.users.insert_one(doc)
            doc["_id"] = result.inserted_id
        return doc

    async def sync_all(
        self,
        tenant_id: str,
        group_mapper: Optional["LDAPGroupMapper"] = None,
        default_role: str = "itam_viewer",
    ) -> dict:
        """Full sync: search LDAP, resolve each user's role via group
        mapping, upsert every user. Returns a summary dict."""
        mapped_users = await asyncio.to_thread(self.search_users)
        synced = 0
        errors: list[dict] = []
        for mapped in mapped_users:
            try:
                role = await group_mapper.resolve_role(mapped["groups"], tenant_id) if group_mapper else None
                await self.sync_user(mapped, tenant_id, role=role, default_role=default_role)
                synced += 1
            except Exception as exc:
                logger.error("Failed to sync LDAP user %s: %s", mapped.get("email"), exc)
                errors.append({"email": mapped.get("email"), "error": str(exc)})
        return {"total_found": len(mapped_users), "synced": synced, "errors": errors}


# ─── Group -> role mapping ─────────────────────────────────────────────────────

class LDAPGroupMapper:
    """Maps LDAP group DNs to ITAM roles via an admin-managed
    `ldap_group_mappings` collection (T-64-09)."""

    def __init__(self, config: LDAPConfig):
        self.config = config
        self._conn_mgr = LDAPConnectionManager(config)

    def search_groups(self) -> list[dict]:
        """Synchronous LDAP group search — run via asyncio.to_thread from
        async callers."""
        if not self.config.group_base_dn:
            return []
        results: list[dict] = []
        with self._conn_mgr.service_connection() as conn:
            conn.search(
                search_base=self.config.group_base_dn,
                search_filter=self.config.group_filter,
                search_scope=SUBTREE,
                attributes=[self.config.group_member_attr, "cn"],
            )
            for entry in conn.entries:
                attrs = entry.entry_attributes_as_dict
                results.append({
                    "dn": entry.entry_dn,
                    "cn": (attrs.get("cn") or [None])[0],
                    "members": list(attrs.get(self.config.group_member_attr) or []),
                })
        return results

    async def resolve_role(self, group_dns: list[str], tenant_id: Optional[str] = None) -> Optional[str]:
        """Given the group DNs a user belongs to (memberOf), return the
        highest-priority mapped ITAM role, or None if no mapping matches."""
        if not group_dns:
            return None
        db = get_database()
        query: dict = {"group_dn": {"$in": group_dns}}
        if tenant_id:
            query["tenant_id"] = tenant_id
        mappings = await db.ldap_group_mappings.find(query).sort("priority", 1).to_list(100)
        if mappings:
            return mappings[0].get("role")
        return None

    @staticmethod
    async def list_mappings(tenant_id: Optional[str] = None) -> list[dict]:
        db = get_database()
        query: dict = {"tenant_id": tenant_id} if tenant_id else {}
        docs = await db.ldap_group_mappings.find(query).to_list(200)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    @staticmethod
    async def upsert_mapping(
        group_dn: str, role: str, tenant_id: Optional[str] = None, priority: int = 100,
    ) -> dict:
        from rbac_service import rbac_service
        normalized = rbac_service._normalize_role(role)
        valid_roles = {rbac_service._normalize_role(k) for k in rbac_service.default_roles.keys()}
        if normalized not in valid_roles:
            raise LDAPConfigError(f"'{role}' is not a valid ITAM role")

        db = get_database()
        doc = {"group_dn": group_dn, "role": role, "tenant_id": tenant_id, "priority": priority}
        result = await db.ldap_group_mappings.update_one(
            {"group_dn": group_dn, "tenant_id": tenant_id},
            {"$set": doc},
            upsert=True,
        )
        doc["_id"] = str(result.upserted_id) if getattr(result, "upserted_id", None) else None
        return doc

    @staticmethod
    async def delete_mapping(mapping_id: str) -> bool:
        from bson import ObjectId
        db = get_database()
        result = await db.ldap_group_mappings.delete_one({"_id": ObjectId(mapping_id)})
        return result.deleted_count > 0


# ─── Full authenticate -> sync -> mint-JWT flow ────────────────────────────────

async def is_ldap_sourced_user(email: str, tenant_id: Optional[str] = None) -> bool:
    """True if the given user's record has source="ldap" — used to block
    local password changes for LDAP-sourced users (Pitfall 4 / T-64-12)."""
    db = get_database()
    query: dict = {"email": email}
    if tenant_id:
        query["tenantId"] = tenant_id
    user = await db.users.find_one(query, {"source": 1})
    return bool(user and user.get("source") == "ldap")


async def authenticate_ldap(username: str, password: str, tenant_id: Optional[str] = None) -> dict:
    """LDAP bind -> sync user -> mint JWT.

    Token minting delegates to authentication_service.create_access_token /
    create_refresh_token (imported, not duplicated) — the login endpoint
    lives in ldap_endpoints.py as its own dedicated route, not as a branch
    inside the existing local-auth login handler in authentication_endpoints.py
    (that file is rewritten by plan 64-06 in the same wave for two-phase MFA;
    a competing edit here would collide).

    `tenant_id` is the caller's known tenant, if any (admin-triggered flows
    always know it). The public login route passes None (no tenant context
    exists before authentication); this function then determines a target
    tenant, in order: an existing local user record's tenantId (so any
    previously-provisioned account keeps its tenant), then LDAP_DEFAULT_TENANT_ID
    (for first-time LDAP-only provisioning in a single-tenant-directory
    deployment), else raises LDAPSyncError.
    """
    config = await get_ldap_config(tenant_id)
    authenticator = LDAPAuthenticator(config)
    await asyncio.to_thread(authenticator.authenticate, username, password)

    syncer = LDAPUserSyncer(config)
    mapped = await asyncio.to_thread(syncer.search_single_user, username)
    if not mapped:
        raise LDAPSyncError(
            f"LDAP user '{username}' authenticated but could not be re-fetched for sync"
        )

    db = get_database()
    existing = await db.users.find_one({"email": mapped["email"]})
    target_tenant_id = (
        tenant_id
        or (existing.get("tenantId") if existing else None)
        or os.getenv("LDAP_DEFAULT_TENANT_ID")
    )
    if not target_tenant_id:
        raise LDAPSyncError(
            f"LDAP user '{mapped['email']}' authenticated but has no existing local "
            "account and no tenant could be determined. Set LDAP_DEFAULT_TENANT_ID "
            "for first-time LDAP provisioning, or pre-create the user via "
            "POST /api/users with the matching tenantId."
        )

    group_mapper = LDAPGroupMapper(config)
    role = await group_mapper.resolve_role(mapped["groups"], target_tenant_id)
    user_doc = await syncer.sync_user(mapped, target_tenant_id, role=role)

    from authentication_service import create_access_token, create_refresh_token
    token_payload = {
        "sub": user_doc["email"],
        "role": user_doc.get("role", "itam_viewer"),
        "tenant_id": target_tenant_id,
    }
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data={"sub": user_doc["email"]})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "success": True,
        "email": user_doc["email"],
        "role": user_doc.get("role", "itam_viewer"),
        "tenant_id": target_tenant_id,
    }
