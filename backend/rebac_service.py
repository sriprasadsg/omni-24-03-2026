"""ReBAC (Relationship-Based Access Control) Service using OpenFGA.

This service provides a Python wrapper around the OpenFGA client for
Zanzibar-style authorization checks.
"""

import os
from typing import Optional, List, Dict, Any
from openfga_sdk import OpenFgaClient, ClientConfiguration
from openfga_sdk.models import (
    TupleKey,
    WriteRequest,
    CheckRequest,
    ListObjectsRequest,
    Tuple,
)


class ReBACService:
    """Service for managing ReBAC policies via OpenFGA."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        store_id: Optional[str] = None,
        authorization_model_id: Optional[str] = None,
    ):
        self.api_url = api_url or os.getenv("OPENFGA_API_URL", "http://localhost:8080")
        self.store_id = store_id or os.getenv("OPENFGA_STORE_ID", "")
        self.authorization_model_id = authorization_model_id or os.getenv(
            "OPENFGA_AUTHORIZATION_MODEL_ID", ""
        )

        self._client: Optional[OpenFgaClient] = None

    @property
    def client(self) -> OpenFgaClient:
        """Lazy-initialized OpenFGA client."""
        if self._client is None:
            config = ClientConfiguration(
                api_url=self.api_url,
                store_id=self.store_id,
                authorization_model_id=self.authorization_model_id,
            )
            self._client = OpenFgaClient(config)
        return self._client

    async def check_permission(
        self,
        user: str,
        relation: str,
        object_type: str,
        object_id: str,
    ) -> bool:
        """Check if user has a specific relation on an object."""
        request = CheckRequest(
            user=user,
            relation=relation,
            object=f"{object_type}:{object_id}",
        )
        try:
            response = await self.client.check(request)
            return response.allowed
        except Exception as e:
            print(f"ReBAC check failed: {e}")
            return False

    async def write_tuples(self, tuples: List[Tuple]) -> bool:
        """Write relationship tuples to OpenFGA."""
        request = WriteRequest(writes=tuples)
        try:
            await self.client.write(request)
            return True
        except Exception as e:
            print(f"ReBAC write failed: {e}")
            return False

    async def delete_tuples(self, tuples: List[Tuple]) -> bool:
        """Delete relationship tuples from OpenFGA."""
        request = WriteRequest(deletes=tuples)
        try:
            await self.client.write(request)
            return True
        except Exception as e:
            print(f"ReBAC delete failed: {e}")
            return False

    async def list_objects(
        self,
        user: str,
        relation: str,
        object_type: str,
    ) -> List[str]:
        """List objects of a given type that the user has a relation to."""
        request = ListObjectsRequest(
            user=user,
            relation=relation,
            type=object_type,
        )
        try:
            response = await self.client.list_objects(request)
            return response.objects or []
        except Exception as e:
            print(f"ReBAC list_objects failed: {e}")
            return []


# ComplianceControl resource type for pilot
COMPLIANCE_CONTROL_TYPE = "compliance_control"


def create_compliance_control_tuple(
    user: str,
    relation: str,
    object_id: str,
) -> Tuple:
    """Create a tuple for a ComplianceControl resource."""
    return Tuple(
        key=TupleKey(
            user=user,
            relation=relation,
            object=f"{COMPLIANCE_CONTROL_TYPE}:{object_id}",
        )
    )


async def grant_compliance_control_access(
    service: ReBACService,
    user: str,
    relation: str,
    object_id: str,
) -> bool:
    """Grant a user a relation on a ComplianceControl."""
    tuple_obj = create_compliance_control_tuple(user, relation, object_id)
    return await service.write_tuples([tuple_obj])


async def revoke_compliance_control_access(
    service: ReBACService,
    user: str,
    relation: str,
    object_id: str,
) -> bool:
    """Revoke a user's relation on a ComplianceControl."""
    tuple_obj = create_compliance_control_tuple(user, relation, object_id)
    return await service.delete_tuples([tuple_obj])


# Global service instance
_reback_service: Optional[ReBACService] = None


def get_reback_service() -> ReBACService:
    """Get or create the global ReBAC service instance."""
    global _reback_service
    if _reback_service is None:
        _reback_service = ReBACService()
    return _reback_service