"""Skill handlers — one async function per /slash command."""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from database import get_database
from skill_handlers_queries import (
    handle_patch_status,
    handle_software_outdated,
    handle_vendor_risk,
    handle_assets,
    handle_tickets,
    handle_approvals,
    handle_dr_status,
    handle_maintenance,
    handle_knowledge_search,
    handle_users,
    handle_risk_register,
    handle_cost_snapshot,
)

from auth_roles import SUPER_AND_ADMIN_ROLES as _SKILL_SUPER_ROLES

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


async def handle_rotate_key(args: str, tenant_id: Optional[str]) -> str:
    try:
        db = get_database()
        key_id = args.strip()
        if not key_id:
            return "Usage: `/rotate-key <key_id>` — e.g. `/rotate-key my-api-key-123`"

        now = datetime.now(timezone.utc).isoformat()
        instruction_id = uuid.uuid4().hex
        await db.agent_instructions.insert_one({
            "id": instruction_id,
            "tenantId": tenant_id,
            "instruction": "rotate_key",
            "status": "pending",
            "created_at": now,
            "type": "autonomous_remediation",
            "payload": {"key_id": key_id},
        })
        return (
            f"**Key rotation instruction dispatched** for `key_id`: `{key_id}`. [NAVIGATE:autonomous-remediation]\n\n"
            f"Instruction ID: `{instruction_id}`"
        )
    except Exception as e:
        logger.error("skill /rotate-key error: %s", e)
        return "Unable to dispatch key rotation. [NAVIGATE:autonomous-remediation]"


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


async def dispatch_skill(message: str, context: dict, ai_svc) -> str:
    """Route a /command message to the correct handler."""
    from skill_registry import SKILLS
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
    if name == "rotate-key":
        return await handle_rotate_key(args, tenant_id)
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
