"""
Every mounted route needs an authentication dependency unless it is on the
reviewed list below (CSO run 1791310678799-7dcecc4e5cd0b8be).

router_registry includes routers without a default auth dependency, so a route
that forgets Depends(get_current_user) is silently public. This test builds the
app exactly as production does and fails on any unauthenticated route that is
not listed here. Entries on the list are public by design or check a
credential inside the handler; the list should only shrink.
Hermetic — no Mongo (routes are registered, never called).
"""
import pytest

from tests._route_walk import run_real_app_walk

# (method, path). "WS" marks a websocket route.
REVIEWED_UNAUTHENTICATED = frozenset({
    # Sign-in, sign-up, token refresh, password reset, MFA, passkeys, LDAP, SSO
    ("POST", "/api/auth/login"), ("POST", "/api/auth/signup"), ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/reset-password/request"), ("POST", "/api/auth/reset-password/confirm"),
    ("POST", "/api/mfa/verify"), ("POST", "/api/passkey/login/options"),
    ("POST", "/api/passkey/login/verify"), ("POST", "/api/auth/ldap/login"),
    ("POST", "/api/auth/saml/acs"), ("GET", "/api/auth/saml/login"),
    ("GET", "/api/auth/saml/metadata"), ("GET", "/api/auth/saml/slo"),
    ("POST", "/api/sso/exchange"), ("GET", "/api/sso/google/callback"),
    # Revokes whatever access token / refresh cookie the caller presents and
    # clears the cookie; must work after the access token has expired
    ("POST", "/api/auth/logout"),
    ("GET", "/api/sso/google/login"), ("GET", "/api/sso/providers"), ("GET", "/api/sso/status"),
    # Agent enrollment and self-update (registration key / public binaries)
    ("POST", "/api/agents/register"), ("GET", "/api/agents/version"),
    ("POST", "/api/tenants/lookup-key"),
    ("GET", "/api/agent-updates/latest"), ("GET", "/api/agent-updates/download/{filename}"),
    ("GET", "/api/agent-updates/checksum/{filename}"),
    ("GET", "/api/agent/install-script"), ("GET", "/api/agent/collect-evidence-script"),
    # Credential checked inside the handler (optional user, one-time token,
    # agent key/JWT, share/response/canary token, signature, OAuth state)
    ("GET", "/api/agent/download/{tenant_id}"), ("GET", "/api/agent/download/{tenant_id}/msi"),
    ("GET", "/api/agent/download/{tenant_id}/rust-binary"),
    ("GET", "/api/agent/download/{tenant_id}/rust-exe"), ("GET", "/api/agent/install/{tenant_id}"),
    ("GET", "/api/agents/{agent_id}/instructions"), ("POST", "/api/deployments/{job_id}/result"),
    ("PATCH", "/api/patches/deployment-jobs/{job_id}/progress"),
    ("POST", "/api/edr/events"), ("POST", "/api/powershell-evidence/submit"),
    ("POST", "/api/questionnaires/{qid}/responses"), ("POST", "/api/file-share/access/{token}"),
    ("POST", "/api/deception/webhook/trigger/{token_id}"), ("POST", "/api/payments/webhook/stripe"),
    ("POST", "/api/webhooks/jira/inbound"), ("POST", "/api/webhooks/zoho/inbound"),
    ("GET", "/api/saas/callback/{provider}"),
    ("GET", "/api/graphql"), ("POST", "/api/graphql"), ("WS", "/api/graphql"),
    ("WS", "/api/stream/live"),
    # Public content
    ("POST", "/api/cookie-consent/record"), ("GET", "/api/cookie-consent/session/{tenant_id}/{session_id}"),
    ("GET", "/api/public/trust/{slug}"), ("POST", "/api/public/trust/{slug}/requests"),
    ("GET", "/api/ai"), ("GET", "/api/ai/"), ("GET", "/api/ai/skills"),
    ("GET", "/api/compliance/artifacts/categories"),
    # final_endpoints' copy; system_health_endpoints registers the same path first
    # (authenticated), so this one is never reached
    ("GET", "/api/system/health"),
})


@pytest.fixture(scope="module")
def route_walk():
    # The walk runs in a fresh interpreter (see tests/_route_walk.py): other tests
    # reload authentication_service or swap its functions.
    return run_real_app_walk()


@pytest.fixture(scope="module")
def unauthenticated_routes(route_walk):
    return {tuple(r) for r in route_walk["unauthenticated"]}


def test_no_unreviewed_unauthenticated_routes(unauthenticated_routes):
    unexpected = sorted(unauthenticated_routes - REVIEWED_UNAUTHENTICATED)
    assert unexpected == [], (
        "Routes without an auth dependency — add Depends(get_current_user) (or a "
        "permission) or, if public by design, review and list them:\n"
        + "\n".join(f"{m} {p}" for m, p in unexpected)
    )


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/stream/publish/{topic}"), ("GET", "/api/stream/metrics"),
    ("GET", "/api/system/fleet"), ("GET", "/api/system/queues"), ("GET", "/api/system/resources"),
    ("POST", "/api/training/modules"), ("POST", "/api/training/assign"),
    ("PUT", "/api/training/progress/{assignment_id}"), ("GET", "/api/training/my-training"),
    ("POST", "/api/predictive/hosts/{host_id}/acknowledge"),
    ("POST", "/api/agent-updates/build"), ("GET", "/api/agent-updates/build/{task_id}"),
    ("POST", "/api/compliance_oracle/analyze"),
    ("GET", "/api/siem/events"), ("POST", "/api/siem/ingest"), ("GET", "/api/ueba/anomalies"),
    ("GET", "/api/sustainability/metrics"), ("GET", "/api/maturity/domains"),
])
def test_previously_public_routes_now_require_auth(unauthenticated_routes, method, path):
    assert (method, path) not in unauthenticated_routes


# Data-changing routes that only need a login: each acts on the caller's own
# account or records (MFA, passkeys, API keys, to-do tasks, support threads,
# training, file shares they created) or is an AI chat open to every user. Everything
# else that changes data needs a permission.
SELF_SERVICE_WRITES = frozenset({
    ("PUT", "/api/users/me/notification-preferences"),
    # API keys act as their owner and can't exceed the owner's role
    ("POST", "/api/api-keys"), ("DELETE", "/api/api-keys/{key_id}"),
    ("POST", "/api/mfa/setup"), ("POST", "/api/mfa/verify-setup"), ("POST", "/api/mfa/disable"),
    ("POST", "/api/mfa/backup-codes/regenerate"), ("POST", "/api/mfa/step-up"),
    ("POST", "/api/passkey/register/options"), ("POST", "/api/passkey/register/verify"),
    ("DELETE", "/api/passkey/credentials/{credential_id}"),
    ("POST", "/api/tasks"), ("PATCH", "/api/tasks/{task_id}"), ("DELETE", "/api/tasks/{task_id}"),
    ("POST", "/api/support/conversations/{convo_id}/messages"),
    ("POST", "/api/support/conversations/{convo_id}/read"),
    ("PUT", "/api/training/progress/{assignment_id}"),
    ("POST", "/api/training/progress/{assignment_id}/quiz"),
    ("POST", "/api/file-share/shares"), ("DELETE", "/api/file-share/shares/{share_id}"),
    ("POST", "/api/trust-center/requests"), ("POST", "/api/experiments/{experiment_id}/track"),
    ("POST", "/api/provenance/verify"), ("POST", "/api/cissp/oracle/chat"),
    ("POST", "/api/jit/requests"),  # asking for just-in-time access; approval is separate
    ("POST", "/api/voice/transcribe"), ("POST", "/api/voice/synthesize"),
    ("POST", "/api/digital_twin/simulate"),  # read-only what-if estimate; writes nothing
})


def test_data_changing_routes_need_a_permission(route_walk):
    login_only = {tuple(r) for r in route_walk["login_only_writes"]}
    unexpected = sorted(login_only - SELF_SERVICE_WRITES)
    assert unexpected == [], (
        "Data-changing routes that only check for a login — use "
        "Depends(require_permission(...)) or, if they act only on the caller's own "
        "records, list them in SELF_SERVICE_WRITES:\n"
        + "\n".join(f"{m} {p}" for m, p in unexpected)
    )
