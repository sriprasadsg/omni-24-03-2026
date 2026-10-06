"""Single source of truth for the deployment environment.

Security-relevant behaviour (refusing placeholder/weak secrets, hiding the API
docs and schema, restricting Socket.IO origins, refusing the mock database)
used to key off two different variables, ENVIRONMENT and APP_ENV, each
defaulting to "development". Deployments that set neither, including the
shipped Helm chart, silently ran with the development fallbacks.

Now ENVIRONMENT is the variable (APP_ENV is honoured as a legacy alias) and an
unset value means production: the default fails closed. Local development and
test runs opt out explicitly with ENVIRONMENT=development (or dev/local/test/ci).
"""
import os

DEV_ENVIRONMENTS = frozenset({"development", "dev", "local", "test", "testing", "ci"})


def environment() -> str:
    """Normalised environment name; "production" when nothing is set."""
    raw = os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "production"
    return raw.strip().lower() or "production"


def is_production() -> bool:
    """True for every environment that is not explicitly a development one
    (production, staging, unrecognised or unset)."""
    return environment() not in DEV_ENVIRONMENTS
