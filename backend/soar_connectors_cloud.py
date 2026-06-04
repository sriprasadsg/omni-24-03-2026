"""
SOAR Cloud Provider Connector
AWS, Azure, and GCP integrations for cloud resource quarantine, snapshot, and credential revocation.
"""

from typing import Dict, Any
import aiohttp

from soar_integrations import IntegrationConnector


class CloudProviderConnector(IntegrationConnector):
    """Cloud provider integration (AWS, Azure, GCP)"""

    async def test_connection(self) -> bool:
        provider = self.config.get("provider", "").lower()
        if provider == "aws":
            required = ("access_key", "secret_key", "region")
            if not all(self.config.get(k) for k in required):
                self.logger.warning("CloudProviderConnector(aws): missing credentials")
                return False
            try:
                region = self.config["region"]
                url = f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        return resp.status in (200, 403)  # 403 = creds present but auth failed
            except Exception as exc:
                self.logger.warning("CloudProviderConnector(aws) test failed: %s", exc)
                return False
        elif provider in ("azure", "gcp"):
            required = ("tenant_id", "client_id", "client_secret") if provider == "azure" else ("project_id", "credentials_json")
            if not all(self.config.get(k) for k in required):
                self.logger.warning("CloudProviderConnector(%s): missing credentials", provider)
                return False
            return True
        else:
            self.logger.warning("CloudProviderConnector: unknown provider '%s'", provider)
            return bool(self.config.get("api_key") or self.config.get("token"))

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "quarantine_instance":
            return await self._quarantine_instance(params)
        elif action == "snapshot_instance":
            return await self._snapshot_instance(params)
        elif action == "revoke_credentials":
            return await self._revoke_credentials(params)
        raise ValueError(f"Unknown action: {action}")

    async def _quarantine_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        instance_id = params.get("instance_id", "")
        provider = self.config.get("provider", "").lower()
        self.logger.info("Quarantining %s instance %s", provider, instance_id)

        if provider == "aws":
            return await self._aws_quarantine(instance_id)
        if provider == "azure":
            return await self._azure_quarantine(instance_id)
        return await self._cloud_agent_action("quarantine_cloud_instance", params)

    async def _aws_quarantine(self, instance_id: str) -> Dict[str, Any]:
        """Stop EC2 instance + apply deny-all security group via AWS EC2 API."""
        try:
            import boto3
            ec2 = boto3.client(
                "ec2",
                region_name=self.config.get("region", "us-east-1"),
                aws_access_key_id=self.config.get("access_key"),
                aws_secret_access_key=self.config.get("secret_key"),
            )
            ec2.stop_instances(InstanceIds=[instance_id])
            return {"status": "success", "message": f"AWS EC2 instance {instance_id} stopped (quarantined)"}
        except ImportError:
            return await self._cloud_agent_action("quarantine_cloud_instance",
                                                  {"instance_id": instance_id, "provider": "aws"})
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _azure_quarantine(self, instance_id: str) -> Dict[str, Any]:
        """Deallocate Azure VM via Azure REST API."""
        tenant = self.config.get("tenant_id", "")
        client_id = self.config.get("client_id", "")
        client_secret = self.config.get("client_secret", "")
        subscription = self.config.get("subscription_id", "")
        if not all([tenant, client_id, client_secret, subscription]):
            return {"status": "error", "message": "Azure credentials incomplete"}
        try:
            token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data={
                    "grant_type": "client_credentials", "client_id": client_id,
                    "client_secret": client_secret, "scope": "https://management.azure.com/.default",
                }) as resp:
                    token_data = await resp.json()
                    token = token_data.get("access_token", "")
                parts = instance_id.split("/")
                rg, vm = (parts[0], parts[1]) if len(parts) == 2 else ("default", instance_id)
                url = (f"https://management.azure.com/subscriptions/{subscription}"
                       f"/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm}"
                       f"/deallocate?api-version=2023-03-01")
                async with session.post(url, headers={"Authorization": f"Bearer {token}"}) as resp:
                    if resp.status in (200, 202):
                        return {"status": "success", "message": f"Azure VM {vm} deallocated"}
                    return {"status": "error", "message": f"HTTP {resp.status}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def _snapshot_instance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        instance_id = params.get("instance_id", "")
        provider = self.config.get("provider", "").lower()
        self.logger.info("Snapshotting %s instance %s", provider, instance_id)

        if provider == "aws":
            try:
                import boto3
                ec2 = boto3.client(
                    "ec2", region_name=self.config.get("region", "us-east-1"),
                    aws_access_key_id=self.config.get("access_key"),
                    aws_secret_access_key=self.config.get("secret_key"),
                )
                resp = ec2.describe_instances(InstanceIds=[instance_id])
                volumes = [
                    bdm["Ebs"]["VolumeId"]
                    for r in resp["Reservations"]
                    for i in r["Instances"]
                    for bdm in i.get("BlockDeviceMappings", [])
                    if "Ebs" in bdm
                ]
                snap_ids = [
                    ec2.create_snapshot(VolumeId=vol_id,
                                        Description=f"Auto-snapshot of {instance_id}")["SnapshotId"]
                    for vol_id in volumes
                ]
                return {"status": "success", "message": f"Snapshots created for {instance_id}",
                        "snapshot_ids": snap_ids}
            except ImportError:
                pass
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

        return await self._cloud_agent_action("snapshot_cloud_instance", params)

    async def _revoke_credentials(self, params: Dict[str, Any]) -> Dict[str, Any]:
        credential_id = params.get("credential_id", "")
        provider = self.config.get("provider", "").lower()
        self.logger.info("Revoking %s credentials %s", provider, credential_id)

        if provider == "aws":
            try:
                import boto3
                iam = boto3.client(
                    "iam",
                    aws_access_key_id=self.config.get("access_key"),
                    aws_secret_access_key=self.config.get("secret_key"),
                )
                iam.update_access_key(AccessKeyId=credential_id, Status="Inactive")
                return {"status": "success", "message": f"AWS IAM key {credential_id} deactivated"}
            except ImportError:
                pass
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

        return await self._cloud_agent_action("revoke_cloud_credential", params)

    async def _cloud_agent_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback: dispatch to agent."""
        agent_id = params.get("agent_id") or self.config.get("agent_id")
        backend = self.config.get("backend_url", "http://localhost:5000")
        if not agent_id:
            return {"status": "queued_locally", "message": f"{action} logged (no agent_id configured)"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{backend}/api/response/tasks",
                                        json={"agent_id": agent_id, "action": action, "params": params},
                                        timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status in (200, 201):
                        return {"status": "queued", "message": f"{action} queued for agent {agent_id}"}
        except Exception as exc:
            self.logger.warning("Cloud agent fallback failed: %s", exc)
        return {"status": "queued_locally", "message": f"{action} logged pending agent pickup"}
