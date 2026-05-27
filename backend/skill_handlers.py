"""Skill handlers — one async function per /slash command."""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from database import get_database

logger = logging.getLogger(__name__)


async def handle_help() -> str:
    from skill_registry import SKILLS
    by_cat: dict = {}
    for s in SKILLS:
        by_cat.setdefault(s.category, []).append(s)
    lines = ["**Available skills** — type `/` followed by a skill name:\n"]
    for cat, skills in by_cat.items():
        lines.append(f"**{cat.title()}**")
        for s in skills:
            lines.append(f"• `{s.usage}` — {s.description}")
        lines.append("")
    return "\n".join(lines)


async def handle_agents(tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        total = await db.agents.count_documents(q)
        online = await db.agents.count_documents({**q, "status": "online"})
        offline = total - online
        return (
            f"**Agent Fleet Summary** [NAVIGATE:agents]\n\n"
            f"• Total agents: **{total}**\n"
            f"• Online: **{online}**\n"
            f"• Offline: **{offline}**\n\n"
            "Go to the Agents view for full details."
        )
    except Exception as e:
        logger.error("skill /agents error: %s", e)
        return "Unable to fetch agent data. [NAVIGATE:agents]"


async def handle_alerts(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        sev = args.strip().capitalize()
        if sev in ("Critical", "High", "Medium", "Low"):
            q["severity"] = sev
        alerts = await (
            db.alerts.find(q, {"_id": 0, "title": 1, "severity": 1, "created_at": 1})
            .sort("created_at", -1)
            .limit(5)
            .to_list(length=5)
        )
        if not alerts:
            return "No alerts found matching your filter. [NAVIGATE:alerts]"
        lines = [f"**Recent Alerts** ({len(alerts)} shown):\n"]
        for a in alerts:
            lines.append(f"• [{a.get('severity', '?')}] {a.get('title', 'Unknown alert')}")
        lines.append("\n[NAVIGATE:alerts]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /alerts error: %s", e)
        return "Unable to fetch alerts. [NAVIGATE:alerts]"


async def handle_vulnerabilities(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        sev = args.strip().capitalize()
        if sev in ("Critical", "High", "Medium", "Low"):
            q["severity"] = sev
        vulns = await (
            db.vulnerabilities.find(q, {"_id": 0, "title": 1, "severity": 1, "cvss_score": 1})
            .sort("cvss_score", -1)
            .limit(5)
            .to_list(length=5)
        )
        if not vulns:
            return "No vulnerabilities found. [NAVIGATE:vulnerabilities]"
        lines = [f"**Top Vulnerabilities** ({len(vulns)} shown):\n"]
        for v in vulns:
            lines.append(
                f"• [{v.get('severity', '?')}] {v.get('title', 'Unknown')} "
                f"(CVSS: {v.get('cvss_score', 'N/A')})"
            )
        lines.append("\n[NAVIGATE:vulnerabilities]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /vulnerabilities error: %s", e)
        return "Unable to fetch vulnerabilities. [NAVIGATE:vulnerabilities]"


async def handle_compliance(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"tenantId": tenant_id} if tenant_id else {}
        framework = args.strip()
        if framework:
            q["framework"] = {"$regex": re.escape(framework), "$options": "i"}
        scores = await (
            db.compliance_scores.find(q, {"_id": 0, "framework": 1, "score": 1, "status": 1})
            .limit(6)
            .to_list(length=6)
        )
        if not scores:
            return "No compliance data found. [NAVIGATE:compliance]"
        lines = ["**Compliance Posture**:\n"]
        for s in scores:
            lines.append(
                f"• {s.get('framework', '?')}: **{s.get('score', '?')}%** — {s.get('status', '?')}"
            )
        lines.append("\n[NAVIGATE:compliance]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /compliance error: %s", e)
        return "Unable to fetch compliance data. [NAVIGATE:compliance]"


async def handle_scan(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        q: dict = {"status": "online"}
        if tenant_id:
            q["tenantId"] = tenant_id
        agents = await db.agents.find(q, {"_id": 0, "id": 1}).limit(20).to_list(length=20)
        if not agents:
            return "No online agents found to scan. [NAVIGATE:agents]"
        now = datetime.now(timezone.utc).isoformat()
        target = args.strip() or "full"
        task_ids = []
        for agent in agents:
            task_id = uuid.uuid4().hex
            await db.agent_instructions.insert_one({
                "id": task_id,
                "agent_id": agent["id"],
                "tenantId": tenant_id,
                "instruction": "security_scan",
                "status": "pending",
                "created_at": now,
                "type": "security_scan",
                "payload": {"target": target},
            })
            task_ids.append(task_id)
        preview = ", ".join(task_ids[:3]) + ("…" if len(task_ids) > 3 else "")
        return (
            f"**Security scan dispatched** to {len(task_ids)} agent(s). [NAVIGATE:agents]\n\n"
            f"Task IDs: `{preview}`"
        )
    except Exception as e:
        logger.error("skill /scan error: %s", e)
        return "Unable to dispatch scan. [NAVIGATE:agents]"


async def handle_threat_hunt(query_text: str, tenant_id: Optional[str], ai_svc) -> str:
    import json as _json
    try:
        db = get_database()
        query_text = re.sub(r"[^\w\s\-\.\,\:\(\)']", " ", query_text[:500]).strip()
        pipeline_prompt = (
            "Convert this threat hunt query to a MongoDB $match filter for `security_events`. "
            "Fields: tenantId, time (ISO8601), severity, message, category_name. "
            f'Always include {{"tenantId": "{tenant_id}"}}. '
            "Return ONLY valid JSON.\n\nQuery: " + query_text
        )
        raw = await ai_svc.generate_text(pipeline_prompt, source="skill_threat_hunt")
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{[\s\S]+\}", cleaned)
        _SAFE = frozenset({"message", "severity", "time", "category_name", "source", "host", "ip", "user", "action", "tenantId"})
        match_filter: dict = {"tenantId": tenant_id} if tenant_id else {}
        if m:
            ai_filter = _json.loads(m.group(0))
            ai_filter = {k: v for k, v in ai_filter.items() if k in _SAFE}
            if tenant_id:
                ai_filter["tenantId"] = tenant_id
            match_filter = ai_filter
        events = await (
            db.security_events.find(match_filter, {"_id": 0, "message": 1, "severity": 1, "time": 1})
            .sort("time", -1)
            .limit(5)
            .to_list(length=5)
        )
        if not events:
            return "No events matched your query. [NAVIGATE:threatHunting]"
        lines = [f"**Threat Hunt Results** ({len(events)} events):\n"]
        for ev in events:
            lines.append(
                f"• [{ev.get('severity', '?')}] {str(ev.get('message', ''))[:100]} "
                f"— {str(ev.get('time', ''))[:10]}"
            )
        lines.append("\n[NAVIGATE:threatHunting]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /threat-hunt error: %s", e)
        return "Threat hunt failed. [NAVIGATE:threatHunting]"


async def handle_playbook(scenario: str, tenant_id: Optional[str], ai_svc) -> str:
    try:
        from ai_playbook_service import ai_playbook_service
        playbook = await ai_playbook_service.generate_playbook(scenario[:300], tenant_id)
        name = playbook.get("name", "Generated Playbook")
        steps = playbook.get("steps", [])
        lines = [f"**Playbook: {name}**\n"]
        for i, step in enumerate(steps[:5], 1):
            if isinstance(step, dict):
                lines.append(f"{i}. **{step.get('name', 'Step')}** — {step.get('description', '')}")
            else:
                lines.append(f"{i}. {step}")
        if len(steps) > 5:
            lines.append(f"…and {len(steps) - 5} more steps.")
        lines.append("\n[NAVIGATE:playbooks]")
        return "\n".join(lines)
    except Exception as e:
        logger.error("skill /playbook error: %s", e)
        return "Failed to generate playbook. [NAVIGATE:playbooks]"


async def handle_summarize(current_view: str, ai_svc) -> str:
    prompt = (
        f"You are a concise enterprise security assistant. "
        f"The user is on the **{current_view}** page. "
        "In 3 short bullet points, describe what key data and actions are available on this page. "
        "Be specific and actionable. No preamble."
    )
    try:
        summary = await ai_svc.generate_text(prompt, source="skill_summarize")
        return f"{summary}\n[NAVIGATE:{current_view}]"
    except Exception as e:
        logger.error("skill /summarize error: %s", e)
        return f"Unable to generate summary. [NAVIGATE:{current_view}]"


_SKILL_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin"}


# ── New skill handlers ────────────────────────────────────────────────────────

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


async def dispatch_skill(message: str, context: dict, ai_svc) -> str:
    """Route a /command message to the correct handler."""
    from skill_registry import SKILLS, SKILL_MAP
    parts = message[1:].strip().split(None, 1)
    if not parts or not parts[0]:
        available = "  ".join(f"`/{s.name}`" for s in SKILLS)
        return f"Available skills: {available}\n\nType `/help` for details."
    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    tenant_id: Optional[str] = context.get("tenantId") or None
    role: str = context.get("role", "") or ""
    current_view: str = context.get("currentView", "dashboard")

    # Fail-closed: non-super-admin users without a tenant context cannot run
    # data-scoped skills — returning unscoped {} queries across all tenants.
    if name not in ("help",) and not tenant_id and role not in _SKILL_SUPER_ROLES:
        return "Skill unavailable: no tenant context found. Please log out and back in."

    if name == "help":
        return await handle_help()
    if name == "agents":
        return await handle_agents(tenant_id)
    if name == "alerts":
        return await handle_alerts(args, tenant_id)
    if name == "vulnerabilities":
        return await handle_vulnerabilities(args, tenant_id)
    if name == "compliance":
        return await handle_compliance(args, tenant_id)
    if name == "scan":
        return await handle_scan(args, tenant_id)
    if name == "threat-hunt":
        if not args:
            return "Usage: `/threat-hunt <query>` — e.g. `/threat-hunt failed logins last 24h`"
        return await handle_threat_hunt(args, tenant_id, ai_svc)
    if name == "playbook":
        if not args:
            return "Usage: `/playbook <scenario>` — e.g. `/playbook ransomware outbreak`"
        return await handle_playbook(args, tenant_id, ai_svc)
    if name == "summarize":
        return await handle_summarize(current_view, ai_svc)
    if name == "patch-status":
        return await handle_patch_status(args, tenant_id)
    if name == "software-outdated":
        return await handle_software_outdated(args, tenant_id)
    if name == "vendor-risk":
        return await handle_vendor_risk(args, tenant_id)
    if name == "assets":
        return await handle_assets(args, tenant_id)
    if name == "tickets":
        return await handle_tickets(args, tenant_id)
    if name == "approvals":
        return await handle_approvals(tenant_id)
    if name == "dr-status":
        return await handle_dr_status(tenant_id)
    if name == "maintenance":
        return await handle_maintenance(tenant_id)
    if name == "knowledge-search":
        if not args:
            return "Usage: `/knowledge-search <query>` — e.g. `/knowledge-search ransomware containment`"
        return await handle_knowledge_search(args, tenant_id, ai_svc)
    if name == "users":
        return await handle_users(args, tenant_id)
    if name == "risk-register":
        return await handle_risk_register(args, tenant_id)
    if name == "cost-snapshot":
        return await handle_cost_snapshot(tenant_id)

    available = "  ".join(f"`/{s.name}`" for s in SKILLS)
    return f"Unknown skill `/{name}`. Type `/help` for the full list.\n\nAvailable: {available}"
