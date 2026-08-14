"""Centralised router registration for the Omni-Agent backend.

Call ``register_all_routers(app)`` once from ``app.py`` after the FastAPI
instance is created. Each router is independently wrapped so one bad import
never prevents subsequent routers from loading.
"""

from __future__ import annotations

import importlib
import logging
from fastapi import FastAPI, APIRouter, Depends

logger = logging.getLogger(__name__)

# Routers that MUST be present for the application to be usable.
# A load failure for any of these will abort startup rather than
# silently serve a broken app with missing endpoints.
_REQUIRED_ROUTERS: frozenset[str] = frozenset({
    "compliance_status_endpoints",
    "compliance_evidence_lifecycle_endpoints",
    "compliance_bulk_evidence_endpoints",
    "compliance_score_endpoints",
    # WR-04 (15-REVIEW.md): evidence_review_endpoints belongs to the same
    # evidence-lifecycle feature set as its siblings above — without this,
    # a broken import (e.g. of authentication_service or
    # evidence_review_service) would silently start the app with the
    # entire review/approve/reject workflow absent, surfaced only by a
    # single ERROR-level startup log line.
    "evidence_review_endpoints",
    # CR-02 (20-REVIEW.md): cloud_accounts_service raises RuntimeError at
    # import time when CLOUD_CREDENTIALS_KEY is unset in production, meant
    # to hard-block startup. Without being required here, that RuntimeError
    # is caught by _load()'s generic except-and-log path and swallowed —
    # the app boots fine with the entire /api/cloud-accounts/* surface
    # silently absent instead of refusing to start as intended.
    "cloud_account_endpoints",
})


def _load(app: FastAPI, module_name: str, attr: str = "router", **kwargs) -> None:
    """Import *module_name*, then include ``getattr(module, attr)`` into *app*.

    Failures are logged at ERROR level and never propagate — every other router
    still loads even if this one is broken.  For routers listed in
    ``_REQUIRED_ROUTERS``, the exception is re-raised so startup fails fast
    rather than running with a critical endpoint silently absent.
    """
    try:
        mod = importlib.import_module(module_name)
        app.include_router(getattr(mod, attr), **kwargs)
        logger.debug("[Router] Loaded %s", module_name)
    except Exception as exc:
        logger.error("[Router] Failed to load %s: %s", module_name, exc)
        if module_name in _REQUIRED_ROUTERS:
            raise


def register_all_routers(app: FastAPI) -> None:
    # ── Route aliases — registered FIRST so exact paths beat /{param} routes ──
    _load(app, "route_aliases", "router")

    # ── Core Infrastructure ───────────────────────────────────────────────────
    _load(app, "agent_endpoints", "router")

    # Global task-status alias expected by the frontend at /api/tasks/{id}
    try:
        task_router = APIRouter()

        @task_router.get("/tasks/{task_id}")
        async def global_task_status(
            task_id: str,
            current_user=Depends(__import__("authentication_service").get_current_user),
        ):
            from agent_endpoints import get_task_status
            return await get_task_status(task_id, current_user=current_user)

        app.include_router(task_router, prefix="/api")
    except Exception as exc:
        logger.error("[Router] Failed to register global task alias: %s", exc)

    _load(app, "itam_catalog_endpoints", "router")  # ITAM Phase 56 Catalog Router
    _load(app, "itam_asset_endpoints", "router")    # ITAM Phase 56 Asset Router
    _load(app, "itam_lifecycle_endpoints", "router")  # ITAM Phase 57 Lifecycle Router
    _load(app, "itam_license_endpoints",   "router")  # ITAM Phase 60 License Router
    _load(app, "itam_consumable_endpoints", "router")  # ITAM Phase 60 Consumable Router
    _load(app, "itam_component_endpoints", "router")  # ITAM Phase 60 Component Router
    _load(app, "itam_component_endpoints", "asset_components_router")  # ITAM Phase 60: GET /api/assets/{id}/components
    _load(app, "itam_label_endpoints",     "router")    # ITAM Phase 58 Label Router
    _load(app, "itam_finance_endpoints",   "router")    # ITAM Phase 59 Finance Router
    _load(app, "itam_data_endpoints",      "router")    # ITAM Phase 65 Data Import/Export Router
    _load(app, "itam_customization_endpoints", "router")  # ITAM Phase 65 Settings & Branding Router
    _load(app, "itam_procurement_endpoints", "router") # ITAM Phase 71 Procurement Router
    _load(app, "asset_endpoints",          "router")

    _load(app, "user_endpoints",           "router")
    _load(app, "api_key_endpoints",        "router")        # ITAM Phase 64-05 API Token Router
    _load(app, "api_key_endpoints",        "admin_router")  # ITAM Phase 64-05 API Token Admin Router
    _load(app, "tenant_endpoints",         "router")
    _load(app, "role_endpoints",           "router")
    _load(app, "authentication_endpoints",       "router")
    _load(app, "auth_password_reset_endpoints",  "router")
    _load(app, "audit_endpoints",          "router")
    _load(app, "cache_endpoints",          "router")
    _load(app, "repo_endpoints",           "router")
    _load(app, "mfa_endpoints",            "router")
    _load(app, "sso_endpoints",            "router")
    _load(app, "sso_endpoints",            "saml_router")  # ITAM Phase 64-04 SAML SSO Router
    _load(app, "ldap_endpoints",           "router")  # ITAM Phase 64-03 LDAP/AD Router

    # ── Security Intelligence Connectors ─────────────────────────────────────
    _load(app, "security_intel_status_endpoints", "router")

    # ── Security & Threat Management ──────────────────────────────────────────
    _load(app, "edr_telemetry_endpoints",  "router")
    _load(app, "agent_telemetry_endpoints", "router")
    _load(app, "response_endpoints",       "router")
    _load(app, "mdr_endpoints",            "router")
    _load(app, "security_endpoints",       "router")
    _load(app, "vuln_endpoints",           "router")
    _load(app, "threat_endpoints",         "router")
    _load(app, "threat_intel_endpoints",   "router")
    _load(app, "correlation_endpoints",    "router")
    _load(app, "siem_endpoints",           "router")
    _load(app, "itdr_endpoints",           "router")
    _load(app, "attack_path_endpoints",    "router")
    _load(app, "pentest_endpoints",        "router")
    _load(app, "zero_trust_service",       "router")
    _load(app, "trust_endpoints",          "router")
    # Genuinely public trust routes (TRUST-02/03) — no auth, no /api/trust-center
    # prefix; mounted so paths are exactly /api/public/trust/...
    _load(app, "trust_endpoints",          "public_router")
    _load(app, "governance_document_endpoints", "router")
    _load(app, "ueba_service",                "router")
    _load(app, "ip_ban_endpoints",            "router")
    _load(app, "agent_quarantine_endpoints",  "router")
    _load(app, "persistence_endpoints",       "router")
    _load(app, "mitre_endpoints",          "router")
    _load(app, "dast_service",             "router")
    _load(app, "sast_endpoints",           "router")
    _load(app, "dlp_endpoints",            "router")
    _load(app, "hadr_endpoints",           "router")
    _load(app, "secrets_endpoints",        "router")

    # ── Patch & Software Management ───────────────────────────────────────────
    _load(app, "patch_endpoints",             "router")
    _load(app, "sbom_endpoints",              "router")
    _load(app, "software_endpoints",          "router")
    _load(app, "update_endpoints",            "router")
    _load(app, "agent_download_endpoints",    "router")
    _load(app, "deployment_result_endpoints", "router")

    # ── Feature Bundles ───────────────────────────────────────────────────────
    _load(app, "bundle_endpoints",          "router")
    _load(app, "ticket_reports_endpoints",  "router")

    # ── Compliance & Governance ───────────────────────────────────────────────
    # compliance_evidence_endpoints.router is NOT loaded directly here — it is
    # mounted via compliance_endpoints.router.include_router(evidence_router)
    # (see compliance_endpoints.py). This is the alternate load path referenced
    # by WR-01 in 07-REVIEW.md; keep this comment in sync if that wiring changes.
    _load(app, "compliance_endpoints",      "router")
    _load(app, "compliance_scans_endpoints", "router")  # direct load — resilient if compliance_endpoints fails
    _load(app, "compliance_status_endpoints",  "router")
    _load(app, "ai_auditor_endpoints",      "router", prefix="/api/compliance", tags=["Compliance AI"])
    _load(app, "compliance_automation_api", "router")
    _load(app, "ai_governance_endpoints",   "router")
    _load(app, "cissp_oracle_endpoints",    "router")
    _load(app, "risk_endpoints",            "router")
    _load(app, "risk_fair_endpoints",       "router")
    _load(app, "agent_analyze_endpoints",   "router")
    _load(app, "mcp_rest_endpoints",        "router")
    _load(app, "vendor_endpoints",          "router")
    _load(app, "soa_endpoints",             "router")
    _load(app, "questionnaire_endpoints",   "router")
    _load(app, "questionnaire_inbound_endpoints", "router")
    # Review router MUST register before the draft router: both share the
    # /api/questionnaire-answer-drafts prefix, and the draft router's bare
    # GET /{draft_id} would otherwise shadow GET /pending-review.
    _load(app, "questionnaire_answer_review_endpoints", "router")
    _load(app, "questionnaire_answer_draft_endpoints", "router")
    _load(app, "maturity_endpoints",        "router")
    _load(app, "audit_program_endpoints",   "router")
    _load(app, "cookie_consent_endpoints",  "router")
    _load(app, "access_review_endpoints",   "router")
    _load(app, "cloud_checks_endpoints",    "router")
    _load(app, "compliance_remediation_endpoints", "router")
    _load(app, "compliance_remediation_sla_endpoints", "router")
    _load(app, "agent_location_history_endpoints", "router")
    _load(app, "geo_security_endpoints",    "router")
    _load(app, "compliance_evidence_lifecycle_endpoints", "router")
    _load(app, "compliance_bulk_evidence_endpoints", "router")
    _load(app, "compliance_score_endpoints", "router")
    _load(app, "saas_integration_endpoints", "router")
    _load(app, "saas_posture_checks_endpoints", "router")
    _load(app, "powershell_evidence_endpoints", "router")
    _load(app, "program_endpoints",             "router")
    _load(app, "evidence_review_endpoints", "router")
    _load(app, "control_comments_endpoints", "router")

    # ── AI & Data Science ─────────────────────────────────────────────────────
    _load(app, "ai_endpoints",             "router")
    _load(app, "ai_assistant_endpoints",   "router")
    _load(app, "ai_supervisor_endpoints",  "router")
    _load(app, "framework_mappings_endpoints", "router")
    _load(app, "ot_ics_endpoints",         "router")
    _load(app, "firmware_attestation_endpoints", "router")
    _load(app, "ai_services.training_endpoints", "router")
    _load(app, "ai_system_endpoints",      "router")
    _load(app, "ai_remediation_service",   "router")
    _load(app, "xai_endpoints",            "router")
    _load(app, "ml_monitoring_endpoints",  "router")
    _load(app, "prompt_endpoints",         "router")
    try:
        import llm_proxy
        app.include_router(llm_proxy.router)
        app.include_router(llm_proxy.chat_router)
    except Exception as exc:
        logger.error("[Router] Failed to load llm_proxy: %s", exc)
    _load(app, "model_retraining_endpoints", "router")
    _load(app, "automl_endpoints",           "router")
    _load(app, "agentic_tasks_endpoints",    "router")

    # ── Operations & Automation ───────────────────────────────────────────────
    _load(app, "future_ops_endpoints",          "router")
    _load(app, "ticketing_endpoints",           "router")
    _load(app, "soar_endpoints",                "router", prefix="/api/soar")
    _load(app, "playbook_endpoints",            "router")
    _load(app, "enhanced_playbook_endpoints",          "router")
    _load(app, "enhanced_playbook_template_endpoints", "router")
    _load(app, "automation_endpoints",          "router")
    _load(app, "policy_endpoints",              "router")
    _load(app, "alert_endpoints",               "router")
    _load(app, "jobs_endpoints",                "router")
    _load(app, "remediation_endpoints",         "router")
    _load(app, "simulation_endpoints",          "router")
    _load(app, "chaos_engineering_service",     "router")

    # ── FinOps & Sustainability ───────────────────────────────────────────────
    _load(app, "finops_endpoints",      "router")
    _load(app, "billing_endpoints",     "router")
    _load(app, "payment_endpoints",     "router")
    _load(app, "sustainability_service","router")

    # ── Data Platform ─────────────────────────────────────────────────────────
    _load(app, "data_lake_endpoints",              "router")
    _load(app, "etl_endpoints",                    "router")
    _load(app, "warehouse_endpoints",              "router")
    _load(app, "stream_processing_endpoints",      "router")
    _load(app, "data_governance_endpoints",        "router")
    _load(app, "system_health_endpoints",          "router")
    _load(app, "predictive_health_endpoints",      "router")
    _load(app, "goal_endpoints",                   "router")
    _load(app, "compliance_frameworks_endpoints",  "router")
    _load(app, "rollback_endpoints",               "router")
    _load(app, "pipeline_security_endpoints",      "router")
    _load(app, "iac_security_endpoints",           "router")
    _load(app, "container_scan_endpoints",         "router")
    _load(app, "pam_endpoints",                    "router")
    _load(app, "baa_endpoints",                    "router")
    _load(app, "dpa_endpoints",                    "router")

    # ── Global Search ─────────────────────────────────────────────────────────
    _load(app, "global_search_endpoints",    "router")

    # ── Certificate / TLS Tracking ────────────────────────────────────────────
    _load(app, "certificate_endpoints",      "router")

    # ── Post-Quantum Cryptography & Provenance ────────────────────────────────
    _load(app, "pqc_endpoints",          "router")
    _load(app, "provenance_endpoints",   "router")

    # ── Observability & Platform ──────────────────────────────────────────────
    _load(app, "network_endpoints",          "router")
    _load(app, "cloud_account_endpoints",    "router")
    _load(app, "iac_scanner_endpoints",       "router")
    _load(app, "container_scanner_endpoints", "router")
    _load(app, "integrations_v2",            "router")
    _load(app, "webhook_endpoints",          "router")
    _load(app, "notification_endpoints",     "router")
    _load(app, "domain_scanner_endpoints",   "router")
    # mcp_server_endpoints no longer exposes a REST router — Phase 37 replaced
    # it with the standalone FastMCP server (backend/mcp_server.py).
    _load(app, "ocsf_endpoints",              "router")
    _load(app, "oscal_endpoints",             "router") # NEW
    _load(app, "analytics_endpoints",        "router")
    _load(app, "settings_endpoints",         "router")
    _load(app, "log_endpoints",              "router")
    _load(app, "kpi_endpoints",              "router")
    _load(app, "tracing_endpoints",          "router")
    _load(app, "apm_endpoints",              "router")
    _load(app, "voice_endpoints",            "router")
    _load(app, "agent_metrics_endpoints",    "router")
    _load(app, "agent_uptime_endpoints",     "router")
    _load(app, "agent_fleet_observability_endpoints", "router")
    _load(app, "agent_fleet_geo_endpoints",  "router")
    _load(app, "agent_security_feed_endpoints", "router")
    _load(app, "agent_security_scan_endpoints", "router")
    _load(app, "asset_metrics_endpoints",    "router")
    _load(app, "digital_twin_service",       "router")
    _load(app, "swarm_endpoints",            "router")
    _load(app, "knowledge_endpoints",        "router")
    _load(app, "system_endpoints",           "router")
    _load(app, "final_endpoints",            "router")
    _load(app, "reporting_endpoints",        "router")
    _load(app, "export_report_endpoint",     "router")
    _load(app, "platform_endpoints",         "router")
    _load(app, "dora_endpoints",             "router")
    _load(app, "insights_endpoints",         "router")
    _load(app, "compliance_report_endpoints","router")

    # ── Optional / Feature Routers (non-fatal if missing) ────────────────────
    _OPTIONAL: list[tuple[str, dict]] = [
        ("ab_testing_endpoints",            {}),
        ("agent_remote_control",            {}),
        ("approval_endpoints",              {}),
        ("binary_analysis_endpoints",       {}),
        ("capability_endpoints",            {}),
        ("cloud_remediation_endpoints",     {}),
        ("compliance_automation_endpoints", {}),
        ("compliance_oracle_service",       {}),
        ("deployment_endpoints",            {}),
        ("email_endpoints",                 {}),
        ("file_share_endpoints",            {}),
        ("integration_endpoints",           {}),
        ("maintenance_endpoints",           {}),
        ("new_playbook_api",                {}),
        ("remote_endpoints",                {}),
        ("agent_chat_endpoints",            {}),
        ("service_mesh_service",            {}),
        ("swarm_service",                   {}),
        ("training_endpoints",              {}),
        ("ueba_endpoints",                  {}),
        ("tasks_endpoints",                 {}),
        ("cloud_integrations_endpoints",    {}),
        ("custom_framework_endpoints",      {}),
        ("deception_endpoints",             {}),
        ("jit_access_endpoints",            {}),
        ("incident_warroom_endpoints",      {}),
        ("passkey_endpoints",               {}), # NEW
        ("graphql_endpoints",               {}), # NEW
        ("privacy_endpoints",               {}),
        ("scheduled_reports_endpoints",     {}),
        ("retention_endpoints",             {}),
        ("api_security_endpoints",          {}),
        ("dam_endpoints",                   {}),
        ("k8s_security_endpoints",          {}),
        ("ndr_endpoints",                   {}),
        ("insider_threat_endpoints",        {}),
        ("email_security_endpoints",        {}),
        ("supply_chain_security_endpoints", {}),
        ("supply_chain_endpoints",          {}),
        ("code_review_graph_endpoints",     {}),
        ("tickets_workflow_endpoints",      {}),
        ("tickets_config_endpoints",        {}),
        ("tickets_endpoints",               {}),
        ("problem_management_endpoints",    {}),
        ("change_management_endpoints",     {}),
        ("support_endpoints",               {}),
        ("autopilot_endpoints",             {}),
        ("conditional_access_endpoints",    {}),
        ("mdm_endpoints",                   {}),
        ("branch_site_endpoints",           {}),
        ("app_catalog_endpoints",           {}),
        ("eol_rogue_endpoints",               {}),
        ("mam_endpoints",                     {}),
        ("android_enterprise_endpoints",      {}),
        ("device_config_profiles_endpoints",  {}),
        ("firmware_driver_endpoints",         {}),
        ("advanced_hunting_endpoints",        {}),
        ("detection_rules_endpoints",         {}),
        ("connectors_hub_endpoints",          {}),
        ("security_copilot_endpoints",        {}),
        ("mssp_endpoints",                    {}),
        ("retention_tiers_endpoints",         {}),
        ("sca_endpoints",                     {}),
        ("agent_group_endpoints",             {}),
        ("config_drift_endpoints",            {}),
        ("fim_endpoints",                     {}),
        ("active_response_endpoints",         {}),
        ("security_ops_endpoints",            {}),
        ("native_security_ops_endpoints",      {}),
        ("remediation_playbook_endpoints",     {}),
        ("remediation_control_endpoints",      {}),
    ]

    seen: set[str] = set()
    for module_name, kwargs in _OPTIONAL:
        if module_name in seen:
            continue
        seen.add(module_name)
        _load(app, module_name, "router", **kwargs)

