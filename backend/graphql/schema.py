import strawberry
from typing import List, Optional
from backend.graphql.types import ComplianceControl, Evidence, Risk
from backend.graphql.resolvers import get_compliance_controls, get_evidence_items, get_risks

@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello World"

    @strawberry.field
    async def compliance_controls(self, info) -> List:
        return await get_compliance_controls(info)

    @strawberry.field
    async def evidence_items(self, info) -> List:
        return await get_evidence_items(info)

    @strawberry.field
    async def risks(self, info) -> List:
        return await get_risks(info)

    @strawberry.field
    async def users(self, info) -> List:
        return await get_users(info)

    @strawberry.field
    async def tenants(self, info) -> List:
        return await get_tenants(info)

schema = strawberry.Schema(query=Query)