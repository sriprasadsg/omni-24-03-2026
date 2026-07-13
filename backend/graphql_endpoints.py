"""GraphQL endpoint — mounts the strawberry schema at /api/graphql.

Auth model: the bearer token is resolved to a user ONCE here via
context_getter (strawberry's constructor hook — subclass get_context
methods are NOT called by the fastapi router). Unauthenticated requests
get current_user=None; every resolver enforces its own auth/RBAC and
returns empty results rather than erroring, so introspection and the
hello field remain publicly reachable without leaking data.
"""
from fastapi import Request
from strawberry.fastapi import GraphQLRouter
from graphql_api.schema import schema
from authentication_service import get_current_user
from typing import Any, Dict


async def _graphql_context(request: Request) -> Dict[str, Any]:
    # get_current_user takes the bearer TOKEN, not the Request — extract it
    # from the Authorization header and resolve the user here.
    auth_header = request.headers.get("authorization", "")
    current_user = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            current_user = await get_current_user(token)
        except Exception:
            current_user = None
    return {
        "current_user": current_user,
        "tenant_id": getattr(current_user, "tenant_id", None),
    }


router = GraphQLRouter(schema, path="/api/graphql", context_getter=_graphql_context)
