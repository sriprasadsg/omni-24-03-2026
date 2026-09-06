"""Regression tests for DB-F07 (2026-08-25 audit): HADR backup/restore must
round-trip BSON types correctly, not just avoid crashing on json.dump.

The old code used plain json.dump/json.load and manually stringified _id
before dumping to dodge the "ObjectId not JSON serializable" crash. That
avoided the crash but silently broke restores: insert_many() re-inserted
documents whose _id was the *string* "507f1f77bcf86cd799439011" instead of
an ObjectId, so any later ObjectId(_id) lookup against the restored data
would find nothing — restore_backup still reported success. bson.json_util
(MongoDB Extended JSON) round-trips ObjectId, datetime, and other BSON
types back to their native Python types on load.

Also covers two bugs found alongside it in the same file, both of which
made the (default-enabled) encrypted-backup restore path completely
non-functional: the backup checksum was computed *before* encryption while
verify_backup always checksums the *encrypted* file, so every encrypted
backup failed verification; and verify_backup's readability check called
_decrypt_backup(), which deletes the original .enc file as a side effect,
so restore_backup's own subsequent decrypt attempt (after calling
verify_backup first) always hit a FileNotFoundError.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId

from hadr_service import HADRService


def _make_service(tmp_path, encryption_enabled=False):
    db = MagicMock()
    db.backup_metadata.insert_one = AsyncMock()
    db.backup_metadata.update_one = AsyncMock()
    db.backup_metadata.find_one = AsyncMock()
    db.restoration_log.insert_one = AsyncMock()
    svc = HADRService(db=db, backup_dir=str(tmp_path))
    svc.encryption_enabled = encryption_enabled
    return svc, db


def _make_cursor(documents):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=documents)
    return cursor


@pytest.mark.asyncio
async def test_object_id_survives_backup_and_restore_as_real_objectid(tmp_path):
    svc, db = _make_service(tmp_path)
    real_id = ObjectId()
    doc = {"_id": real_id, "name": "widget", "tenantId": "t1"}

    db.list_collection_names = AsyncMock(return_value=["assets"])
    db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=_make_cursor([doc]))))

    metadata = await svc.create_backup(collections=["assets"])
    assert metadata["status"] == "completed"

    db.backup_metadata.find_one = AsyncMock(return_value=metadata)
    insert_many_calls = []
    db.__getitem__ = MagicMock(
        return_value=MagicMock(insert_many=AsyncMock(side_effect=lambda docs: insert_many_calls.append(docs)))
    )

    result = await svc.restore_backup("assets-backup", collections=["assets"])
    assert result["success"] is True
    assert result["errors"] == []

    restored_docs = insert_many_calls[0]
    assert len(restored_docs) == 1
    restored_id = restored_docs[0]["_id"]
    assert isinstance(restored_id, ObjectId)
    assert restored_id == real_id


@pytest.mark.asyncio
async def test_datetime_field_survives_backup_and_restore(tmp_path):
    svc, db = _make_service(tmp_path)
    real_dt = datetime(2026, 8, 25, 12, 30, 0, tzinfo=timezone.utc)
    doc = {"_id": ObjectId(), "expiresAt": real_dt}

    db.list_collection_names = AsyncMock(return_value=["licenses"])
    db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=_make_cursor([doc]))))

    metadata = await svc.create_backup(collections=["licenses"])
    db.backup_metadata.find_one = AsyncMock(return_value=metadata)

    insert_many_calls = []
    db.__getitem__ = MagicMock(
        return_value=MagicMock(insert_many=AsyncMock(side_effect=lambda docs: insert_many_calls.append(docs)))
    )
    await svc.restore_backup("licenses-backup", collections=["licenses"])

    restored_dt = insert_many_calls[0][0]["expiresAt"]
    assert isinstance(restored_dt, datetime)
    # BSON's Date type has no timezone component (always UTC millis since
    # epoch) — bson.json_util correctly round-trips it as a naive UTC
    # datetime, matching what a real MongoDB find() would also return.
    assert restored_dt.replace(tzinfo=timezone.utc) == real_dt


@pytest.mark.asyncio
async def test_roundtrip_survives_encryption(tmp_path):
    """Encryption is orthogonal to serialization — confirm the BSON
    round-trip still holds through the encrypt/decrypt path too."""
    svc, db = _make_service(tmp_path, encryption_enabled=True)
    real_id = ObjectId()
    doc = {"_id": real_id, "name": "encrypted-widget"}

    db.list_collection_names = AsyncMock(return_value=["assets"])
    db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=_make_cursor([doc]))))

    metadata = await svc.create_backup(collections=["assets"])
    assert metadata["file_path"].endswith(".enc")
    db.backup_metadata.find_one = AsyncMock(return_value=metadata)

    insert_many_calls = []
    db.__getitem__ = MagicMock(
        return_value=MagicMock(insert_many=AsyncMock(side_effect=lambda docs: insert_many_calls.append(docs)))
    )
    result = await svc.restore_backup("assets-backup", collections=["assets"])

    assert result["success"] is True
    assert insert_many_calls[0][0]["_id"] == real_id


@pytest.mark.asyncio
async def test_verify_backup_is_non_destructive_and_repeatable(tmp_path):
    """verify_backup used to decrypt the .enc file to a plaintext copy and
    delete the original — a read-only check with a destructive side effect.
    That both broke idempotency (a second verify would find no .enc file)
    and broke restore_backup (which calls verify_backup first, then tries
    to decrypt the same now-deleted .enc file itself)."""
    svc, db = _make_service(tmp_path, encryption_enabled=True)
    doc = {"_id": ObjectId(), "name": "widget"}
    db.list_collection_names = AsyncMock(return_value=["assets"])
    db.__getitem__ = MagicMock(return_value=MagicMock(find=MagicMock(return_value=_make_cursor([doc]))))

    metadata = await svc.create_backup(collections=["assets"])
    db.backup_metadata.find_one = AsyncMock(return_value=metadata)
    enc_path = Path(metadata["file_path"])
    assert enc_path.exists()

    first = await svc.verify_backup("assets-backup")
    assert first["valid"] is True
    assert enc_path.exists()  # not deleted by verification

    second = await svc.verify_backup("assets-backup")
    assert second["valid"] is True
    assert enc_path.exists()
