"""
AWS CloudTrail SIEM Ingest
Polls configured S3 buckets for CloudTrail log files and ingests them into security_events.
Falls back gracefully when boto3 is not installed or credentials are not configured.
"""

import asyncio
import gzip
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import uuid

from database import get_database

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False
    logger.warning("[CloudTrail] boto3 not installed — AWS CloudTrail ingest disabled")


def _make_s3_client(aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
    if not _BOTO3_AVAILABLE:
        return None
    return boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=region,
    )


def _parse_cloudtrail_record(record: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": record.get("eventTime", datetime.now(timezone.utc).isoformat()),
        "log_type": "aws_cloudtrail",
        "eventSource": record.get("eventSource", ""),
        "eventName": record.get("eventName", ""),
        "awsRegion": record.get("awsRegion", ""),
        "sourceIPAddress": record.get("sourceIPAddress", ""),
        "userAgent": record.get("userAgent", ""),
        "userIdentity": record.get("userIdentity", {}),
        "requestParameters": record.get("requestParameters"),
        "responseElements": record.get("responseElements"),
        "errorCode": record.get("errorCode"),
        "errorMessage": record.get("errorMessage"),
        "severity": "High" if record.get("errorCode") else "Low",
        "raw_message": f"{record.get('eventName', '')} from {record.get('sourceIPAddress', '')}",
    }


async def fetch_cloudtrail_logs(
    tenant_id: str,
    s3_bucket: str,
    aws_access_key: str,
    aws_secret_key: str,
    last_fetch_time: datetime,
    region: str = "us-east-1",
) -> int:
    """
    Fetch CloudTrail logs from S3 written after last_fetch_time.
    Returns count of events ingested.
    """
    if not _BOTO3_AVAILABLE:
        return 0
    if not s3_bucket or aws_access_key in ("", "fake_key", None):
        logger.debug("[CloudTrail] No valid credentials for tenant %s — skipping", tenant_id)
        return 0

    s3 = _make_s3_client(aws_access_key, aws_secret_key, region)
    if not s3:
        return 0

    db = get_database()
    ingested = 0
    prefix = f"AWSLogs/"

    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                last_modified = obj["LastModified"].replace(tzinfo=timezone.utc)
                if last_modified <= last_fetch_time.replace(tzinfo=timezone.utc):
                    continue

                try:
                    response = s3.get_object(Bucket=s3_bucket, Key=obj["Key"])
                    body = response["Body"].read()
                    # CloudTrail logs are gzipped JSON
                    if obj["Key"].endswith(".gz"):
                        body = gzip.decompress(body)
                    data = json.loads(body)
                    records = data.get("Records", [])
                    docs = [_parse_cloudtrail_record(r, tenant_id) for r in records]
                    if docs:
                        await db.security_events.insert_many(docs)
                        ingested += len(docs)
                except Exception as exc:
                    logger.error("[CloudTrail] Failed to read object %s: %s", obj["Key"], exc)

    except (ClientError, NoCredentialsError) as exc:
        logger.error("[CloudTrail] S3 access error for tenant %s: %s", tenant_id, exc)
    except Exception as exc:
        logger.error("[CloudTrail] Unexpected error for tenant %s: %s", tenant_id, exc)

    if ingested:
        logger.info("[CloudTrail] Ingested %d events for tenant %s", ingested, tenant_id)
    return ingested


async def start_aws_polling():
    """Poll every 5 minutes for each configured AWS CloudTrail integration."""
    from tenant_context import set_tenant_id
    while True:
        try:
            set_tenant_id("platform-admin")
            db = get_database()
            configs = await db.siem_configs.find({"provider": "aws_cloudtrail", "enabled": True}).to_list(length=100)
            for config in configs:
                _ct_tid = config.get("tenant_id") or None
                if not _ct_tid:
                    logger.warning("[CloudTrail] Skipping config %s — no tenant_id configured", config.get("id", "?"))
                    continue
                await fetch_cloudtrail_logs(
                    tenant_id=_ct_tid,
                    s3_bucket=config.get("s3_bucket", ""),
                    aws_access_key=config.get("aws_access_key", ""),
                    aws_secret_key=config.get("aws_secret_key", ""),
                    last_fetch_time=datetime.now(timezone.utc) - timedelta(minutes=5),
                    region=config.get("region", "us-east-1"),
                )
        except Exception as exc:
            logger.error("[CloudTrail] Polling loop error: %s", exc)

        await asyncio.sleep(300)
