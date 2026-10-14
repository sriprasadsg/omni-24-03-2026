"""Startup helpers: config validation, database seeding, background service launcher."""

import asyncio
import logging
import os
from app_env import is_production
import secrets
import uuid
from datetime import datetime, timezone

from auth_utils import hash_password
from database import get_database
from migrations.runner import run_migrations
from rbac_defaults import seed_role_documents

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
    if not is_production():
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
    if is_production() and (jwt_key.lower() in _KNOWN_WEAK_JWT_VALUES or len(jwt_key) < 32):
        raise RuntimeError(
            "Refusing to start: JWT_SECRET_KEY is unset, a known-weak default or shorter than 32 "
            "characters. Remove it from the environment to use the provisioned platform key, or set "
            "a strong one. For local development set ENVIRONMENT=development."
        )
    if jwt_key.lower() in _KNOWN_WEAK_JWT_VALUES:
        issues.append(
            "JWT_SECRET_KEY is unset or uses a known-weak default. "
            "Generate a secure key: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )

    super_pass = os.getenv("SUPER_ADMIN_PASSWORD", "")
    if super_pass in {"", "your-secure-super-admin-password", "change-me-to-a-strong-password"}:
        issues.append("SUPER_ADMIN_PASSWORD is unset or uses a placeholder value.")

    if not os.getenv("CLOUD_CREDENTIALS_KEY", ""):
        issues.append(
            "CLOUD_CREDENTIALS_KEY is unset — cloud account credentials will use an "
            "ephemeral encryption key (dev only; production refuses to start without it). "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

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

    Runs on every startup so rule fixes in the source files reach the DB. A
    built-in is only refreshed while its stored content still equals what was
    last seeded (``seedHash``), so a platform admin's edit is never overwritten.
    Docs seeded before ``seedHash`` existed are refreshed once — the old parser
    truncated any rule containing a hex string or regex quantifier.
    """
    import hashlib
    import re
    from pathlib import Path

    yara_dir = Path(__file__).resolve().parent.parent / "agent" / "capabilities" / "yara_rules"
    if not yara_dir.is_dir():
        logger.debug("[YARA] yara_rules directory not found at %s — skipping seed", yara_dir)
        return

    # The closing brace must start a line: a non-greedy "\{(.*?)\}" stopped at the
    # first "}" inside a hex string ({ FC E8 ... }) or regex quantifier ({25,34}).
    rule_pattern = re.compile(
        r'^rule\s+(\w+)\s*(?::\s*[\w\s]+)?\{(.*?)^\}',
        re.DOTALL | re.MULTILINE,
    )
    meta_field = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    seeded = 0
    refreshed = 0
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
            content = rule_body.strip()
            rule_fields = {
                "name":        rule_name,
                "content":     content,
                "description": meta.get("description", f"Built-in {category} detection rule"),
                "severity":    meta.get("severity", "medium"),
                "mitre":       meta.get("mitre", ""),
                "family":      meta.get("family", ""),
                "category":    category,
                "seedHash":    _content_hash(content),
            }

            existing = await raw_db.custom_yara_rules.find_one(
                {"id": doc_id}, {"_id": 0, "content": 1, "seedHash": 1}
            )
            if existing is None:
                await raw_db.custom_yara_rules.update_one(
                    {"id": doc_id},
                    {"$setOnInsert": {
                        **rule_fields,
                        "id":        doc_id,
                        "source":    "builtin",
                        "enabled":   True,
                        "tenantId":  "platform-admin",
                        "createdBy": "system",
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    }},
                    upsert=True,
                )
                seeded += 1
                continue

            stored = existing.get("content", "")
            unmodified = (
                existing.get("seedHash") is None  # legacy (possibly truncated) seed
                or _content_hash(stored) == existing["seedHash"]
            )
            # Also stamp seedHash on legacy docs so later admin edits are recognised.
            if unmodified and (stored != content or existing.get("seedHash") is None):
                await raw_db.custom_yara_rules.update_one({"id": doc_id}, {"$set": rule_fields})
                refreshed += 1

    if seeded or refreshed:
        logger.info(
            "[YARA] Built-in detection rules from %s: %d seeded, %d refreshed",
            yara_dir, seeded, refreshed,
        )


# Passwords that were hardcoded as fallbacks in tracked scripts (start-all-services*.sh,
# diag2.py, fix_super_admin.py) before 2026-10-06 and so remain in git history.
_LEAKED_DEFAULT_PASSWORDS = ("Admin@2030",)


def _warn_if_leaked_default_password(stored_hash: str | None) -> bool:
    """Log CRITICAL when the super admin still uses a password published in the repo."""
    from auth_utils import verify_password
    if not stored_hash:
        return False
    for leaked in _LEAKED_DEFAULT_PASSWORDS:
        try:
            if verify_password(leaked, stored_hash):
                logger.critical(
                    "[Security] The super admin (super@omni.ai) still uses a default password that is "
                    "published in this repository's git history. Change it now from My Profile, or run "
                    "ADMIN_RESET_PASSWORD='<new password>' python reset_admin_password.py in backend/."
                )
                return True
        except Exception:
            continue
    return False


async def seed_database():
    """Create or refresh the super admin user, platform tenant and built-in roles.

    Steps: migrations, super admin user, platform tenant, one step that mirrors
    rbac_defaults into the 13 shared role documents (each document written
    independently), then the ITAM enabledFeatures backfill.

    ARCH-018 (2026-08-25 audit): this used to be one try/except wrapping
    every seeding step below. A failure partway through silently aborted every
    step after it too, with only one generic "Database seeding error" log line
    and no indication which step actually failed. Each step below now fails
    independently: one broken step is logged with its own message and does
    not prevent the others from running.
    """
    db = get_database()

    try:
        # Run schema migrations before any seeding so indexes exist before data is inserted
        await run_migrations(db._db)
    except Exception as e:
        logger.error("[Seed] Schema migrations failed: %s", e)

    try:
        raw_users = db._db.users

        super_admin = await raw_users.find_one({"email": "super@omni.ai"})
        if not super_admin:
            # Password is set only at first creation, from SUPER_ADMIN_PASSWORD
            # (or a random fallback, logged so the operator can retrieve it).
            # Mongo is the sole source of truth after this: no later restart,
            # env change, or re-seed ever touches this field again — rotate
            # the password via the login/reset flow, not by restarting.
            _super_admin_password = os.getenv("SUPER_ADMIN_PASSWORD")
            if not _super_admin_password:
                _super_admin_password = secrets.token_urlsafe(32)
                logger.warning(
                    "SUPER_ADMIN_PASSWORD env var not set — generated a random "
                    "password for the one-time super admin account creation: %s",
                    _super_admin_password,
                )

            logger.info("Creating new super admin user...")
            await raw_users.insert_one({
                "id": f"user-{uuid.uuid4()}",
                "tenantId": "platform-admin",
                "tenantName": "Platform",
                "name": "Super Admin",
                "email": "super@omni.ai",
                # `password` is the field login_for_access_token reads (as do
                # signup and every other user writer); a differently named
                # hash field leaves a fresh install with no usable admin login.
                "password": hash_password(_super_admin_password),
                "role": "Super Admin",
                "avatar": "https://i.pravatar.cc/150?u=super-admin",
                "status": "Active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            logger.info("Verifying existing super admin account status/role...")
            update: dict = {"$set": {"status": "Active", "role": "Super Admin"}}
            # Installs seeded by the old code stored the hash as `passwordHash`,
            # which login never reads. Move it to `password` once, so those
            # admins can log in with the SUPER_ADMIN_PASSWORD they were created
            # with; an existing `password` always wins and is never touched.
            if super_admin.get("passwordHash") and not super_admin.get("password"):
                update["$set"]["password"] = super_admin["passwordHash"]
                update["$unset"] = {"passwordHash": ""}
                logger.info("[Seed] Migrated legacy super admin passwordHash field to password")
            await raw_users.update_one({"email": "super@omni.ai"}, update)
            _warn_if_leaked_default_password(update["$set"].get("password") or super_admin.get("password"))

        logger.info("Super admin account verified.")
    except Exception as e:
        logger.error("[Seed] Super admin account seeding failed: %s", e)

    try:
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
    except Exception as e:
        logger.error("[Seed] Platform tenant seeding failed: %s", e)

    try:
        # D-12/D-13/D-25: every boot mirrors the single table (rbac_defaults) into the 13
        # shared role documents. The raw handle bypasses the tenant wrapper, which under the
        # platform-admin context passes a bare name filter through to every tenant's documents;
        # the {name, tenantId} filter keeps a tenant's own same-named document out of reach.
        raw_roles = db._db.roles
        role_docs = seed_role_documents()
        written = 0
        for doc in role_docs:
            try:
                await raw_roles.update_one(
                    {"name": doc["name"], "tenantId": doc["tenantId"]},
                    {"$set": doc},
                    upsert=True,
                )
                written += 1
            except Exception as e:
                logger.error("[Seed] Role %s seeding failed: %s", doc["name"], e)
        logger.info("Built-in role documents mirrored from rbac_defaults: %d of %d", written, len(role_docs))
    except Exception as e:
        logger.error("[Seed] Built-in role seeding failed: %s", e)

    try:
        # Backfill: tenants provisioned before ITAM (Phase 56-61) never had
        # view:itam/manage:itam written into their enabledFeatures — the
        # frontend intersects a user's role permissions against their
        # tenant's enabledFeatures (App.tsx), so a role grant alone doesn't
        # surface the ITAM console for pre-existing tenants without this.
        itam_backfill = await db.tenants.update_many(
            {"enabledFeatures": {"$nin": ["manage:itam"]}},
            {"$addToSet": {"enabledFeatures": {"$each": ["view:itam", "manage:itam"]}}},
        )
        if itam_backfill.modified_count:
            logger.info(f"Backfilled view:itam/manage:itam onto {itam_backfill.modified_count} existing tenant(s)")
    except Exception as e:
        logger.error("[Seed] ITAM enabledFeatures backfill failed: %s", e)


async def _prebuild_windows_agent() -> None:
    """Warm the Windows agent binary cache at startup so the first tenant
    download is instant.

    Delegates to agent_rust_builder._ensure_rust_binary — the same builder the
    download endpoints use (x86_64-pc-windows-gnu target, MinGW check, build
    lock, rustup-cargo precedence). This used to run its own host-target
    `cargo build --release` and check target/release/omni-agent.exe, a file a
    Linux build never produces, so every startup rebuilt and then logged a
    false "Pre-build complete" for a non-existent exe.
    """
    from pathlib import Path as _Path
    from fastapi import HTTPException as _HTTPException
    from agent_rust_builder import _ensure_rust_binary

    src_dir = _Path(__file__).resolve().parent.parent / "agent-install" / "omni-agent-rs"
    if not src_dir.is_dir():
        logger.debug("[WindowsAgent] agent source not present; skipping pre-build")
        return
    try:
        exe = await _ensure_rust_binary(src_dir)
    except _HTTPException as exc:
        logger.warning("[WindowsAgent] Pre-build skipped: %s", exc.detail)
        return
    logger.info("[WindowsAgent] Windows agent binary ready — %s", exe)


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

        endpoint = os.getenv("PHOENIX_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(provider)
        AnthropicInstrumentor().instrument()

        # Phase 39 (AISPEC-39-S5): wire LangChainInstrumentor spans into this
        # same Phoenix pipeline via ai_orchestration.tracing, reusing
        # `provider`/`endpoint` — single startup hook, graceful-degrade
        # internally so a missing package can never break the Anthropic
        # instrumentation that already succeeded above.
        try:
            from ai_orchestration.tracing import instrument_langchain
            instrument_langchain(provider)
        except Exception as lc_exc:
            logger.warning("[AgenticTracing] LangChain instrumentation wiring failed: %s", lc_exc)

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

    # Initialize AI provider from DB config (seeded or configured)
    try:
        from ai_service import ai_service
        await ai_service.initialize()
    except Exception as _e:
        logger.warning("[AI] Provider initialization failed: %s", _e)

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
    asyncio.create_task(_safe_bg_task(_start_xdr_correlation_scanner(), "xdr_correlation"), name="xdr_correlation")

    try:
        from threat_feed_sync import start_threat_feed_loop
        asyncio.create_task(_safe_bg_task(start_threat_feed_loop(db._db), "threat_feed_loop"))
    except Exception as _e:
        logger.warning("[ThreatFeed] Failed to start: %s", _e)

    try:
        from nvd_sync import start_nvd_sync_loop
        asyncio.create_task(_safe_bg_task(start_nvd_sync_loop(db._db), "nvd_sync_loop"), name="nvd_sync_loop")
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

    from app_background_tasks import (
        monitor_agent_status,
        compliance_evidence_sweep_loop, snapshot_compliance_scores_loop,
        agent_uptime_rollup_loop, license_seat_maintenance_loop, audit_maintenance_loop,
    )
    asyncio.create_task(_safe_bg_task(monitor_agent_status(), "agent_status_monitor"))
    asyncio.create_task(_safe_bg_task(compliance_evidence_sweep_loop(), "compliance_evidence_sweep"))
    asyncio.create_task(_safe_bg_task(snapshot_compliance_scores_loop(), "compliance_score_snapshot"))
    asyncio.create_task(_safe_bg_task(agent_uptime_rollup_loop(), "agent_uptime_rollup"))
    asyncio.create_task(_safe_bg_task(license_seat_maintenance_loop(), "license_seat_maintenance"))
    asyncio.create_task(_safe_bg_task(audit_maintenance_loop(), "audit_maintenance"))

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
        from ticketing_bridge import start_close_loop_scheduler
        from database import mongodb as _mdb
        asyncio.create_task(start_close_loop_scheduler(_mdb.db))
        logger.info("[Ticketing] Remediation close-loop scheduler started")
    except Exception as _e:
        logger.warning("[Ticketing] Close-loop scheduler failed to start: %s", _e)

    try:
        from compliance_remediation_sla_service import start_remediation_sla_scheduler
        from database import mongodb as _mdb
        asyncio.create_task(start_remediation_sla_scheduler(_mdb.db))
        logger.info("[Remediation] SLA escalation scheduler started")
    except Exception as _e:
        logger.warning("[Remediation] SLA escalation scheduler failed to start: %s", _e)

    try:
        from itam_finance_service import start_warranty_alert_scheduler
        from database import mongodb as _mdb
        asyncio.create_task(start_warranty_alert_scheduler(_mdb.db))
        logger.info("[ITAM] Warranty alert scheduler started")
    except Exception as _e:
        logger.warning("[ITAM] Warranty alert scheduler failed to start: %s", _e)

    try:
        from itam_event_sweeps import start_itam_event_sweep_scheduler
        from database import mongodb as _mdb
        asyncio.create_task(start_itam_event_sweep_scheduler(_mdb.db))
        logger.info("[ITAM] Event sweep scheduler started (audit-overdue + stuck-approval)")
    except Exception as _e:
        logger.warning("[ITAM] Event sweep scheduler failed to start: %s", _e)

    try:
        from syslog_receiver import start_syslog_server
        _syslog_port = int(os.getenv("SYSLOG_UDP_PORT", "5140"))
        asyncio.create_task(start_syslog_server(host="0.0.0.0", port=_syslog_port), name="syslog_receiver")
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
            asyncio.create_task(getattr(_mod, func)(), name=func)
            logger.info("%s polling started", label)
        except Exception as _e:
            logger.warning("%s ingest not started: %s", label, _e)

    try:
        from jit_access_service import start_jit_expiry_loop
        asyncio.create_task(start_jit_expiry_loop(), name="jit_expiry_loop")
        logger.info("[JIT] Expiry enforcement loop started")
    except Exception as _e:
        logger.warning("[JIT] Expiry loop not started: %s", _e)

    try:
        from scheduled_reports_service import start_report_scheduler
        asyncio.create_task(start_report_scheduler(), name="report_scheduler")
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

    from app_background_tasks import autonomous_remediation_loop
    asyncio.create_task(_safe_bg_task(autonomous_remediation_loop(), "autonomous_remediation"))

    try:
        init_agentic_tracing()
    except Exception as exc:
        logger.warning("[Startup] Agentic tracing init failed (non-fatal): %s", exc)
