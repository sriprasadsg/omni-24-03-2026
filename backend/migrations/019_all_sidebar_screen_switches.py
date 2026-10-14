"""Migration 019: a switch for every remaining sidebar item (spec C6).

The screens below got their own "screen:<view>" switch, so a Super Admin can now turn off any
sidebar item a tenant role reaches, one by one. Every tenant keeps every one of these screens it
can reach today (no parent, or its parent switch is on); nobody loses a screen on deploy. Only
these screens are added: a screen of an earlier migration that a Super Admin switched off stays off.
"""
from motor.motor_asyncio import AsyncIOMotorDatabase

import tenant_features

DESCRIPTION = "Switch on the new per-screen switches of every sidebar item a tenant already reaches"

NEW_SCREENS = (
    "dashboard", "digitalTwin", "futureTech", "executiveSummary", "reporting", "distributedTracing", "apm",
    "networkObservability", "networkTopology", "dataUtilization", "serviceMesh", "agents", "chat",
    "assetManagement", "certificates", "patchManagement", "deploymentApprovals", "softwareDeployment",
    "stagedDeployments", "cloudSecurity", "cloudAccounts", "cloudChecksScanner", "iacContainer",
    "incidentResponse", "incidentWarRoom", "incidentImpact", "supplyChain", "devsecops", "codeReviewGraph",
    "pipelineSecurity", "iacSecurity", "containerScan", "apiExtensions", "mlops", "modelMonitoring",
    "aiGovernance", "approvalWorkflows", "tasks", "internalTickets", "aiAssistantChat", "automation",
    "notificationsRouting", "playbooks", "soar", "scheduledReports", "agentApproval", "aiRemediation",
    "notificationPrefs", "fleetObservability", "fleetGeoMap", "nativeSecurity", "dataWarehouse",
)


def screens_to_add(enabled: list) -> list:
    """The NEW_SCREENS switches this tenant's list reaches but does not hold yet."""
    have = set(enabled)
    added = []
    for view in NEW_SCREENS:
        switch = f"{tenant_features.SCREEN_PREFIX}{view}"
        parent = tenant_features.SWITCH_PARENTS.get(switch)
        if switch in tenant_features.SWITCH_PARENTS and switch not in have and (parent is None or parent in have):
            added.append(switch)
    return added


async def up(db: AsyncIOMotorDatabase) -> None:
    async for tenant in db.tenants.find({"enabledFeatures": {"$type": "array"}}, {"_id": 0, "id": 1, "enabledFeatures": 1}):
        screens = screens_to_add(tenant["enabledFeatures"])
        if screens:
            await db.tenants.update_one({"id": tenant["id"]}, {"$addToSet": {"enabledFeatures": {"$each": screens}}})
