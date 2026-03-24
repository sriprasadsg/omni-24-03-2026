import boto3
import os
import json
import shutil
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError
from typing import List, Optional, Dict, Any

class DataLakeService:
    def __init__(self):
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "omni-datalake-local")
        self.region = os.getenv("S3_REGION", "us-east-1")
        self.provider = os.getenv("DATA_LAKE_PROVIDER", "local") # 'aws' or 'local'
        
        # Local storage setup
        self.local_storage_root = os.path.join(os.getcwd(), "data_lake_storage")
        if self.provider == "local":
            os.makedirs(os.path.join(self.local_storage_root, "raw"), exist_ok=True)
            os.makedirs(os.path.join(self.local_storage_root, "processed"), exist_ok=True)
            print(f"[DataLake] Initialized LOCAL storage at {self.local_storage_root}")
        else:
            self.s3 = boto3.client('s3', region_name=self.region)
            print(f"[DataLake] Initialized AWS S3 storage bucket={self.bucket_name}")

    async def ingest_data(self, data: Dict[str, Any], zone: str, category: str, filename: str) -> bool:
        """
        Save data to the Data Lake.
        path: {zone}/{category}/{YYYY}/{MM}/{DD}/{filename}
        """
        now = datetime.utcnow()
        path = f"{zone}/{category}/{now.year}/{now.month:02d}/{now.day:02d}/{filename}"
        
        content = json.dumps(data, indent=2)
        
        if self.provider == "local":
            return self._save_local(path, content)
        else:
            return self._save_s3(path, content)

    def _save_local(self, path: str, content: str) -> bool:
        try:
            full_path = os.path.join(self.local_storage_root, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"[DataLake] Local save error: {e}")
            return False

    def _save_s3(self, path: str, content: str) -> bool:
        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=path,
                Body=content,
                ContentType='application/json'
            )
            return True
        except Exception as e:
            print(f"[DataLake] S3 save error: {e}")
            return False

    async def list_files(self, zone: str, category: str) -> List[str]:
        """List files in a specific zone/category"""
        prefix = f"{zone}/{category}/"
        results = []

        if self.provider == "local":
            search_root = os.path.join(self.local_storage_root, zone, category)
            if not os.path.exists(search_root):
                return []
            
            for root, _, files in os.walk(search_root):
                for file in files:
                    # Create relative path from zone root
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, self.local_storage_root)
                    results.append(rel_path.replace("\\", "/"))
        else:
            try:
                paginator = self.s3.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            results.append(obj['Key'])
            except Exception as e:
                print(f"[DataLake] S3 list error: {e}")
        
        return results

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        return {
            "provider": self.provider,
            "bucket": self.bucket_name if self.provider == "aws" else self.local_storage_root,
            "status": "Healthy"
        }

# Global Instance
data_lake_service = DataLakeService()
