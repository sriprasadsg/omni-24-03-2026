"""
SSO Service — SAML 2.0 + OIDC Provider Support
------------------------------------------------
Supports:
  - SAML 2.0 Service Provider (Okta, Azure AD, ADFS, OneLogin)
  - OIDC / OAuth2 (Google Workspace, Azure AD, Okta, GitHub Enterprise)
  - Automatic user provisioning from IdP assertions
  - Per-tenant SSO configuration stored in MongoDB
"""

import uuid
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Optional
from database import get_database

# In-memory OIDC state store (nonce → { provider, redirect_uri, expires })
_oidc_states: dict = {}


# ─── OIDC Provider Configs (well-known providers) ─────────────────────────────

KNOWN_OIDC_PROVIDERS = {
    "google": {
        "name": "Google Workspace",
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": "openid email profile",
    },
    "azure": {
        "name": "Microsoft Azure AD",
        "authorization_endpoint": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
        "token_endpoint": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
        "scopes": "openid email profile",
    },
    "okta": {
        "name": "Okta",
        "authorization_endpoint": "https://{okta_domain}/oauth2/default/v1/authorize",
        "token_endpoint": "https://{okta_domain}/oauth2/default/v1/token",
        "userinfo_endpoint": "https://{okta_domain}/oauth2/default/v1/userinfo",
        "scopes": "openid email profile groups",
    },
    "github": {
        "name": "GitHub Enterprise",
        "authorization_endpoint": "https://github.com/login/oauth/authorize",
        "token_endpoint": "https://github.com/login/oauth/access_token",
        "userinfo_endpoint": "https://api.github.com/user",
        "scopes": "read:user user:email",
    },
}


# ─── SSO Config Management ────────────────────────────────────────────────────

async def get_sso_configs(tenant_id: str) -> list:
    """Return all SSO providers configured for a tenant."""
    db = get_database()
    configs = await db.sso_configs.find({"tenant_id": tenant_id}).to_list(100)
    # Mask client_secret
    for c in configs:
        c["_id"] = str(c["_id"])
        if c.get("client_secret"):
            c["client_secret"] = "***masked***"
        if c.get("saml_certificate"):
            c["saml_certificate"] = c["saml_certificate"][:40] + "..."
    return configs


async def save_sso_config(tenant_id: str, config: dict) -> dict:
    """Save or update an SSO provider configuration."""
    db = get_database()
    config_id = config.get("config_id") or str(uuid.uuid4())
    doc = {
        "config_id": config_id,
        "tenant_id": tenant_id,
        "provider_type": config.get("provider_type"),  # "saml" | "oidc"
        "provider_name": config.get("provider_name"),   # e.g. "Okta", "Azure AD"
        "enabled": config.get("enabled", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
        # SAML fields
        "idp_entity_id": config.get("idp_entity_id"),
        "idp_sso_url": config.get("idp_sso_url"),
        "saml_certificate": config.get("saml_certificate"),
        "attribute_email": config.get("attribute_email", "email"),
        "attribute_name": config.get("attribute_name", "name"),
        "attribute_role": config.get("attribute_role", "role"),
        # OIDC fields
        "oidc_provider": config.get("oidc_provider"),   # key in KNOWN_OIDC_PROVIDERS
        "client_id": config.get("client_id"),
        "client_secret": config.get("client_secret"),
        "okta_domain": config.get("okta_domain"),
        "azure_tenant_id": config.get("azure_tenant_id"),
        "redirect_uri": config.get("redirect_uri", "http://localhost:3000/api/sso/oidc/callback"),
    }
    await db.sso_configs.update_one(
        {"config_id": config_id, "tenant_id": tenant_id},
        {"$set": doc},
        upsert=True,
    )
    return {"success": True, "config_id": config_id}


async def delete_sso_config(tenant_id: str, config_id: str) -> dict:
    db = get_database()
    result = await db.sso_configs.delete_one({"config_id": config_id, "tenant_id": tenant_id})
    return {"success": result.deleted_count > 0}


# ─── OIDC Flow ────────────────────────────────────────────────────────────────

def build_oidc_auth_url(config: dict) -> str:
    """Build the authorization URL for OIDC login."""
    provider_key = config.get("oidc_provider", "google")
    provider = KNOWN_OIDC_PROVIDERS.get(provider_key, {})
    
    auth_endpoint = provider.get("authorization_endpoint", "")
    
    # Template substitutions
    if provider_key == "azure":
        auth_endpoint = auth_endpoint.replace("{tenant_id}", config.get("azure_tenant_id", "common"))
    elif provider_key == "okta":
        auth_endpoint = auth_endpoint.replace("{okta_domain}", config.get("okta_domain", ""))
    
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)
    _oidc_states[state] = {
        "config_id": config.get("config_id"),
        "nonce": nonce,
    }
    
    params = {
        "client_id": config.get("client_id"),
        "response_type": "code",
        "scope": provider.get("scopes", "openid email profile"),
        "redirect_uri": config.get("redirect_uri"),
        "state": state,
        "nonce": nonce,
    }
    return auth_endpoint + "?" + urllib.parse.urlencode(params)


async def handle_oidc_callback(code: str, state: str) -> dict:
    """
    Exchange auth code for user info and provision/return user.
    Returns: { success, email, name, provider }
    """
    state_data = _oidc_states.pop(state, None)
    if not state_data:
        return {"success": False, "error": "Invalid or expired OAuth state"}

    db = get_database()
    config = await db.sso_configs.find_one({"config_id": state_data["config_id"]})
    if not config:
        return {"success": False, "error": "SSO config not found"}

    provider_key = config.get("oidc_provider", "google")
    provider = KNOWN_OIDC_PROVIDERS.get(provider_key, {})

    token_endpoint = provider.get("token_endpoint", "")
    if provider_key == "azure":
        token_endpoint = token_endpoint.replace("{tenant_id}", config.get("azure_tenant_id", "common"))
    elif provider_key == "okta":
        token_endpoint = token_endpoint.replace("{okta_domain}", config.get("okta_domain", ""))

    try:
        import httpx
        # Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.get("redirect_uri"),
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
        }
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(token_endpoint, data=token_data)
            tokens = token_resp.json()
            
            access_token = tokens.get("access_token")
            userinfo_url = provider.get("userinfo_endpoint", "").replace(
                "{okta_domain}", config.get("okta_domain", "")
            )
            userinfo_resp = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            userinfo = userinfo_resp.json()

        email = userinfo.get("email") or userinfo.get("login")  # GitHub uses 'login'
        if not email and provider_key == "github":
            # Fetch primary email separately for GitHub
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            primary = next((e for e in emails_resp.json() if e.get("primary")), {})
            email = primary.get("email")

        name = userinfo.get("name") or userinfo.get("display_name") or email
        return {"success": True, "email": email, "name": name, "provider": provider_key}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── SAML Flow (lightweight — no python3-saml dependency required) ────────────

async def get_saml_sp_metadata(base_url: str) -> str:
    """Return SP metadata XML."""
    return f"""<?xml version="1.0"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata"
  entityID="{base_url}/api/sso/saml/metadata">
  <SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="{base_url}/api/sso/saml/acs"
      index="0"/>
  </SPSSODescriptor>
</EntityDescriptor>"""


async def process_saml_response(saml_response_b64: str, tenant_id: str) -> dict:
    """
    Parse a base64-encoded SAMLResponse and extract user attributes.
    Returns: { success, email, name }
    Uses python3-saml if available, otherwise falls back to regex parsing for demo.
    """
    import base64
    try:
        xml = base64.b64decode(saml_response_b64).decode("utf-8", errors="replace")
    except Exception:
        return {"success": False, "error": "Invalid SAML response encoding"}

    try:
        # Try with python3-saml if installed
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        return {"success": False, "error": "python3-saml requires server-side setup"}
    except ImportError:
        pass

    # Lightweight XML parsing fallback (for demo purposes)
    import re
    email_match = re.search(r'<(?:saml|saml2):NameID[^>]*>([^<]+@[^<]+)</', xml)
    name_match = re.search(r'<Attribute Name="[^"]*[Nn]ame[^"]*"[^>]*>\s*<AttributeValue>([^<]+)</AttributeValue>', xml)
    
    if email_match:
        return {
            "success": True,
            "email": email_match.group(1).strip(),
            "name": name_match.group(1).strip() if name_match else None,
        }
    return {"success": False, "error": "Could not extract email from SAML assertion"}


# ─── User Provisioning ────────────────────────────────────────────────────────

async def provision_sso_user(email: str, name: str, provider: str, tenant_id: str) -> dict:
    """
    Ensure an SSO user exists in MongoDB.
    Creates them on first login; updates name on subsequent logins.
    Returns the user document.
    """
    db = get_database()
    user = await db.users.find_one({"email": email})
    
    if not user:
        # First SSO login — provision the user
        import bcrypt
        new_user = {
            "email": email,
            "username": email.split("@")[0],
            "name": name or email,
            "role": "analyst",  # Default SSO role — admin can elevate
            "tenantId": tenant_id,
            "password": bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode(),
            "sso_provider": provider,
            "created_via": "sso",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(new_user)
        user = await db.users.find_one({"email": email})
    else:
        # Update name from IdP on each login
        await db.users.update_one(
            {"email": email},
            {"$set": {"name": name or user.get("name"), "last_sso_login": datetime.now(timezone.utc).isoformat()}}
        )
    
    return {k: v for k, v in user.items() if k not in ("password", "_id", "mfa")}
