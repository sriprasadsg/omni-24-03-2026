"""HADRService backup operations mixin: create, verify, and restore backups."""

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


class HADRServiceBackupMixin:
    """Backup creation, verification, and restore logic for HADRService."""

    async def create_backup(
        self,
        backup_type: str = "full",
        collections: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a database backup (full, incremental, or differential)."""
        backup_id = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{backup_type}"

        backup_metadata = {
            "backup_id": backup_id,
            "backup_type": backup_type,
            "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "collections": collections or [],
            "tenant_id": tenant_id,
            "size_bytes": 0,
            "encrypted": self.encryption_enabled,
            "checksum": None,
            "error": None,
        }

        await self.db.backup_metadata.insert_one(backup_metadata.copy())

        try:
            if collections is None:
                collections = await self.db.list_collection_names()

            backup_data = {}
            total_size = 0

            for collection_name in collections:
                self.logger.info("Backing up collection: %s", collection_name)
                query = {}
                if tenant_id:
                    query["tenantId"] = tenant_id
                cursor = self.db[collection_name].find(query)
                documents = await cursor.to_list(length=1000)
                for doc in documents:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                backup_data[collection_name] = documents
                total_size += len(json.dumps(documents).encode("utf-8"))

            backup_file = self.backup_dir / f"{backup_id}.json.gz"
            with gzip.open(backup_file, "wt", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)

            checksum = self._calculate_checksum(backup_file)

            if self.encryption_enabled:
                backup_file = self._encrypt_backup(backup_file)

            backup_metadata.update({
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "size_bytes": total_size,
                "file_path": str(backup_file),
                "checksum": checksum,
            })
            await self.db.backup_metadata.update_one(
                {"backup_id": backup_id}, {"$set": backup_metadata}
            )
            self.logger.info("Backup completed: %s, Size: %d bytes", backup_id, total_size)
            return backup_metadata

        except Exception as e:
            self.logger.error("Backup failed: %s", e)
            await self.db.backup_metadata.update_one(
                {"backup_id": backup_id},
                {"$set": {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }},
            )
            raise

    async def verify_backup(self, backup_id: str) -> Dict[str, Any]:
        """Verify backup integrity (file exists, checksum, readable, encryption valid)."""
        backup = await self.db.backup_metadata.find_one({"backup_id": backup_id})
        if not backup:
            raise ValueError(f"Backup not found: {backup_id}")

        result: Dict[str, Any] = {
            "backup_id": backup_id,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "checks": {},
            "valid": True,
            "errors": [],
        }

        try:
            backup_file = Path(backup["file_path"])

            if not backup_file.exists():
                result["checks"]["file_exists"] = False
                result["valid"] = False
                result["errors"].append("Backup file not found")
            else:
                result["checks"]["file_exists"] = True

            current_checksum = self._calculate_checksum(backup_file)
            if current_checksum != backup.get("checksum"):
                result["checks"]["checksum_valid"] = False
                result["valid"] = False
                result["errors"].append("Checksum mismatch - backup may be corrupted")
            else:
                result["checks"]["checksum_valid"] = True

            try:
                test_file = self._decrypt_backup(backup_file) if backup.get("encrypted") else backup_file
                with gzip.open(test_file, "rt", encoding="utf-8") as f:
                    data = json.load(f)
                result["checks"]["data_readable"] = True
                result["checks"]["collections_count"] = len(data)
            except Exception as e:
                result["checks"]["data_readable"] = False
                result["valid"] = False
                result["errors"].append(f"Cannot read backup data: {e}")

            if result["valid"]:
                await self.db.backup_metadata.update_one(
                    {"backup_id": backup_id},
                    {"$set": {"status": "verified", "verified_at": result["verified_at"]}},
                )
            return result

        except Exception as e:
            self.logger.error("Backup verification failed: %s", e)
            result["valid"] = False
            result["errors"].append(str(e))
            return result

    async def restore_backup(
        self,
        backup_id: str,
        collections: Optional[List[str]] = None,
        point_in_time: Optional[datetime] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Restore from a completed or verified backup."""
        backup = await self.db.backup_metadata.find_one({"backup_id": backup_id})
        if not backup:
            raise ValueError(f"Backup not found: {backup_id}")
        if backup["status"] not in ("completed", "verified"):
            raise ValueError(f"Backup is not in a restorable state: {backup['status']}")

        result: Dict[str, Any] = {
            "backup_id": backup_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "dry_run": dry_run,
            "collections_restored": [],
            "documents_restored": 0,
            "errors": [],
        }

        try:
            verification = await self.verify_backup(backup_id)
            if not verification["valid"]:
                raise ValueError(f"Backup verification failed: {verification['errors']}")

            backup_file = Path(backup["file_path"])
            data_file = self._decrypt_backup(backup_file) if backup.get("encrypted") else backup_file

            with gzip.open(data_file, "rt", encoding="utf-8") as f:
                backup_data = json.load(f)

            for collection_name in (collections or list(backup_data.keys())):
                if collection_name not in backup_data:
                    result["errors"].append(f"Collection not found in backup: {collection_name}")
                    continue
                documents = backup_data[collection_name]
                if not dry_run and documents:
                    await self.db[collection_name].insert_many(documents)
                result["collections_restored"].append(collection_name)
                result["documents_restored"] += len(documents)
                self.logger.info("Restored %d documents to %s", len(documents), collection_name)

            result["completed_at"] = datetime.now(timezone.utc).isoformat()
            result["success"] = True
            await self.db.restoration_log.insert_one(result.copy())
            return result

        except Exception as e:
            self.logger.error("Restoration failed: %s", e)
            result["completed_at"] = datetime.now(timezone.utc).isoformat()
            result["success"] = False
            result["errors"].append(str(e))
            return result
