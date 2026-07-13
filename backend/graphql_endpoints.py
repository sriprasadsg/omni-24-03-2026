from fastapi import APIRouter, Depends, Request, Response
from strawberry.fastapi import GraphQLRouter
from backend.graphql.schema import schema
from authentication_service import get_current_user
from auth_types import TokenData
from typing import Any

class CustomGraphQLRouter(GraphQLRouter):
    async def get_context(self, request: Request, response: Response) -> Any:
        # Get user from FastAPI's dependency injection
        current_user = await get_current_user(request)
        return {
            "request": request,
            "response": response,
            "current_user": current_user,
            "tenant_id": getattr(current_user, "tenant_id", None)
        }

# GraphQLRouter is already a Starlette Router (not a FastAPI APIRouter)
# Export it directly for router_registry.py
router = CustomGraphQLRouter(schema, path="/api/graphql")