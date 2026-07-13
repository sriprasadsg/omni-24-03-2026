import strawberry
from typing import List
from strawberry.types import Info
from graphql_api.types import ComplianceControl, Evidence, Risk, User, Tenant
from graphql_api.resolvers import (
    get_compliance_controls,
    get_evidence_items,
    get_risks,
    get_users,
    get_tenants,
)


@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        return "Hello World"

    @strawberry.field
    async def compliance_controls(self, info: Info) -> List[ComplianceControl]:
        return await get_compliance_controls(info)

    @strawberry.field
    async def evidence_items(self, info: Info) -> List[Evidence]:
        return await get_evidence_items(info)

    @strawberry.field
    async def risks(self, info: Info) -> List[Risk]:
        return await get_risks(info)

    @strawberry.field
    async def users(self, info: Info) -> List[User]:
        return await get_users(info)

    @strawberry.field
    async def tenants(self, info: Info) -> List[Tenant]:
        return await get_tenants(info)


schema = strawberry.Schema(query=Query)
