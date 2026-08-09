"""Startup helpers: config validation, database seeding, background service launcher."""

import asyncio
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

from auth_utils import hash_password
from database import get_database
from migrations.runner import run_migrations

logger = logging.getLogger(__name__)

_KNOWN_WEAK_JWT_VALUES = {
    "",
    "your-super-secret-jwt-key-change-this-in-production",
    "change-me-to-a-long-random-secret-string-at-least-32-chars",
    "secret",
    "changeme",
}

_PLACEHOLDER_PATTERNS = ("changeme_set_", "change_this_", "your_password", "password123")


def _check_placeholder_secrets():
    """Refuse to start in production if placeholder secrets are detected."""
    env = os.environ.get("APP_ENV", "development").lower()
    if env in ("development", "dev", "test", "ci"):
        return  # Allow placeholders in non-production

    dangerous = []
    for var in ("SUPER_ADMIN_PASSWORD", "TENANT_ADMIN_PASSWORD", "JWT_SECRET_KEY",
                "MONGO_ROOT_PASSWORD", "REDIS_PASSWORD"):
        val = os.environ.get(var, "")
        if any(val.startswith(p) or val == p for p in _PLACEHOLDER_PATTERNS):
            dangerous.append(var)

    if dangerous:
        raise RuntimeError(
            f"Refusing to start: placeholder secrets detected for: {', '.join(dangerous)}. "
            "Set real secrets before deploying to production."
        )


def _validate_startup_config() -> None:
    """Warn about dangerous or missing configuration at startup."""
    _check_placeholder_secrets()

    issues: list[str] = []

    jwt_key = os.getenv("JWT_SECRET_KEY", "")
    if jwt_key.lower() in _KNOWN_WEAK_JWT_VALUES:
        issues.append(
            "JWT_SECRET_KEY is unset or uses a known-weak default. "
            "Generate a secure key: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

    super_pass = os.getenv("SUPER_ADMIN_PASSWORD", "")
    if super_pass in {"", "your-secure-super-admin-password", "change-me-to-a-strong-password"}:
        issues.append("SUPER_ADMIN_PASSWORD is unset or uses a placeholder value.")

    optional_integrations = {
        "GEMINI_API_KEY": "AI/LLM features",
        "VIRUSTOTAL_API_KEY": "VirusTotal binary scanning",
        "SMTP_USER": "email notifications",
        "SLACK_WEBHOOK_URL": "Slack alerts",
        "STRIPE_SECRET_KEY": "Stripe payments",
    }
    missing_optional = [
        f"{var} ({desc})" for var, desc in optional_integrations.items()
        if not os.getenv(var)
    ]

    for issue in issues:
        logger.warning("[StartupConfig] ⚠️  %s", issue)
    if missing_optional:
        logger.info(
            "[StartupConfig] Optional integrations not configured (features will be degraded): %s",
            ", ".join(missing_optional),
        )
    if not issues:
        logger.info("[StartupConfig] ✅ Core configuration looks good.")


async def _seed_yara_rules(raw_db) -> None:
    """
    Parse every .yar file in agent/capabilities/yara_rules/ and upsert each
    individual rule block into the custom_yara_rules collection as a built-in
    read-only sample visible to all tenants.
    """
    import re
    from pathlib import Path

    yara_dir = Path(__file__).resolve().parent.parent / "agent" / "capabilities" / "yara_rules"
    if not yara_dir.is_dir():
        logger.debug("[YARA] yara_rules directory not found at %s — skipping seed", yara_dir)
        return

    # Only seed if the collection has no built-in rules yet (idempotent)
    existing = await raw_db.custom_yara_rules.count_documents({"source": "builtin"})
    if existing > 0:
        logger.debug("[YARA] %d built-in rules already present — skipping re-seed", existing)
        return

    rule_pattern = re.compile(
        r'rule\s+(\w+)\s*(?::\s*[\w\s]+)?\{(.*?)\}',
        re.DOTALL,
    )
    meta_field = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

    seeded = 0
    for yar_file in sorted(yara_dir.glob("*.yar")):
        category = yar_file.stem  # e.g. "ransomware", "web_shells"
        content = yar_file.read_text(encoding="utf-8", errors="replace")
        for match in rule_pattern.finditer(content):
            rule_name = match.group(1)
            rule_body = f"rule {rule_name} {{{match.group(2)}}}"
            # Parse meta block
            meta_block_m = re.search(r'meta:\s*(.*?)(?:strings:|condition:)', rule_body, re.DOTALL)
            meta: dict = {}
            if meta_block_m:
                for kv in meta_field.finditer(meta_block_m.group(1)):
                    meta[kv.group(1)] = kv.group(2)

            doc_id = f"builtin_{category}_{rule_name}".lower()
            await raw_db.custom_yara_rules.update_one(
                {"id": doc_id},
                {"$setOnInsert": {
                    "id":            doc_id,
                    "name":          rule_name,
                    "content":       rule_body.strip(),
                    "description":   meta.get("description", f"Built-in {category} detection rule"),
                    "severity":      meta.get("severity", "medium"),
                    "mitre":         meta.get("mitre", ""),
                    "family":        meta.get("family", ""),
                    "category":      category,
                    "source":        "builtin",
                    "enabled":       True,
                    "tenantId":      "platform-admin",
                    "createdBy":     "system",
                    "createdAt":     datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )
            seeded += 1

    if seeded:
        logger.info("[YARA] Seeded %d built-in detection rules from %s", seeded, yara_dir)


async def seed_database():
    """Create or refresh the super admin user and platform tenant."""
    try:
        db = get_database()

        # Run schema migrations before any seeding so indexes exist before data is inserted
        await run_migrations(db._db)

        raw_users = db._db.users

        _super_admin_password = os.getenv("SUPER_ADMIN_PASSWORD")
        if not _super_admin_password:
            _super_admin_password = secrets.token_urlsafe(32)
            logger.warning(
                "SUPER_ADMIN_PASSWORD env var not set — generated a random password. "
                "Set the variable explicitly for a stable super admin login."
            )

        super_admin_data = {
            "tenantId": "platform-admin",
            "tenantName": "Platform",
            "name": "Super Admin",
            "email": "super@omni.ai",
            "password": hash_password(_super_admin_password),
            "role": "Super Admin",
            "avatar": "https://i.pravatar.cc/150?u=super-admin",
            "status": "Active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        super_admin = await raw_users.find_one({"email": "super@omni.ai"})
        if not super_admin:
            logger.info("Creating new super admin user...")
            super_admin_data["id"] = f"user-{uuid.uuid4()}"
            await raw_users.insert_one(super_admin_data)
        else:
            logger.info("Updating existing super admin credentials...")
            await raw_users.update_one(
                {"email": "super@omni.ai"},
                {"$set": {
                    "password": super_admin_data["password"],
                    "status": "Active",
                    "role": "Super Admin",
                }},
            )

        logger.info("Super admin account verified.")

        platform_tenant = await db.tenants.find_one({"id": "platform-admin"})
        if not platform_tenant:
            _reg_key = os.getenv("PLATFORM_ADMIN_REG_KEY") or secrets.token_urlsafe(32)
            if not os.getenv("PLATFORM_ADMIN_REG_KEY"):
                logger.warning("PLATFORM_ADMIN_REG_KEY env var not set — generated a random registration key.")
            await db.tenants.insert_one({
                "id": "platform-admin",
                "name": "Platform",
                "subscriptionTier": "Enterprise",
                "registrationKey": _reg_key,
                "enabledFeatures": [],
                "apiKeys": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info("Platform tenant created successfully.")

        all_permissions = [
            "view:dashboard", "view:reporting", "export:reports", "view:agents",
            "view:software_deployment", "view:agent_logs", "remediate:agents", "view:assets",
            "view:patching", "manage:patches", "view:security", "manage:security_cases",
            "manage:security_playbooks", "investigate:security", "view:compliance",
            "manage:compliance_evidence", "view:ai_governance", "manage:ai_risks",
            "manage:settings", "manage:tenants", "view:cloud_security", "view:finops",
            "view:audit_log", "manage:rbac", "manage:api_keys", "view:logs",
            "view:threat_hunting", "view:profile", "view:automation", "manage:automation",
            "view:devsecops", "manage:devsecops", "view:sbom", "manage:sbom",
            "view:developer_hub", "view:insights", "view:tracing",
            "view:dspm", "view:attack_path", "view:service_catalog", "view:dora_metrics",
            "view:chaos", "view:network", "manage:pricing", "view:software_updates",
            "view:zero_trust", "view:mdr", "view:xdr", "view:agent_capabilities",
            "manage:agents", "view:autopilot", "manage:autopilot",
            "view:conditional_access", "manage:conditional_access",
            "view:mdm", "manage:mdm", "view:branch_sites", "manage:branch_sites",
            "view:app_catalog", "manage:app_catalog",
            "view:asset_intelligence", "manage:asset_intelligence",
            "view:mam", "manage:mam",
            "view:android_enterprise", "manage:android_enterprise",
            "view:device_config_profiles", "manage:device_config_profiles",
            "view:firmware_drivers", "manage:firmware_drivers",
            "view:advanced_hunting", "manage:advanced_hunting",
            "view:detection_rules", "manage:detection_rules",
            "view:connectors_hub", "manage:connectors_hub",
            "view:security_copilot",
            "view:mssp", "manage:mssp",
            "view:attack_timeline",
            "view:geographic_map",
            "view:retention_policies", "manage:retention_policies",
            "view:sca", "manage:sca",
            "view:agent_groups", "manage:agent_groups",
            "view:config_drift", "manage:config_drift",
            "view:fim", "manage:fim",
            "view:active_response", "manage:active_response",
            "admin:*",
        ]
        await db.roles.update_one(
            {"name": "Super Admin"},
            {"$set": {
                "id": "role-super-admin",
                "name": "Super Admin",
                "description": "Has all permissions across all tenants.",
                "permissions": all_permissions,
                "isEditable": False,
                "tenantId": "platform",
            }},
            upsert=True,
        )
        logger.info("Super Admin role permissions updated")

        tenant_admin_permissions = [
            "view:dashboard", "view:reporting", "export:reports",
            "view:agents", "view:software_deployment", "view:agent_logs", "remediate:agents",
            "view:assets", "view:patching", "manage:patches", "view:security",
            "manage:security_cases", "investigate:security", "view:compliance",
            "manage:compliance_evidence", "view:ai_governance", "manage:ai_risks",
            "view:cloud_security", "view:finops", "view:audit_log",
            "manage:rbac", "manage:api_keys", "view:logs", "view:profile",
            "view:automation", "manage:automation", "view:devsecops", "manage:devsecops",
            "view:sbom", "manage:sbom", "view:insights", "view:software_updates",
            "view:threat_hunting", "view:tracing", "view:dspm", "view:attack_path",
            "view:service_catalog", "view:dora_metrics", "view:chaos", "view:network",
            "view:zero_trust", "view:developer_hub", "manage:security_playbooks",
            "view:cxo_dashboard", "view:unified_ops", "view:advanced_bi",
            "view:sustainability", "view:web_monitoring", "view:analytics",
            "view:threat_intel", "view:vulnerabilities", "view:persistence",
            "view:security_audit", "view:mlops", "view:llmops", "view:automl",
            "manage:experiments", "view:xai", "view:governance", "manage:playbooks",
            "view:swarm", "view:mdr", "view:xdr", "view:agent_capabilities",
            "manage:pricing", "manage:agents", "view:integrations",
            "view:autopilot", "manage:autopilot",
            "view:conditional_access", "manage:conditional_access",
            "view:mdm", "manage:mdm", "view:branch_sites", "manage:branch_sites",
            "view:app_catalog", "manage:app_catalog",
            "view:asset_intelligence", "manage:asset_intelligence",
            "view:mam", "manage:mam",
            "view:android_enterprise", "manage:android_enterprise",
            "view:device_config_profiles", "manage:device_config_profiles",
            "view:firmware_drivers", "manage:firmware_drivers",
            "view:advanced_hunting", "manage:advanced_hunting",
            "view:detection_rules", "manage:detection_rules",
            "view:connectors_hub", "manage:connectors_hub",
            "view:security_copilot",
            "view:mssp", "manage:mssp",
            "view:attack_timeline",
            "view:geographic_map",
            "view:retention_policies", "manage:retention_policies",
            "view:sca", "manage:sca",
            "view:agent_groups", "manage:agent_groups",
            "view:config_drift", "manage:config_drift",
            "view:fim", "manage:fim",
            "view:active_response", "manage:active_response",
        ]
        await db.roles.update_one(
            {"name": "Tenant Admin"},
            {"$set": {
                "id": "role-tenant-admin",
                "name": "Tenant Admin",
                "description": "Administrator for a specific tenant with full permissions except cross-tenant management.",
                "permissions": tenant_admin_permissions,
                "isEditable": False,
                "tenantId": "all",
            }},
            upsert=True,
        )
        logger.info("Tenant Admin role created/updated")

        # ── Standard roles (seeded with tenantId="all" so they apply platform-wide) ──
        standard_roles = [
            {
                "id": "role-analyst",
                "name": "analyst",
                "display_name": "Analyst",
                "description": "Security analyst with investigation and threat-hunting access.",
                "permissions": [
                    "view:dashboard", "view:reporting", "view:agents", "view:assets",
                    "view:security", "investigate:security", "view:compliance",
                    "view:threat_hunting", "view:threat_intel", "view:vulnerabilities",
                    "view:audit_log", "view:logs", "view:attack_path", "view:dspm",
                    "view:mdr", "view:xdr", "view:devsecops", "view:tracing", "view:profile",
                ],
                "isEditable": True,
                "tenantId": "all",
            },
            {
                "id": "role-security-analyst",
                "name": "security_analyst",
                "display_name": "Security Analyst",
                "description": "Deep security investigation with case management access.",
                "permissions": [
                    "view:dashboard", "view:security", "investigate:security",
                    "manage:security_cases", "view:threat_hunting", "view:threat_intel",
                    "view:vulnerabilities", "view:attack_path", "view:audit_log",
                    "view:logs", "view:mdr", "view:xdr", "view:dspm", "view:tracing",
                    "view:compliance", "view:assets", "view:profile",
                ],
                "isEditable": True,
                "tenantId": "all",
            },
            {
                "id": "role-incident-responder",
                "name": "incident_responder",
                "display_name": "Incident Responder",
                "description": "Incident triage and security case management.",
                "permissions": [
                    "view:dashboard", "view:security", "investigate:security",
                    "manage:security_cases", "view:threat_hunting", "view:audit_log",
                    "view:logs", "view:mdr", "view:xdr", "view:profile",
                    "view:agents", "view:assets",
                ],
                "isEditable": True,
                "tenantId": "all",
            },
            {
                "id": "role-user",
                "name": "user",
                "display_name": "User",
                "description": "Standard platform user with read-only access to core modules.",
                "permissions": [
                    "view:dashboard", "view:reporting", "view:agents", "view:agent_capabilities",
                    "view:assets", "view:patching", "view:security", "view:compliance",
                    "view:ai_governance", "view:cloud_security", "view:finops",
                    "view:audit_log", "view:logs", "view:threat_hunting", "view:profile",
                    "view:automation", "view:devsecops", "view:developer_hub",
                    "view:insights", "view:tracing", "view:mdr", "view:xdr",
                ],
                "isEditable": True,
                "tenantId": "all",
            },
            {
                "id": "role-viewer",
                "name": "viewer",
                "display_name": "Viewer",
                "description": "Read-only access to dashboards and reports.",
                "permissions": [
                    "view:dashboard", "view:reporting", "view:assets", "view:compliance",
                    "view:ai_governance", "view:cloud_security", "view:finops", "view:profile",
                ],
                "isEditable": True,
                "tenantId": "all",
            },
        ]
        for role_def in standard_roles:
            await db.roles.update_one(
                {"name": role_def["name"]},
                {"$set": role_def},
                upsert=True,
            )
        logger.info("Standard roles (analyst, security_analyst, incident_responder, user, viewer) seeded")

    except Exception as e:
        logger.error("Database seeding error: %s", e)


async def _prebuild_windows_agent() -> None:
    """
    Build the Rust Windows agent binary in the background at server startup.
    Idempotent — skips if the binary already exists or cargo is not available.
    """
    from pathlib import Path as _Path
    import shutil as _shutil

    base_dir = _Path(__file__).parent.parent
    exe_path = base_dir / "agent-install" / "omni-agent-rs" / "target" / "release" / "omni-agent.exe"
    if exe_path.exists():
        logger.debug("[WindowsAgent] Pre-built binary already present; skipping build")
        return

    src_dir = base_dir / "agent-install" / "omni-agent-rs"
    cargo = _shutil.which("cargo")
    if not src_dir.is_dir() or not cargo:
        logger.debug("[WindowsAgent] cargo not found; skipping pre-build")
        return

    logger.info("[WindowsAgent] Pre-building Rust agent binary in background...")
    proc = await asyncio.create_subprocess_exec(
        cargo, "build", "--release",
        cwd=str(src_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=600)
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning("[WindowsAgent] Pre-build timed out (>10 min)")
        return

    if proc.returncode == 0:
        logger.info("[WindowsAgent] Pre-build complete — %s", exe_path)
    else:
        snippet = (stderr_bytes or b"").decode(errors="replace")[-300:]
        logger.warning("[WindowsAgent] Pre-build failed: %s", snippet)


async def _safe_bg_task(coro, name: str) -> None:
    """Run a background coroutine; log exceptions instead of silently dropping them."""
    try:
        await coro
    except Exception as _exc:
        logger.error("Background task '%s' failed: %s", name, _exc, exc_info=True)


def init_agentic_tracing() -> None:
    """Wire Arize Phoenix OpenTelemetry tracing for AsyncAnthropic calls.

    Called once at startup. If Phoenix is unreachable or packages are missing,
    logs a warning and returns — never raises to the caller.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from openinference.instrumentation.anthropic import AnthropicInstrumentor

        endpoint = os.getenv("PHOENIX_OTLP_ENDPOINT", "http://localhost:4317")
        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(provider)
        AnthropicInstrumentor().instrument()
        logger.info("[AgenticTracing] Phoenix tracing active at %s", endpoint)
    except ImportError:
        logger.warning(
            "[AgenticTracing] openinference-instrumentation-anthropic not installed — "
            "agentic LLM calls will not be traced. Run: pip install arize-phoenix "
            "openinference-instrumentation-anthropic opentelemetry-exporter-otlp-proto-http"
        )
    except Exception as exc:
        logger.warning("[AgenticTracing] Failed to initialise tracing: %s", exc)


async def run_startup_services() -> None:
    """Launch all background tasks and periodic services."""
    db = get_database()

    try:
        from database_migrations import (
            migrate_compliance_tenant_ids, migrate_instructions_tenant_ids,
            migrate_tenant_registration_keys, seed_compliance_frameworks,
        )
        await migrate_compliance_tenant_ids()
        await migrate_instructions_tenant_ids()
        await migrate_tenant_registration_keys()
        await seed_compliance_frameworks()
    except Exception as _e:
        logger.warning("[Migrations] Database self-healing migrations failed: %s", _e)

    try:
        from response_endpoints import initialize_response_module
        await initialize_response_module()
    except Exception as _e:
        logger.warning("[MDR] Response policy seeding failed: %s", _e)

    try:
        from response_orchestrator import seed_builtin_policies
        await seed_builtin_policies()
    except Exception as _e:
        logger.warning("[Orchestrator] Policy seeding failed: %s", _e)

    try:
        from xdr_playbook_seeds import seed_xdr_playbooks
        await seed_xdr_playbooks()
    except Exception as _e:
        logger.warning("[XDR] Playbook seeding failed: %s", _e)

    from app_background_tasks import _start_xdr_correlation_scanner
    asyncio.create_task(_safe_bg_task(_start_xdr_correlation_scanner(), "xdr_correlation"))

    try:
        from threat_feed_sync import start_threat_feed_loop
        asyncio.create_task(_safe_bg_task(start_threat_feed_loop(db._db), "threat_feed_loop"))
    except Exception as _e:
        logger.warning("[ThreatFeed] Failed to start: %s", _e)

    try:
        from nvd_sync import start_nvd_sync_loop
        asyncio.create_task(_safe_bg_task(start_nvd_sync_loop(db._db), "nvd_sync_loop"))
    except Exception as _e:
        logger.warning("[NVD] CVE sync failed to start: %s", _e)

    try:
        from usage_tracker import start_usage_tracking_loop
        asyncio.create_task(_safe_bg_task(start_usage_tracking_loop(), "usage_tracking"))
    except Exception as _e:
        logger.warning("[UsageTracker] Failed to start: %s", _e)

    async def _approval_timeout_loop():
        from enhanced_playbook_engine import process_approval_timeouts
        from database import get_database as _gdb
        from tenant_context import set_tenant_id as _sti
        _atl_log = logging.getLogger("approval_timeout_loop")
        while True:
            try:
                _sti("platform-admin")
                await process_approval_timeouts(_gdb()._db)
            except Exception as _e:
                _atl_log.warning("Approval timeout processor error: %s", _e)
            await asyncio.sleep(60)

    asyncio.create_task(_approval_timeout_loop())

    from app_background_tasks import monitor_agent_status, refresh_mitre_heatmap_loop, compliance_evidence_sweep_loop
    asyncio.create_task(_safe_bg_task(monitor_agent_status(), "agent_status_monitor"))
    asyncio.create_task(_safe_bg_task(refresh_mitre_heatmap_loop(), "mitre_heatmap_refresh"))
    asyncio.create_task(_safe_bg_task(compliance_evidence_sweep_loop(), "compliance_evidence_sweep"))

    try:
        from scheduler import start_scheduler as start_deployment_scheduler
        start_deployment_scheduler()
    except ImportError:
        logger.warning("[Scheduler] Deployment scheduler module not found, skipping")

    try:
        from finops_scheduler import start_scheduler as start_finops_scheduler
        start_finops_scheduler()
    except ImportError:
        logger.warning("[FinOps] Scheduler module not found, skipping")

    try:
        from tickets_escalation_service import start_escalation_scheduler
        from database import mongodb as _mdb
        asyncio.create_task(start_escalation_scheduler(_mdb.db))
        logger.info("[Tickets] SLA auto-escalation scheduler started")
    except Exception as _e:
        logger.warning("[Tickets] Escalation scheduler failed to start: %s", _e)

    try:
        from syslog_receiver import start_syslog_server
        _syslog_port = int(os.getenv("SYSLOG_UDP_PORT", "5140"))
        asyncio.create_task(start_syslog_server(host="0.0.0.0", port=_syslog_port))
        logger.info("[SIEM] UDP Syslog server started on port %d", _syslog_port)
    except Exception as _e:
        logger.warning("[SIEM] Syslog server not started: %s", _e)

    for module, func, label in [
        ("aws_cloudtrail_ingest", "start_aws_polling", "[SIEM] AWS CloudTrail"),
        ("okta_log_ingest", "start_okta_polling", "[SIEM] Okta log"),
        ("azure_defender_ingest", "start_azure_polling", "[SIEM] Azure Defender"),
        ("gcp_scc_ingest", "start_gcp_polling", "[SIEM] GCP SCC"),
    ]:
        try:
            import importlib
            _mod = importlib.import_module(module)
            asyncio.create_task(getattr(_mod, func)())
            logger.info("%s polling started", label)
        except Exception as _e:
            logger.warning("%s ingest not started: %s", label, _e)

    try:
        from jit_access_service import start_jit_expiry_loop
        asyncio.create_task(start_jit_expiry_loop())
        logger.info("[JIT] Expiry enforcement loop started")
    except Exception as _e:
        logger.warning("[JIT] Expiry loop not started: %s", _e)

    try:
        from scheduled_reports_service import start_report_scheduler
        asyncio.create_task(start_report_scheduler())
        logger.info("[Reports] Scheduled report delivery started")
    except Exception as _e:
        logger.warning("[Reports] Scheduler not started: %s", _e)

    try:
        from streaming_service import processor as _stream_processor
        await _stream_processor.start()
        logger.info("[Stream] StreamProcessor started")
    except Exception as _e:
        logger.warning("[Stream] StreamProcessor failed to start: %s", _e)

    try:
        from knowledge_endpoints import seed_knowledge_base
        _kb_count = await seed_knowledge_base(db._db)
        if _kb_count:
            logger.info("[KnowledgeBase] Seeded %d default security documents", _kb_count)
    except Exception as _e:
        logger.warning("[KnowledgeBase] Seeding failed: %s", _e)

    try:
        await _seed_yara_rules(db._db)
    except Exception as _e:
        logger.warning("[YARA] Rule seeding failed: %s", _e)

    # Seed default LLM settings (Ollama local) if not yet configured
    try:
        from local_ip import ollama_default_url
        import os as _os
        existing_llm = await db._db.system_settings.find_one({"type": "llm"})
        if not existing_llm:
            await db._db.system_settings.insert_one({
                "type":        "llm",
                "provider":    "Local",
                "ollamaUrl":   _os.getenv("OLLAMA_URL", ollama_default_url()),
                "ollamaModel": _os.getenv("OLLAMA_MODEL", _os.getenv("LLM_MODEL", "llama3.2:3b")),
                "model":       _os.getenv("OLLAMA_MODEL", _os.getenv("LLM_MODEL", "llama3.2:3b")),
                "host":        _os.getenv("OLLAMA_URL", ollama_default_url()).replace("http://", ""),
                "temperature": 0.7,
                "timeout":     30,
            })
            logger.info("[LLM] Default Ollama settings seeded (provider=Local, url=%s)", ollama_default_url())
    except Exception as _e:
        logger.warning("[LLM] Default settings seeding failed: %s", _e)

    # Pre-build the Windows Rust agent in the background so the first tenant download is instant
    asyncio.create_task(_safe_bg_task(_prebuild_windows_agent(), "windows_agent_prebuild"))

    try:
        init_agentic_tracing()
    except Exception as exc:
        logger.warning("[Startup] Agentic tracing init failed (non-fatal): %s", exc)
