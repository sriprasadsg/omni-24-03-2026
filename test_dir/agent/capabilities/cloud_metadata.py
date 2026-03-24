
import logging
import requests
from typing import Dict, Any
from .base import BaseCapability

logger = logging.getLogger(__name__)

class CloudMetadataCapability(BaseCapability):
    """
    Collects metadata from cloud instance metadata services (IMDS).
    Supports AWS, GCP, and Azure.
    """
    
    @property
    def capability_id(self) -> str:
        return 'cloud_metadata'

    @property
    def capability_name(self) -> str:
        return 'Cloud Metadata'

    def __init__(self):
        super().__init__()

    def collect(self) -> Dict[str, Any]:
        metadata = {}
        
        # Try AWS IMDSv2 (Token required)
        try:
            token = requests.put(
                "http://169.254.169.254/latest/api/token",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
                timeout=1
            ).text
            
            headers = {"X-aws-ec2-metadata-token": token}
            doc = requests.get(
                "http://169.254.169.254/latest/dynamic/instance-identity/document",
                headers=headers,
                timeout=1
            ).json()
            
            metadata = {
                "provider": "AWS",
                "instanceId": doc.get("instanceId"),
                "region": doc.get("region"),
                "accountId": doc.get("accountId"),
                "imageId": doc.get("imageId"),
                "details": "AWS IMDSv2 verified"
            }
            return metadata
        except:
            pass
            
        # Try GCP
        try:
            headers = {"Metadata-Flavor": "Google"}
            # Check just one field to verify
            project_id = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers=headers,
                timeout=1
            ).text
            
            # Get instance ID
            instance_id = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/id",
                headers=headers,
                timeout=1
            ).text
            
             # Get zone
            zone = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/zone",
                headers=headers,
                timeout=1
            ).text

            metadata = {
                "provider": "GCP",
                "instanceId": instance_id,
                "projectId": project_id,
                "zone": zone.split('/')[-1] if zone else "unknown",
                "details": "GCP Metadata verified"
            }
            return metadata
        except:
            pass

        # Try Azure
        try:
            headers = {"Metadata": "true"}
            resp = requests.get(
                "http://169.254.169.254/metadata/instance?api-version=2021-02-01",
                headers=headers,
                timeout=1
            ).json()
            
            compute = resp.get("compute", {})
            metadata = {
                "provider": "Azure",
                "instanceId": compute.get("vmId"),
                "name": compute.get("name"),
                "location": compute.get("location"),
                "details": "Azure Metadata verified"
            }
            return metadata
        except:
            pass

        return {"provider": "Unknown", "details": "No cloud metadata service reachable"}
