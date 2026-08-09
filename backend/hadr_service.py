"""
High Availability & Disaster Recovery Service

Provides comprehensive HA/DR capabilities:
- Automated database backups (daily full, hourly incremental)
- Backup encryption and verification
- Point-in-time recovery
- Failover automation
- Health monitoring
- DR testing and validation
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import hashlib
import logging
import os
from pathlib import Path
from cryptography.fernet import Fernet

from hadr_service_backup import HADRServiceBackupMixin


class BackupType:
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"


class BackupStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


class HADRService(HADRServiceBackupMixin):
    """High Availability and Disaster Recovery Service."""

    def __init__(self, db: AsyncIOMotorDatabase, backup_dir: str = "./backups"):
        self.db = db
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("HADRService")

        self.rto_minutes = 15
        self.rpo_hours = 1
        self.backup_retention_days = 30
        self.encryption_enabled = True

        key_path = self.backup_dir / "backup.key"
        raw_key = os.environ.get("BACKUP_ENCRYPTION_KEY")
        if raw_key:
            self._cipher = Fernet(raw_key.encode())
        elif key_path.exists():
            self._cipher = Fernet(key_path.read_bytes())
        else:
            new_key = Fernet.generate_key()
            key_path.write_bytes(new_key)
            self._cipher = Fernet(new_key)

    async def schedule_backups(self) -> Dict[str, Any]:
        """Set up automated backup schedule (full daily, incremental hourly)."""
        schedule = {
            "full_backup": {
                "frequency": "daily",
                "time": "02:00",
                "retention_days": self.backup_retention_days,
            },
            "incremental_backup": {
                "frequency": "hourly",
                "retention_days": 7,
            },
        }
        await self.db.backup_schedule.update_one(
            {"_id": "default"}, {"$set": schedule}, upsert=True
        )
        return schedule

    async def cleanup_old_backups(self) -> Dict[str, Any]:
        """Clean up backups older than the retention period."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.backup_retention_days)
        cursor = self.db.backup_metadata.find({
            "started_at": {"$lt": cutoff_date.isoformat()},
            "status": {"$in": [BackupStatus.COMPLETED, BackupStatus.VERIFIED]},
        })
        deleted_count = 0
        freed_bytes = 0
        async for backup in cursor:
            try:
                backup_file = Path(backup["file_path"])
                if backup_file.exists():
                    freed_bytes += backup_file.stat().st_size
                    backup_file.unlink()
                await self.db.backup_metadata.delete_one({"backup_id": backup["backup_id"]})
                deleted_count += 1
                self.logger.info("Deleted old backup: %s", backup["backup_id"])
            except Exception as e:
                self.logger.error("Failed to delete backup %s: %s", backup["backup_id"], e)
        return {
            "deleted_count": deleted_count,
            "freed_bytes": freed_bytes,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        }

    async def get_backup_status(self) -> Dict[str, Any]:
        """Get overall backup status and RPO compliance."""
        pipeline = [
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "total_size": {"$sum": "$size_bytes"},
            }}
        ]
        cursor = self.db.backup_metadata.aggregate(pipeline)
        status_counts: Dict[str, Any] = {}
        total_size = 0
        async for result in cursor:
            status_counts[result["_id"]] = {
                "count": result["count"],
                "size_bytes": result.get("total_size", 0),
            }
            total_size += result.get("total_size", 0)

        latest_backup = await self.db.backup_metadata.find_one(
            {"status": BackupStatus.COMPLETED}, sort=[("started_at", -1)]
        )
        rpo_compliant = False
        if latest_backup:
            latest_time = datetime.fromisoformat(latest_backup["started_at"])
            rpo_compliant = datetime.now(timezone.utc) - latest_time < timedelta(hours=self.rpo_hours)

        return {
            "status_counts": status_counts,
            "total_size_bytes": total_size,
            "total_size_gb": round(total_size / (1024 ** 3), 2),
            "latest_backup": latest_backup.get("backup_id") if latest_backup else None,
            "latest_backup_time": latest_backup.get("started_at") if latest_backup else None,
            "rpo_compliant": rpo_compliant,
            "rpo_hours": self.rpo_hours,
            "rto_minutes": self.rto_minutes,
        }

    async def test_disaster_recovery(self) -> Dict[str, Any]:
        """Validate DR: find latest backup, verify it, dry-run restore, and check RTO."""
        test_result: Dict[str, Any] = {
            "test_id": f"dr_test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "tests": {},
            "rto_achieved": False,
            "success": False,
        }
        start_time = datetime.now(timezone.utc)

        try:
            latest_backup = await self.db.backup_metadata.find_one(
                {"status": {"$in": [BackupStatus.COMPLETED, BackupStatus.VERIFIED]}},
                sort=[("started_at", -1)],
            )
            if not latest_backup:
                test_result["tests"]["backup_available"] = False
                test_result["errors"] = ["No backup available for testing"]
                return test_result

            test_result["tests"]["backup_available"] = True
            test_result["backup_id"] = latest_backup["backup_id"]

            verification = await self.verify_backup(latest_backup["backup_id"])
            test_result["tests"]["backup_valid"] = verification["valid"]
            if not verification["valid"]:
                test_result["errors"] = verification["errors"]
                return test_result

            restore_result = await self.restore_backup(
                backup_id=latest_backup["backup_id"], dry_run=True
            )
            test_result["tests"]["restore_successful"] = restore_result["success"]
            test_result["documents_tested"] = restore_result["documents_restored"]

            duration_minutes = (datetime.now(timezone.utc) - start_time).total_seconds() / 60
            test_result["duration_minutes"] = round(duration_minutes, 2)
            test_result["rto_achieved"] = duration_minutes <= self.rto_minutes
            test_result["success"] = all([
                test_result["tests"]["backup_available"],
                test_result["tests"]["backup_valid"],
                test_result["tests"]["restore_successful"],
                test_result["rto_achieved"],
            ])
            test_result["completed_at"] = datetime.now(timezone.utc).isoformat()
            await self.db.dr_test_log.insert_one(test_result.copy())
            return test_result

        except Exception as e:
            self.logger.error("DR test failed: %s", e)
            test_result["completed_at"] = datetime.now(timezone.utc).isoformat()
            test_result["success"] = False
            test_result["errors"] = [str(e)]
            return test_result

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _encrypt_backup(self, file_path: Path) -> Path:
        """Encrypt backup file with AES-256 (Fernet) and write to <file>.enc."""
        encrypted_path = file_path.with_suffix(file_path.suffix + ".enc")
        encrypted_path.write_bytes(self._cipher.encrypt(file_path.read_bytes()))
        file_path.unlink()
        return encrypted_path

    def _decrypt_backup(self, file_path: Path) -> Path:
        """Decrypt an AES-256 (Fernet) encrypted backup file."""
        if file_path.suffix != ".enc":
            return file_path
        decrypted_path = file_path.with_suffix("")
        decrypted_path.write_bytes(self._cipher.decrypt(file_path.read_bytes()))
        file_path.unlink()
        return decrypted_path


_hadr_service: Optional[HADRService] = None


def get_hadr_service(db: AsyncIOMotorDatabase) -> Optional[HADRService]:
    """Get or create the HA/DR service singleton. Returns None if initialization fails."""
    global _hadr_service
    if _hadr_service is None:
        try:
            _hadr_service = HADRService(db)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to initialize HADRService: %s", e)
            _hadr_service = None # Ensure it's explicitly None on failure
    return _hadr_service
