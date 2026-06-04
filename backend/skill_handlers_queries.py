"""Skill handlers — operational query commands (/patch-status, /assets, etc.)."""
import logging
import re
from typing import Optional

from database import get_database

logger = logging.getLogger(__name__)


async def handle_patch_status(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        filt = args.strip().lower()
        if filt in ("critical", "high", "medium", "low"):
            q["severity"] = filt.capitalize()
        elif filt == "overdue":
            q["status"] = "overdue"
        total = await db.patches.count_documents(q)
        pending = await db.patches.count_documents({**q, "status": "pending"})
        overdue = await db.patches.count_documents({**q, "status": "overdue"})
        recent_jobs = await (
            db.patch_deployment_jobs.find(
                {"tenantId": tenant_id} if tenant_id else {},
                {"_id": 0, "status": 1, "progress": 1, "createdAt": 1, "targetAssetIds": 1}
            ).sort("createdAt", -1).limit(3).to_list(length=3)
        )
        lines = ["**Patch Status**\n"]
        lines.append(f"• Total patches tracked: **{total}**")
        lines.append(f"• Pending: **{pending}**")
        lines.append(f"• Overdue: **{overdue}**")
        if recent_jobs:
            lines.append("\n**Recent Deployment Jobs:**")
            for j in recent_jobs:
                assets = len(j.get("targetAssetIds", []))
                lines.append(f"• {j.get('status','?')} — {assets} asset(s), progress {j.get('progress', 0)}%")
        lines.append("\n[NAVIGATE:patchManagement]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /patch-status error: %s", e)
        return "Unable to fetch patch status. [NAVIGATE:patchManagement]"


async def handle_software_outdated(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id, "updateAvailable": True} if tenant_id else {"updateAvailable": True}
        pkg_type = args.strip().lower()
        if pkg_type:
            q["pkg_type"] = pkg_type
        outdated = await (
            db.installed_software.find(q, {"_id": 0, "name": 1, "version": 1, "latestVersion": 1, "assetId": 1})
            .limit(8).to_list(length=8)
        )
        total = await db.installed_software.count_documents(q)
        if not outdated:
            return "No outdated software found. [NAVIGATE:patchManagement]"
        lines = [f"**Outdated Software** ({total} total):\n"]
        for pkg in outdated:
            lines.append(
                f"• **{pkg.get('name','?')}** {pkg.get('version','?')} → {pkg.get('latestVersion','latest')}"
            )
        lines.append("\n[NAVIGATE:patchManagement]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /software-outdated error: %s", e)
        return "Unable to fetch outdated software. [NAVIGATE:patchManagement]"


async def handle_vendor_risk(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        name_filter = args.strip()
        if name_filter:
            q["name"] = {"$regex": re.escape(name_filter), "$options": "i"}
        vendors = await (
            db.vendors.find(q, {"_id": 0, "name": 1, "criticality": 1, "assessments": 1, "status": 1})
            .limit(6).to_list(length=6)
        )
        if not vendors:
            return "No vendors found. [NAVIGATE:vendorRisk]"
        lines = [f"**Vendor Risk Summary** ({len(vendors)} shown):\n"]
        for v in vendors:
            assessments = v.get("assessments", [])
            score = assessments[-1].get("risk_score", "—") if assessments else "—"
            lines.append(f"• **{v.get('name','?')}** [{v.get('criticality','?')}] — Risk score: {score}")
        lines.append("\n[NAVIGATE:vendorRisk]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /vendor-risk error: %s", e)
        return "Unable to fetch vendor data. [NAVIGATE:vendorRisk]"


async def handle_assets(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        os_filter = args.strip()
        if os_filter:
            q["os"] = {"$regex": re.escape(os_filter), "$options": "i"}
        total = await db.assets.count_documents(q)
        recent = await (
            db.assets.find(q, {"_id": 0, "hostname": 1, "os": 1, "ip": 1, "status": 1})
            .sort("last_seen", -1).limit(5).to_list(length=5)
        )
        lines = [f"**Asset Inventory** ({total} total):\n"]
        for a in recent:
            lines.append(f"• {a.get('hostname', a.get('ip','?'))} — {a.get('os','?')} [{a.get('status','?')}]")
        lines.append("\n[NAVIGATE:assetInventory]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /assets error: %s", e)
        return "Unable to fetch asset data. [NAVIGATE:assetInventory]"


async def handle_tickets(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        status_filter = args.strip().lower()
        if status_filter in ("open", "closed", "resolved", "in_progress"):
            q["status"] = status_filter
        tickets = await (
            db.tickets.find(q, {"_id": 0, "title": 1, "status": 1, "severity": 1, "created_at": 1})
            .sort("created_at", -1).limit(5).to_list(length=5)
        )
        config = await db.ticketing_configs.find_one(
            {"tenantId": tenant_id} if tenant_id else {}, {"_id": 0, "provider": 1}
        )
        provider = config.get("provider", "not configured") if config else "not configured"
        lines = [f"**Tickets** (provider: {provider}):\n"]
        if not tickets:
            lines.append("No tickets found.")
        for t in tickets:
            lines.append(f"• [{t.get('severity','?')}] {t.get('title','?')} — {t.get('status','?')}")
        lines.append("\n[NAVIGATE:ticketing]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /tickets error: %s", e)
        return "Unable to fetch tickets. [NAVIGATE:ticketing]"


async def handle_approvals(tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"status": "pending"}
        if tenant_id:
            q["tenantId"] = tenant_id
        pending = await (
            db.approval_requests.find(q, {"_id": 0, "id": 1, "actionType": 1, "requester": 1, "createdAt": 1})
            .sort("createdAt", -1).limit(5).to_list(length=5)
        )
        total = await db.approval_requests.count_documents(q)
        if not pending:
            return "No pending approvals. [NAVIGATE:approvals]"
        lines = [f"**Pending Approvals** ({total} total):\n"]
        for r in pending:
            lines.append(
                f"• [{r.get('actionType','?')}] by {r.get('requester','?')} — `{r.get('id','?')}`"
            )
        lines.append("\n[NAVIGATE:approvals]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /approvals error: %s", e)
        return "Unable to fetch approvals. [NAVIGATE:approvals]"


async def handle_dr_status(tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        config = await db.dr_configs.find_one(q, {"_id": 0, "rto": 1, "rpo": 1, "status": 1, "last_test": 1})
        hadr = await db.hadr_status.find_one(q, {"_id": 0, "replication_lag": 1, "primary": 1, "replicas": 1})
        lines = ["**Disaster Recovery Status**\n"]
        if config:
            lines.append(f"• DR Status: **{config.get('status','?')}**")
            lines.append(f"• RTO: {config.get('rto','N/A')} | RPO: {config.get('rpo','N/A')}")
            lines.append(f"• Last tested: {str(config.get('last_test','Never'))[:10]}")
        else:
            lines.append("• DR configuration not found.")
        if hadr:
            lines.append(f"• Primary: {hadr.get('primary','?')} | Replicas: {hadr.get('replicas','?')}")
            lines.append(f"• Replication lag: {hadr.get('replication_lag','?')}")
        lines.append("\n[NAVIGATE:disasterRecovery]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /dr-status error: %s", e)
        return "Unable to fetch DR status. [NAVIGATE:disasterRecovery]"


async def handle_maintenance(tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        windows = await (
            db.maintenance_windows.find(q, {"_id": 0, "name": 1, "start_time": 1, "end_time": 1, "status": 1})
            .sort("start_time", 1).limit(5).to_list(length=5)
        )
        if not windows:
            return "No maintenance windows scheduled. [NAVIGATE:maintenance]"
        lines = ["**Maintenance Windows**:\n"]
        for w in windows:
            start = str(w.get("start_time", "?"))[:16]
            end = str(w.get("end_time", "?"))[:16]
            lines.append(f"• **{w.get('name','?')}** [{w.get('status','?')}] {start} → {end}")
        lines.append("\n[NAVIGATE:maintenance]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /maintenance error: %s", e)
        return "Unable to fetch maintenance windows. [NAVIGATE:maintenance]"


async def handle_knowledge_search(query: str, tenant_id: Optional[str], ai_svc) -> str:
    try:
        db = get_database()
        q: dict = {
            "$or": [
                {"title": {"$regex": re.escape(query[:100]), "$options": "i"}},
                {"content": {"$regex": re.escape(query[:100]), "$options": "i"}},
                {"tags": {"$in": [query.strip().lower()]}},
            ]
        }
        if tenant_id:
            q["$and"] = [{"$or": [{"tenantId": tenant_id}, {"tenantId": {"$exists": False}}]}]
            del q["$or"]
            q["$and"].append({"$or": [
                {"title": {"$regex": re.escape(query[:100]), "$options": "i"}},
                {"content": {"$regex": re.escape(query[:100]), "$options": "i"}},
            ]})
        docs = await (
            db.knowledge_docs.find(q, {"_id": 0, "title": 1, "content": 1})
            .limit(3).to_list(length=3)
        )
        if not docs:
            return f"No knowledge base articles found for `{query[:60]}`. [NAVIGATE:knowledgeBase]"
        lines = [f"**Knowledge Base: '{query[:60]}'**\n"]
        for doc in docs:
            excerpt = str(doc.get("content", ""))[:150].rstrip()
            lines.append(f"**{doc.get('title','?')}**\n{excerpt}…\n")
        lines.append("[NAVIGATE:knowledgeBase]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /knowledge-search error: %s", e)
        return "Unable to search knowledge base. [NAVIGATE:knowledgeBase]"


async def handle_users(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        role_filter = args.strip()
        if role_filter:
            q["role"] = {"$regex": re.escape(role_filter), "$options": "i"}
        total = await db.users.count_documents(q)
        users = await (
            db.users.find(q, {"_id": 0, "email": 1, "role": 1, "last_login": 1, "status": 1})
            .sort("last_login", -1).limit(6).to_list(length=6)
        )
        lines = [f"**Users** ({total} total):\n"]
        for u in users:
            last = str(u.get("last_login", "never"))[:10]
            lines.append(f"• {u.get('email','?')} [{u.get('role','?')}] — last login: {last}")
        lines.append("\n[NAVIGATE:userManagement]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /users error: %s", e)
        return "Unable to fetch users. [NAVIGATE:userManagement]"


async def handle_risk_register(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        status_filter = args.strip().lower()
        if status_filter in ("open", "accepted", "mitigated", "closed"):
            q["status"] = status_filter.capitalize()
        risks = await (
            db.risks.find(q, {"_id": 0, "title": 1, "status": 1, "likelihood": 1, "impact": 1, "owner": 1})
            .sort("impact", -1).limit(5).to_list(length=5)
        )
        total = await db.risks.count_documents(q)
        if not risks:
            return "No risks found in the register. [NAVIGATE:riskRegister]"
        lines = [f"**Risk Register** ({total} total):\n"]
        for r in risks:
            score = (r.get("likelihood", 0) or 0) * (r.get("impact", 0) or 0)
            lines.append(
                f"• **{r.get('title','?')}** [{r.get('status','?')}] "
                f"Score: {score} — Owner: {r.get('owner','?')}"
            )
        lines.append("\n[NAVIGATE:riskRegister]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /risk-register error: %s", e)
        return "Unable to fetch risk register. [NAVIGATE:riskRegister]"


async def handle_cost_snapshot(tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        costs = await (
            db.cloud_costs.find(q, {"_id": 0, "provider": 1, "amount": 1, "currency": 1, "period": 1})
            .sort("period", -1).limit(5).to_list(length=5)
        )
        recs = await db.cost_recommendations.count_documents(q)
        if not costs:
            return "No cloud cost data found. Configure cloud integrations to see spend. [NAVIGATE:finOps]"
        total = sum(c.get("amount", 0) or 0 for c in costs)
        lines = ["**Cloud Cost Snapshot**\n"]
        for c in costs:
            lines.append(
                f"• {c.get('provider','?')} — {c.get('currency','$')}{c.get('amount',0):,.2f} "
                f"({str(c.get('period','?'))[:7]})"
            )
        lines.append(f"\n• **Total across shown records:** ${total:,.2f}")
        if recs:
            lines.append(f"• **Optimization recommendations available:** {recs}")
        lines.append("\n[NAVIGATE:finOps]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /cost-snapshot error: %s", e)
        return "Unable to fetch cost data. [NAVIGATE:finOps]"
