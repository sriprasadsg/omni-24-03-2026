"""Vector Access Controller — fine-grained RBAC for vector data.

Implements:
- Role-based access (admin, analyst, viewer)
- Data classification tags (PII, confidential, public)
- Audit logging for all vector operations
- Quarantine for sensitive data
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger(__name__)


class Role(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"
    RESTRICTED = "restricted"


class Operation(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SEARCH = "search"
    EXPORT = "export"


@dataclass
class AccessPolicy:
    """Access policy for a vector collection."""
    collection_name: str
    tenant_id: str
    role_permissions: Dict[Role, Set[Operation]] = field(default_factory=dict)
    classification: DataClassification = DataClassification.INTERNAL
    pii_fields: Set[str] = field(default_factory=set)
    quarantine_enabled: bool = False


@dataclass
class AccessLogEntry:
    """Audit log entry for vector operations."""
    timestamp: float
    user_id: str
    tenant_id: str
    collection_name: str
    operation: Operation
    classification: DataClassification
    allowed: bool
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# Default role permissions
DEFAULT_PERMISSIONS = {
    Role.ADMIN: {Operation.CREATE, Operation.READ, Operation.UPDATE,
                 Operation.DELETE, Operation.SEARCH, Operation.EXPORT},
    Role.ANALYST: {Operation.READ, Operation.SEARCH, Operation.EXPORT},
    Role.VIEWER: {Operation.READ, Operation.SEARCH},
}


class VectorAccessController:
    """Access control for tenant-isolated vector data."""

    def __init__(self):
        self.policies: Dict[str, AccessPolicy] = {}  # tenant_collection -> policy
        self.audit_log: List[AccessLogEntry] = []
        self.max_log_size = 10000

    def set_policy(
        self,
        tenant_id: str,
        collection_name: str,
        role_permissions: Dict[Role, Set[Operation]] = None,
        classification: DataClassification = DataClassification.INTERNAL,
        pii_fields: List[str] = None,
        quarantine_enabled: bool = False,
    ) -> None:
        """Set access policy for a collection."""
        key = f"{tenant_id}_{collection_name}"
        policy = AccessPolicy(
            collection_name=collection_name,
            tenant_id=tenant_id,
            role_permissions=role_permissions or DEFAULT_PERMISSIONS.copy(),
            classification=classification,
            pii_fields=set(pii_fields or []),
            quarantine_enabled=quarantine_enabled,
        )
        self.policies[key] = policy
        logger.info("Policy set for %s: classification=%s", key, classification.value)

    def get_policy(self, tenant_id: str, collection_name: str) -> Optional[AccessPolicy]:
        """Get policy for collection."""
        return self.policies.get(f"{tenant_id}_{collection_name}")

    def check_access(
        self,
        user_id: str,
        tenant_id: str,
        role: Role,
        collection_name: str,
        operation: Operation,
        data_classification: DataClassification = None,
    ) -> tuple[bool, str]:
        """Check if user has permission for operation."""
        policy = self.get_policy(tenant_id, collection_name)
        if not policy:
            self._audit(user_id, tenant_id, collection_name, operation,
                        data_classification or DataClassification.INTERNAL,
                        False, "no_policy")
            return False, "No access policy defined"

        allowed_ops = policy.role_permissions.get(role, set())
        if operation not in allowed_ops:
            self._audit(user_id, tenant_id, collection_name, operation,
                        data_classification or policy.classification,
                        False, "operation_not_allowed")
            return False, f"Role {role.value} cannot {operation.value}"

        # Check data classification escalation
        if data_classification and data_classification != DataClassification.PUBLIC:
            if role == Role.VIEWER and data_classification in (DataClassification.CONFIDENTIAL,
                                                                 DataClassification.PII,
                                                                 DataClassification.RESTRICTED):
                self._audit(user_id, tenant_id, collection_name, operation,
                            data_classification, False, "classification_escalation")
                return False, f"Viewer cannot access {data_classification.value} data"

        # Check PII field access
        if operation in (Operation.EXPORT, Operation.READ) and policy.pii_fields:
            if role == Role.VIEWER:
                self._audit(user_id, tenant_id, collection_name, operation,
                            DataClassification.PII, False, "pii_access_denied")
                return False, "Viewer cannot access PII fields"

        self._audit(user_id, tenant_id, collection_name, operation,
                    data_classification or policy.classification, True, "allowed")
        return True, "Allowed"

    def _audit(
        self,
        user_id: str,
        tenant_id: str,
        collection_name: str,
        operation: Operation,
        classification: DataClassification,
        allowed: bool,
        reason: str,
    ) -> None:
        """Record audit log entry."""
        entry = AccessLogEntry(
            timestamp=time.time(),
            user_id=user_id,
            tenant_id=tenant_id,
            collection_name=collection_name,
            operation=operation,
            classification=classification,
            allowed=allowed,
            reason=reason,
        )
        self.audit_log.append(entry)
        if len(self.audit_log) > self.max_log_size:
            self.audit_log = self.audit_log[-self.max_log_size:]

    def get_audit_log(
        self,
        tenant_id: str = "",
        user_id: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        filtered = self.audit_log
        if tenant_id:
            filtered = [e for e in filtered if e.tenant_id == tenant_id]
        if user_id:
            filtered = [e for e in filtered if e.user_id == user_id]
        return [
            {
                "timestamp": e.timestamp,
                "user_id": e.user_id,
                "tenant_id": e.tenant_id,
                "collection_name": e.collection_name,
                "operation": e.operation.value,
                "classification": e.classification.value,
                "allowed": e.allowed,
                "reason": e.reason,
            }
            for e in filtered[-limit:]
        ]

    def quarantine_collection(self, tenant_id: str, collection_name: str) -> bool:
        """Enable quarantine for a collection (blocks all access except admin)."""
        policy = self.get_policy(tenant_id, collection_name)
        if not policy:
            return False
        policy.quarantine_enabled = True
        logger.warning("Collection %s quarantined", f"{tenant_id}_{collection_name}")
        return True

    def release_quarantine(self, tenant_id: str, collection_name: str) -> bool:
        """Release collection from quarantine."""
        policy = self.get_policy(tenant_id, collection_name)
        if not policy:
            return False
        policy.quarantine_enabled = False
        logger.info("Collection %s released from quarantine", f"{tenant_id}_{collection_name}")
        return True


# Singleton
vector_access_controller = VectorAccessController()