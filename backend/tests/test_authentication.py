"""
Tests for authentication service: JWT creation, verification, expiry cap,
algorithm allow-list, and secret key strength.

These tests reload authentication_service after patching env vars so each
test runs in an isolated module state without interfering with other tests.
"""
import os
import sys
import importlib
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_auth():
    """Force a fresh import of authentication_service, respecting current env."""
    import authentication_service
    importlib.reload(authentication_service)
    return authentication_service


# ---------------------------------------------------------------------------
# Token expiry cap
# ---------------------------------------------------------------------------

class TestTokenExpiryCap:

    def test_expiry_is_capped_at_120_minutes(self):
        """ACCESS_TOKEN_EXPIRE_MINUTES must never exceed 120 regardless of env var."""
        with patch.dict(os.environ, {"ACCESS_TOKEN_EXPIRE_MINUTES": "999",
                                     "ENVIRONMENT": "test"}):
            auth = _reload_auth()
            assert auth.ACCESS_TOKEN_EXPIRE_MINUTES <= 120, (
                f"Token expiry {auth.ACCESS_TOKEN_EXPIRE_MINUTES} exceeds the 120-minute cap"
            )

    def test_expiry_default_is_reasonable(self):
        """Default token expiry should be between 15 and 120 minutes."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}, clear=False):
            # Remove the override if present so the default kicks in
            env = {k: v for k, v in os.environ.items() if k != "ACCESS_TOKEN_EXPIRE_MINUTES"}
            env["ENVIRONMENT"] = "test"
            with patch.dict(os.environ, env, clear=True):
                auth = _reload_auth()
                assert 15 <= auth.ACCESS_TOKEN_EXPIRE_MINUTES <= 120, (
                    f"Default expiry {auth.ACCESS_TOKEN_EXPIRE_MINUTES} is outside the 15-120 range"
                )

    def test_expiry_low_value_is_preserved(self):
        """Values below the cap (e.g. 30 min) should not be modified."""
        with patch.dict(os.environ, {"ACCESS_TOKEN_EXPIRE_MINUTES": "30",
                                     "ENVIRONMENT": "test"}):
            auth = _reload_auth()
            assert auth.ACCESS_TOKEN_EXPIRE_MINUTES == 30


# ---------------------------------------------------------------------------
# Token claims
# ---------------------------------------------------------------------------

class TestCreateAccessToken:

    def test_token_contains_required_claims(self):
        """Access token must contain sub, jti, exp, and tenant_id."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            import jwt as pyjwt
            token = auth.create_access_token(
                data={"sub": "user@example.com", "tenant_id": "tenant-test", "role": "User"}
            )
            payload = pyjwt.decode(
                token,
                auth.SECRET_KEY,
                algorithms=[auth.ALGORITHM],
            )
            assert "sub" in payload, "Token must contain 'sub' claim"
            assert "jti" in payload, "Token must contain 'jti' (JWT ID) claim"
            assert "exp" in payload, "Token must contain 'exp' (expiry) claim"
            assert "tenant_id" in payload, "Token must contain 'tenant_id' claim"

    def test_token_sub_matches_input(self):
        """sub claim must match the email passed to create_access_token."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            import jwt as pyjwt
            token = auth.create_access_token(
                data={"sub": "alice@example.com", "tenant_id": "t1"}
            )
            payload = pyjwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            assert payload["sub"] == "alice@example.com"

    def test_jti_is_unique_across_tokens(self):
        """Each token must have a distinct jti to enable per-token revocation."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            import jwt as pyjwt
            tokens = [
                auth.create_access_token(data={"sub": f"user{i}@example.com", "tenant_id": "t1"})
                for i in range(5)
            ]
            payloads = [
                pyjwt.decode(t, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
                for t in tokens
            ]
            jtis = [p["jti"] for p in payloads]
            assert len(set(jtis)) == 5, "All JTIs must be unique"


# ---------------------------------------------------------------------------
# Algorithm allow-list / none-algorithm attack
# ---------------------------------------------------------------------------

class TestJwtAlgorithmSecurity:

    def test_none_algorithm_token_is_rejected(self):
        """Tokens signed with 'none' algorithm must be rejected by verify_token."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            import jwt as pyjwt
            from fastapi import HTTPException

            # PyJWT >= 2.x raises an error on encode with 'none'; craft raw token instead
            import base64, json
            header = base64.urlsafe_b64encode(
                json.dumps({"alg": "none", "typ": "JWT"}).encode()
            ).rstrip(b"=").decode()
            payload_part = base64.urlsafe_b64encode(
                json.dumps({"sub": "attacker@example.com",
                            "tenant_id": "platform-admin",
                            "role": "Super Admin"}).encode()
            ).rstrip(b"=").decode()
            # 'none' algorithm token has an empty signature
            malicious_token = f"{header}.{payload_part}."

            with pytest.raises(Exception):
                auth.verify_token(malicious_token)

    def test_verify_token_rejects_tampered_signature(self):
        """A token with a modified payload must fail verification."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            import jwt as pyjwt
            from fastapi import HTTPException

            token = auth.create_access_token(
                data={"sub": "user@example.com", "tenant_id": "t1", "role": "User"}
            )
            # Tamper with the middle (payload) segment
            header, payload_b64, sig = token.split(".")
            import base64, json
            padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            payload_obj = json.loads(base64.urlsafe_b64decode(padded))
            payload_obj["role"] = "Super Admin"
            tampered_payload = base64.urlsafe_b64encode(
                json.dumps(payload_obj).encode()
            ).rstrip(b"=").decode()
            tampered_token = f"{header}.{tampered_payload}.{sig}"

            with pytest.raises(Exception):
                auth.verify_token(tampered_token)


# ---------------------------------------------------------------------------
# Secret key strength
# ---------------------------------------------------------------------------

class TestSecretKeyStrength:

    def test_secret_key_not_empty_in_test_env(self):
        """JWT secret key must not be empty (dev env generates an ephemeral one)."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            assert len(auth.SECRET_KEY) >= 32, (
                f"JWT secret key is too short ({len(auth.SECRET_KEY)} chars). "
                "Minimum 32 characters required."
            )

    def test_algorithm_is_hmac_based(self):
        """Only HMAC-based algorithms are permitted."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            assert auth.ALGORITHM.startswith("HS"), (
                f"Non-HMAC algorithm '{auth.ALGORITHM}' detected"
            )

    def test_invalid_algorithm_raises_on_load(self):
        """Setting JWT_ALGORITHM to 'RS256' must raise RuntimeError at import time."""
        env = {
            "JWT_ALGORITHM": "RS256",
            "JWT_SECRET_KEY": "x" * 64,
            "ENVIRONMENT": "test",
        }
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(RuntimeError, match="not in the allowed set"):
                _reload_auth()


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------

class TestRefreshToken:

    def test_refresh_token_has_type_claim(self):
        """Refresh tokens must carry type='refresh' to distinguish from access tokens."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            import jwt as pyjwt
            token = auth.create_refresh_token(
                data={"sub": "user@example.com", "tenant_id": "t1"}
            )
            payload = pyjwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            assert payload.get("type") == "refresh"

    def test_refresh_token_expiry_is_7_days(self):
        """Refresh token must expire in exactly 7 days."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            auth = _reload_auth()
            assert auth.REFRESH_TOKEN_EXPIRE_DAYS == 7
