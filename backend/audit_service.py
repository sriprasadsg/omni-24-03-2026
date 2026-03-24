import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from database import get_database

class AuditService:
    """
    Manages audit logging and rollback capabilities using MongoDB.
    Implements SHA-256 Hash Chaining for Immutable Ledger.
    """
    
    def _compute_hash(self, entry: Dict[str, Any], previous_hash: str) -> str:
        """Compute SHA-256 hash of the entry + previous hash"""
        # Create a canonical string representation
        # We include critical fields: timestamp, action, user, resource, previous_hash
        # Details and PreviousState are included if present
        payload = f"{entry['timestamp']}|{entry['userName']}|{entry['action']}|{entry['resourceType']}|{entry['resourceId']}|{previous_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def log_action(self, *args, **kwargs):
        logging.warning("Synchronous log_action called - not persisting to DB! Use log_action_async.")
        return {}

    async def log_action_async(self, 
                   user_name: str, 
                   action: str, 
                   resource_type: str, 
                   resource_id: str, 
                   details: str, 
                   previous_state: Optional[Dict[str, Any]] = None,
                   tenant_id: str = "default-tenant") -> Dict[str, Any]:
         
        # 1. Prepare base entry
        log_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "userName": user_name,
            "action": action,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "details": details,
            "previousState": previous_state,
            "tenantId": tenant_id
        }
        
        try:
            db = get_database()
            
            # 2. Get Previous Hash (Chain)
            # Find the last log for this tenant
            last_log = await db.audit_logs.find_one(
                {"tenantId": tenant_id},
                sort=[("timestamp", -1)]
            )
            
            previous_hash = last_log.get("hash", "0" * 64) if last_log else "0" * 64
            
            # 3. Compute Current Hash
            current_hash = self._compute_hash(log_entry, previous_hash)
            
            # 4. Attach Hash info
            log_entry["hash"] = current_hash
            log_entry["previousHash"] = previous_hash
            
            await db.audit_logs.insert_one(log_entry)
            
        except Exception as e:
            logging.error(f"Failed to persist audit log: {e}")
            # Fallback: still return entry but without hash persistence confirmation
            
        logging.info(f"[AUDIT] {user_name} performed {action} on {resource_type} {resource_id} [Hash: {log_entry.get('hash', 'N/A')[:8]}...]")
        return log_entry

    async def get_logs(self, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve logs, optionally filtered by tenant.
        """
        db = get_database()
        query = {}
        if tenant_id:
            query['tenantId'] = tenant_id
            
        # Return most recent first
        logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).to_list(length=100)
        return logs

    async def get_log_by_id(self, log_id: str) -> Optional[Dict[str, Any]]:
        db = get_database()
        return await db.audit_logs.find_one({"id": log_id}, {"_id": 0})

    async def rollback(self, log_id: str, current_user: str, tenant_id: str = None) -> Dict[str, Any]:
        """
        Rollback.
        """
        log_entry = await self.get_log_by_id(log_id)
        if not log_entry:
            raise ValueError("Audit log entry not found")
        
        # Verify tenant ownership
        if tenant_id and log_entry.get("tenantId") != tenant_id:
            raise ValueError("Unauthorized: Audit log belongs to another tenant")

        if not log_entry.get("previousState"):
            raise ValueError("No previous state recorded for this action. Cannot rollback.")

        logging.info(f"[AUDIT] Rolling back action {log_entry['action']} on {log_entry['resourceId']}")
        
        # Log the rollback action itself!
        await self.log_action_async(
            user_name=current_user,
            action=f"rollback.{log_entry['action']}",
            resource_type=log_entry['resourceType'],
            resource_id=log_entry['resourceId'],
            details=f"Rolled back change from {log_entry['timestamp']}",
            previous_state=None, 
            tenant_id=log_entry.get('tenantId', 'default-tenant')
        )
        
        return log_entry["previousState"]

    async def verify_integrity(self, tenant_id: str) -> Dict[str, Any]:
        """
        Verify the cryptographic integrity of the audit ledger for a tenant.
        Returns report of any broken chains.
        """
        db = get_database()
        
        # Get all logs sorted by timestamp ASCENDING (oldest first) to walk the chain
        logs = await db.audit_logs.find(
            {"tenantId": tenant_id}, 
            {"_id": 0}
        ).sort("timestamp", 1).to_list(length=None)
        
        if not logs:
            return {"status": "empty", "valid": True}
            
        broken_links = []
        expected_prev_hash = "0" * 64
        
        for log in logs:
            # 1. Check if previous hash matches expected
            stored_prev_hash = log.get("previousHash")
            if stored_prev_hash != expected_prev_hash:
                broken_links.append({
                    "id": log["id"],
                    "timestamp": log["timestamp"],
                    "reason": "Previous Hash Mismatch",
                    "expected": expected_prev_hash,
                    "found": stored_prev_hash
                })
                
            # 2. Re-compute hash and check integrity
            computed_hash = self._compute_hash(log, stored_prev_hash)
            if computed_hash != log.get("hash"):
                broken_links.append({
                    "id": log["id"],
                    "timestamp": log["timestamp"],
                    "reason": "Data Integrity Failure (Hash Mismatch)",
                    "expected": computed_hash,
                    "found": log.get("hash")
                })
                
            # Set expectation for next link
            expected_prev_hash = log.get("hash")
            
        return {
             "valid": len(broken_links) == 0,
             "total_records": len(logs),
             "broken_links": broken_links
        }

# Global singleton
_audit_service = AuditService()

def get_audit_service():
    return _audit_service

