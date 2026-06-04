"""PatchPolicyActionsMixin: action execution methods for PatchPolicyEngine."""

import aiohttp
from datetime import datetime, timezone
from typing import Dict, Any


class PatchPolicyActionsMixin:
    """Mixin providing the five action execution methods for PatchPolicyEngine."""

    async def _auto_deploy_patch(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Deploy patch immediately."""
        asset_ids = patch.get("affectedAssets", [])

        if config.get("asset_groups"):
            assets = await self.db.assets.find(
                {
                    "id": {"$in": asset_ids},
                    "group": {"$in": config["asset_groups"]}
                },
                {"_id": 0, "id": 1}
            ).to_list(length=1000)
            asset_ids = [a["id"] for a in assets]

        job_id = f"auto-deploy-{patch['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        deployment_job = {
            "id": job_id,
            "type": "immediate",
            "tenant_id": tenant_id,
            "patch_ids": [patch["id"]],
            "asset_ids": asset_ids,
            "status": "scheduled",
            "created_by": "policy_engine",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_for": config.get("schedule", "immediate"),
        }
        await self.db.patch_deployment_jobs.insert_one(deployment_job)
        return {
            "deployment_id": job_id,
            "asset_count": len(asset_ids),
            "scheduled_for": deployment_job["scheduled_for"],
        }

    async def _auto_deploy_staged(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Deploy patch using staged deployment."""
        from deployment_service import get_deployment_service
        deployment_service = get_deployment_service(self.db)
        asset_ids = patch.get("affectedAssets", [])
        deployment = await deployment_service.create_staged_deployment(
            patch_ids=[patch["id"]],
            asset_ids=asset_ids,
            tenant_id=tenant_id,
            created_by="policy_engine",
            deployment_config={
                "auto_progress": config.get("auto_progress", False),
                "rollback_on_failure": config.get("rollback_on_failure", True),
                "failure_threshold": config.get("failure_threshold", 0.10),
            },
        )
        return {"deployment_id": deployment["id"], "type": "staged", "stages": len(deployment["stages"])}

    async def _request_manual_approval(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Create manual approval request."""
        approval_id = f"approval-{patch['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        approval = {
            "id": approval_id,
            "type": "manual_patch_approval",
            "patch_id": patch["id"],
            "tenant_id": tenant_id,
            "status": "pending",
            "approvers": config.get("approvers", []),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc).timestamp() + (config.get("expiry_hours", 48) * 3600)),
        }
        await self.db.manual_approvals.insert_one(approval)

        if config.get("approvers"):
            from email_service import email_service
            smtp_config = await self.db.smtp_config.find_one({"tenant_id": tenant_id})
            if smtp_config:
                email_service.send_alert_notification(
                    smtp_config=smtp_config,
                    recipients=config["approvers"],
                    alert={
                        "title": f"Approval Required: Patch {patch.get('name')}",
                        "severity": "High",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "asset": f"Patch ID: {patch['id']}",
                        "description": (
                            f"A patch requires your approval before deployment.\n"
                            f"Policy: {config.get('policy_name', 'Manual Approval Policy')}"
                        ),
                        "recommendations": (
                            f"Please review and approve via the dashboard.\n"
                            f"Expires at: {datetime.fromtimestamp(approval['expires_at'], timezone.utc)}"
                        ),
                    },
                )
        return {"approval_id": approval_id}

    async def _send_notifications(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Send notifications about a patch."""
        message = (
            f"New patch available: {patch.get('name')}\n"
            f"Severity: {patch.get('severity')}\n"
            f"CVSS: {patch.get('cvss_score', 'N/A')}\n"
            f"Affected Assets: {len(patch.get('affectedAssets', []))}\n"
        )
        results: Dict[str, Any] = {"email_sent": False, "reasons": []}

        if "email" in config.get("channels", ["email"]):
            from email_service import email_service
            smtp_config = await self.db.smtp_config.find_one({"tenant_id": tenant_id})
            if smtp_config:
                recipients = config.get("recipients", [])
                if recipients:
                    email_result = email_service.send_alert_notification(
                        smtp_config=smtp_config,
                        recipients=recipients,
                        alert={
                            "title": f"Patch Notification: {patch.get('name')}",
                            "severity": patch.get("severity", "Medium"),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "asset": f"{len(patch.get('affectedAssets', []))} assets affected",
                            "description": message,
                            "recommendations": "Review and approve/deploy this patch.",
                        },
                    )
                    results["email_sent"] = email_result["success"]
                    results["email_details"] = email_result
                else:
                    results["reasons"].append("No recipients configured")
            else:
                results["reasons"].append("SMTP config not found for tenant")

        for channel, key in [("slack", "slack_webhook"), ("teams", "teams_webhook")]:
            if channel in config.get("channels", []):
                webhook_url = config.get(key)
                if webhook_url:
                    payload = {"text": (
                        f"New Patch Available: {patch.get('name')}\n"
                        f"Severity: {patch.get('severity')}\n"
                        f"Affected Assets: {len(patch.get('affectedAssets', []))}"
                    )}
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.post(webhook_url, json=payload) as response:
                                results[f"{channel}_sent"] = response.status in [200, 201]
                    except Exception as e:
                        results[f"{channel}_sent"] = False
                        results["reasons"].append(f"{channel.capitalize()} webhook failed: {e}")
                else:
                    results["reasons"].append(f"{channel.capitalize()} webhook missing")

        return results

    async def _quarantine_patch(
        self,
        patch: Dict[str, Any],
        config: Dict[str, Any],
        _tenant_id: str
    ) -> Dict[str, Any]:
        """Quarantine patch for manual review."""
        await self.db.patches.update_one(
            {"id": patch["id"]},
            {"$set": {
                "quarantined": True,
                "quarantine_reason": config.get("reason", "Automatic quarantine by policy"),
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return {"quarantined": True}
