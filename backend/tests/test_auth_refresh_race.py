"""Live-Mongo regression test for SESS-01 (D-05 Mechanism A).

Proves that two concurrent /api/auth/refresh calls carrying the identical
refresh token yield exactly one winner, backed by the revoked_tokens.jti
unique index added in database.py. A mock of db._db.revoked_tokens would
allow duplicate inserts and pass whether or not the index exists (Pitfall 3,
40-RESEARCH.md), so this test drives the real FastAPI router — via
httpx.AsyncClient over an ASGI transport — against a real MongoDB instance,
following the live-Mongo fixture pattern in test_evidence_review.py
(lines 406-463: motor client + ping/skip + try/finally cleanup).
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _make_auth_app():
    """Minimal FastAPI app with only the auth router and SlowAPI middleware.

    Mirrors test_auth_mfa.py's _make_auth_app helper; duplicated here (rather
    than imported) so this file's live-Mongo fixture scaffolding stays
    self-contained, matching the isolation rationale for a new test file
    called out in the plan.
    """
    import authentication_endpoints as auth_ep
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    mini = FastAPI()
    test_limiter = Limiter(key_func=get_remote_address)
    mini.state.limiter = test_limiter
    mini.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    mini.add_middleware(SlowAPIMiddleware)
    mini.include_router(auth_ep.router)
    return mini


class _RealDbWrapper:
    """Minimal shim matching the db._db access pattern refresh_access_token
    uses (it bypasses tenant isolation for auth-global lookups — see the
    "WHY db._db.* IS USED IN THIS FILE" comment block at the top of
    authentication_endpoints.py), backed by a real Mongo database instead of
    a mock."""

    def __init__(self, mdb):
        self._db = mdb


def test_concurrent_refresh_yields_exactly_one_winner():
    """SESS-01 / D-05 Mechanism A regression test.

    Fires two concurrent POST /api/auth/refresh calls carrying the identical
    refresh token. Without the revoked_tokens.jti unique index, both requests
    can "win" the find_one_and_update + $setOnInsert race and both succeed,
    silently corrupting single-use rotation and producing the intermittent
    401s SESS-01 tracks. With the index, exactly one call gets a fresh token
    pair (200) and the other is rejected (401), and exactly one revoked_tokens
    document is persisted for the jti — proving the *database* enforced
    uniqueness, not merely that the two requests happened to serialize.
    """
    import motor.motor_asyncio
    import authentication_service as auth_svc
    import jwt as _jwt

    mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI", "mongodb://localhost:27017")

    async def _run():
        client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
        except Exception:
            client.close()
            # In CI, a missing MongoDB is a broken environment, not a legitimately-
            # absent optional dependency — fail loudly instead of silently skipping.
            if os.environ.get("CI"):
                pytest.fail(
                    f"No live MongoDB reachable at {mongo_uri} for SESS-01 concurrent-refresh "
                    f"regression test — CI environments must provide MONGODB_URI/MONGO_URI so "
                    f"this test actually runs instead of silently skipping"
                )
            pytest.skip(f"No live MongoDB reachable at {mongo_uri} for SESS-01 concurrent-refresh regression test")
            return

        motor_db = client["auth_refresh_race_test"]
        email = "sess01-refresh-race@example.com"
        jti = None

        # Ensure the jti unique index exists on this test DB — mirrors the
        # line added to database.py's connect_to_mongo index block so the
        # test actually exercises the uniqueness constraint, not merely
        # whatever happens to exist on whichever DB the test runner points at.
        await motor_db.revoked_tokens.create_index("jti", unique=True, background=True)

        try:
            await motor_db.users.delete_many({"email": email})
            await motor_db.users.insert_one({
                "id": "sess01-race-user",
                "email": email,
                "role": "user",
                "tenantId": "tenant-sess01-race",
                "status": "Active",
            })

            refresh_token = auth_svc.create_refresh_token(data={"sub": email})
            payload = _jwt.decode(refresh_token, auth_svc.SECRET_KEY, algorithms=[auth_svc.ALGORITHM])
            jti = payload["jti"]

            # Belt-and-suspenders: a leftover document from a previous failed
            # run with the same jti would make this test pass vacuously.
            await motor_db.revoked_tokens.delete_many({"jti": jti})

            app = _make_auth_app()
            db = _RealDbWrapper(motor_db)

            with patch("authentication_endpoints.get_database", return_value=db):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
                    resp1, resp2 = await asyncio.gather(
                        http_client.post("/api/auth/refresh", json={"refresh_token": refresh_token}),
                        http_client.post("/api/auth/refresh", json={"refresh_token": refresh_token}),
                    )

            statuses = sorted([resp1.status_code, resp2.status_code])
            assert statuses == [200, 401], (
                f"SESS-01 regression: expected exactly one 200 + one 401 for concurrent "
                f"/refresh with the same token, got {resp1.status_code} and {resp2.status_code} "
                f"— {resp1.text!r} / {resp2.text!r}"
            )

            winner = resp1 if resp1.status_code == 200 else resp2
            body = winner.json()
            assert body.get("success") is True
            assert body.get("access_token")
            assert body.get("refresh_token")

            count = await motor_db.revoked_tokens.count_documents({"jti": jti})
            assert count == 1, (
                f"SESS-01 regression: expected exactly one revoked_tokens document for "
                f"jti={jti!r} after a concurrent-refresh race (proving the unique index "
                f"rejected the duplicate insert), got {count}"
            )
        finally:
            await motor_db.users.delete_many({"email": email})
            if jti:
                await motor_db.revoked_tokens.delete_many({"jti": jti})
            client.close()

    asyncio.run(_run())
