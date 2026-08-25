"""HADRService backup operations mixin: create, verify, and restore backups."""

import gzip
from bson import json_util
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
                backup_data[collection_name] = documents
                total_size += len(json_util.dumps(documents).encode("utf-8"))

            # DB-F07 (2026-08-25 audit): plain json.dump/json.load cannot
            # round-trip BSON types — ObjectId, datetime, Decimal128, etc.
            # The old code manually stringified _id before dumping, which
            # avoided a crash but silently broke restores: insert_many() on
            # a document whose _id is the *string* "507f1f..." instead of
            # an ObjectId means any later ObjectId(_id) lookup against the
            # restored data finds nothing, even though restore_backup
            # reports success. bson.json_util uses MongoDB Extended JSON
            # and correctly restores ObjectId/datetime/etc. to their native
            # types on load, for every field, not just _id.
            backup_file = self.backup_dir / f"{backup_id}.json.gz"
            with gzip.open(backup_file, "wt", encoding="utf-8") as f:
                f.write(json_util.dumps(backup_data, indent=2))

            # Checksum the file exactly as it will sit at rest — computing it
            # *before* encryption (the old order) meant verify_backup, which
            # always checksums whatever file_path currently points to (the
            # encrypted .enc file once encryption_enabled), compared an
            # encrypted-bytes checksum against a plaintext-bytes checksum
            # and reported "corrupted" on every single encrypted backup.
            # encryption_enabled defaults to True, so this broke verification
            # (and therefore restore_backup, which verifies first) for the
            # default configuration, independent of the BSON fix above.
            if self.encryption_enabled:
                backup_file = self._encrypt_backup(backup_file)

            checksum = self._calculate_checksum(backup_file)

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
                # DB-F07 (2026-08-25 audit): verification must be read-only.
                # _decrypt_backup() writes a decrypted copy to disk *and
                # deletes the original .enc file* — calling it here used to
                # consume the canonical backup artifact just to check it was
                # readable, so restore_backup's own subsequent _decrypt_backup
                # call (on the same file_path) always hit a FileNotFoundError,
                # since verify_backup (which restore_backup always calls
                # first) had already deleted the .enc file out from under it.
                # Decrypting into memory here, without touching the file on
                # disk, keeps this check side-effect-free.
                if backup.get("encrypted"):
                    raw_bytes = self._cipher.decrypt(backup_file.read_bytes())
                    data = json_util.loads(gzip.decompress(raw_bytes).decode("utf-8"))
                else:
                    with gzip.open(backup_file, "rt", encoding="utf-8") as f:
                        data = json_util.loads(f.read())
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
                backup_data = json_util.loads(f.read())

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
