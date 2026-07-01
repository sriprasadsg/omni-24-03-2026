# backend/cloud_checks/__init__.py
from .aws import AWS_CHECKS
from .azure import AZURE_CHECKS
from .gcp import GCP_CHECKS

CLOUD_CHECKS = {}
CLOUD_CHECKS.update(AWS_CHECKS)
CLOUD_CHECKS.update(AZURE_CHECKS)
CLOUD_CHECKS.update(GCP_CHECKS)

__all__ = ["CLOUD_CHECKS", "AWS_CHECKS", "AZURE_CHECKS", "GCP_CHECKS"]
