
import os
import sys
from database import connect_to_mongo, close_mongo_connection, get_database
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Any, List, Dict, Optional
import logging
from datetime import datetime, timedelta, timezone
import uuid
import random
from contextlib import asynccontextmanager
from tenant_context import set_tenant_id, get_tenant_id
from authentication_service import verify_token
import jwt
from auth_utils import hash_password, verify_password
from email_service import email_service
import re
import asyncio
from audit_service import get_audit_service
from security_service import get_security_service
from deployment_service import get_deployment_service
import authentication_endpoints
from bi_analytics_service import get_bi_analytics_service
from pagination_utils import paginate_mongo_query, PaginationParams
import jobs_endpoints
from health_service import get_system_health

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from network_traffic_simulator import run_network_traffic_simulator

# WebSocket for real-time notifications
from websocket_manager import sio
import socketio

# --- Background Tasks ---

async def monitor_agent_status():
    """Background task to mark agents as Offline if inactive > 2 min"""
    import websocket_manager
    
    while True:
        try:
            await asyncio.sleep(60) # Run every minute
            db = get_database()
            # 1. Update stale agents (no heartbeat for > 15 minutes)
            threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
            
            result = await db.agents.update_many(
                {
                    "status": "Online",
                    "lastSeen": {"$lt": threshold.isoformat()}
                },
                {"$set": {"status": "Offline"}}
            )
            if result.modified_count > 0:
                print(f"[Monitor] Marked {result.modified_count} stale agents as Offline")
                
                # Get the affected agents to broadcast updates
                affected_agents = await db.agents.find(
                    {"status": "Offline", "lastSeen": {"$lt": threshold.isoformat()}}
                ).to_list(length=result.modified_count)
                
                # Broadcast real-time updates for each affected agent
                for agent in affected_agents:
                    tenant_id = agent.get("tenantId")
                    if tenant_id:
                        await websocket_manager.broadcast_agent_status_change(
                            tenant_id=tenant_id,
                            agent_id=agent.get("id"),
                            status="Offline",
                            details={"reason": "Heartbeat timeout"}
                        )
                
                # Trigger Notification (Async)
                from notification_manager import notification_manager
                await notification_manager.send_notification("agent.offline", {
                    "count": result.modified_count, 
                    "timestamp": datetime.now().isoformat()
                }, "platform-admin")
                
        except Exception as e:
            print(f"[Monitor] Error in stale agent check: {e}")

async def seed_database():
    """Create default super admin user if database is empty"""
    try:
        db = get_database()
        
        # Check if super admin exists
        super_admin = await db.users.find_one({"email": "super@omni.ai"})
        
        # Always define the standard super admin object
        super_admin_data = {
            "tenantId": "platform-admin",
            "tenantName": "Platform",
            "name": "Super Admin",
            "email": "super@omni.ai",
            "password": hash_password("password123"), # Fix: field name must be 'password' to match auth endpoints
            "role": "Super Admin",
            "avatar": "https://i.pravatar.cc/150?u=super-admin",
            "status": "Active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        if not super_admin:
            print("[INFO] Creating new super admin user...")
            super_admin_data["id"] = f"user-{uuid.uuid4()}"
            await db.users.insert_one(super_admin_data)
        else:
            print("[INFO] Updating existing super admin credentials...")
            # Update password and ensure active status
            await db.users.update_one(
                {"email": "super@omni.ai"},
                {"$set": {
                    "password": super_admin_data["password"], # Fix: field name must be 'password'
                    "status": "Active",
                    "role": "Super Admin"
                }}
            )
            
        print(f"[SUCCESS] Super admin verified: super@omni.ai / password123")
            
        # Create platform tenant if it doesn't exist
        platform_tenant = await db.tenants.find_one({"id": "platform-admin"})
        if not platform_tenant:
            tenant = {
                "id": "platform-admin",
                "name": "Platform",
                "subscriptionTier": "Enterprise",
                "registrationKey": f"platform-{uuid.uuid4()}",
                "enabledFeatures": [],
                "apiKeys": [],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.tenants.insert_one(tenant)
            print("Platform tenant created")
            
        # Force update Super Admin Role to ensure new permissions are present
        all_permissions = [
            'view:dashboard', 'view:reporting', 'export:reports', 'view:agents',
            'view:software_deployment', 'view:agent_logs', 'remediate:agents', 'view:assets',
            'view:patching', 'manage:patches', 'view:security', 'manage:security_cases',
            'manage:security_playbooks', 'investigate:security', 'view:compliance',
            'manage:compliance_evidence', 'view:ai_governance', 'manage:ai_risks',
            'manage:settings', 'manage:tenants', 'view:cloud_security', 'view:finops',
            'view:audit_log', 'manage:rbac', 'manage:api_keys', 'view:logs',
            'view:threat_hunting', 'view:profile', 'view:automation', 'manage:automation',
            'view:devsecops', 'manage:devsecops', 'view:sbom', 'manage:sbom',
            'view:developer_hub', 'view:insights', 'view:tracing',
            'view:dspm', 'view:attack_path', 'view:service_catalog', 'view:dora_metrics',
            'view:chaos', 'view:network', 'manage:pricing', 'view:software_updates',
            'view:zero_trust'
        ]
        
        await db.roles.update_one(
            {"name": "Super Admin"},
            {"$set": {
                "id": "role-super-admin",
                "name": "Super Admin",
                "description": "Has all permissions across all tenants.",
                "permissions": all_permissions,
                "isEditable": False,
                "tenantId": "platform"
            }},
            upsert=True
        )
        print("Super Admin role permissions updated")
        
        # Create Tenant Admin role (All features, NO administration)
        tenant_admin_permissions = [
            'view:dashboard', 'view:reporting', 'export:reports', 
            'view:agents', 'view:software_deployment', 'view:agent_logs', 'remediate:agents',
            'view:assets', 'view:patching', 'manage:patches', 'view:security', 
            'manage:security_cases', 'investigate:security', 'view:compliance',
            'manage:compliance_evidence', 'view:ai_governance', 'manage:ai_risks',
            'view:cloud_security', 'view:finops', 'view:audit_log',
            'manage:rbac', 'manage:api_keys', 'view:logs', 'view:profile',
            'view:automation', 'manage:automation', 'view:devsecops', 'manage:devsecops',
            'view:sbom', 'manage:sbom', 'view:insights', 'view:software_updates',
            'view:threat_hunting', 'view:tracing', 'view:dspm', 'view:attack_path',
            'view:service_catalog', 'view:dora_metrics', 'view:chaos', 'view:network',
            'view:zero_trust', 'view:developer_hub', 'manage:security_playbooks',
            'view:cxo_dashboard', 'view:unified_ops', 'view:advanced_bi',
            'view:sustainability', 'view:web_monitoring', 'view:analytics', 
            'view:threat_intel', 'view:vulnerabilities', 'view:persistence',
            'view:security_audit', 'view:mlops', 'view:llmops', 'view:automl',
            'manage:experiments', 'view:xai', 'view:governance', 'manage:playbooks',
            'view:swarm'
        ]
        
        await db.roles.update_one(
            {"name": "Tenant Admin"},
            {"$set": {
                "id": "role-tenant-admin",
                "name": "Tenant Admin",
                "description": "Administrator for a specific tenant with full permissions except cross-tenant management.",
                "permissions": tenant_admin_permissions,
                "isEditable": False,
                "tenantId": "all"
            }},
            upsert=True
        )
        print("Tenant Admin role created/updated")
            
    except Exception as e:
        print(f"Database seeding error: {e}")

# --- Lifespan & App Init ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Startup
        print("DEBUG: All Routes:")
        for r in app.routes:
            print(f" - {r.path}")
        await connect_to_mongo()
        
        # Seed database with super admin if it doesn't exist
        await seed_database()

        # Start background monitor
        asyncio.create_task(monitor_agent_status())
        
        # Start deployment scheduler
        try:
            from scheduler import start_scheduler as start_deployment_scheduler
            start_deployment_scheduler()
        except ImportError:
            print("\u26a0\ufe0f Deployment scheduler module not found, skipping")
        
        # Start finOps scheduler
        try:
            from finops_scheduler import start_scheduler as start_finops_scheduler
            start_finops_scheduler()
        except ImportError:
            print("\u26a0\ufe0f FinOps scheduler module not found, skipping")
            
        # Start SIEM Listeners
        # try:
        #     from syslog_receiver import start_syslog_server
        #     from aws_cloudtrail_ingest import start_aws_polling
        #     from okta_log_ingest import start_okta_polling
        #     asyncio.create_task(start_syslog_server(host="0.0.0.0", port=5140))
        #     asyncio.create_task(start_aws_polling())
        #     asyncio.create_task(start_okta_polling())
        #     print("SIEM Background workers started (Syslog, AWS, Okta)")
        # except ImportError as e:
        #     print(f"SIEM listeners modules not found, skipping: {e}")

        # Start Network Traffic Simulator
        # asyncio.create_task(run_network_traffic_simulator())
        
        yield
        # Shutdown
        try:
            from scheduler import stop_scheduler as stop_deployment_scheduler
            stop_deployment_scheduler()
        except ImportError:
            pass
        
        try:
            from finops_scheduler import stop_scheduler as stop_finops_scheduler
            stop_finops_scheduler()
        except ImportError:
            pass
        await close_mongo_connection()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"CRITICAL ERROR IN LIFESPAN: {e}")
        raise e

# Initialize rate limiter BEFORE creating app
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Omni Backend", version="2030.0", lifespan=lifespan)

# --- Emergency / High Priority Routers ---
import dr_endpoints
app.include_router(dr_endpoints.router)
import siem_endpoints
app.include_router(siem_endpoints.router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount static files
from fastapi.staticfiles import StaticFiles
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/api/ws/remote/{agent_id}")
async def websocket_remote_shell(websocket: WebSocket, agent_id: str):
    print(f"DEBUG: Remote Shell connection attempt from {agent_id}")
    await websocket.accept()
    try:
        while True:
            # Relay loop
            # 1. Receive data from agent (stdout/stderr)
            data = await websocket.receive_text()
            print(f"AGENT [{agent_id}]: {data}")
            
            # 2. For demo purposes, we just acknowledge or send a dummy command
            # In a real scenario, this would relay from a frontend admin user
            if "Shell Ready" in data:
                 await websocket.send_text("echo 'Hello from Backend'")
            
    except WebSocketDisconnect:
        print(f"DEBUG: Remote Shell disconnected for {agent_id}")

# --- Middleware ---

from tenant_middleware import TenantMiddleware
from usage_middleware import UsageTrackingMiddleware

# Parse CORS Origins from environment if available
cors_env = os.getenv("CORS_ORIGINS", "")
if cors_env:
    allowed_origins = [o.strip() for o in cors_env.split(',')]
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.10.214:3000",
        "http://192.168.90.68:3000",
        "http://172.26.80.1:3000"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

app.add_middleware(TenantMiddleware)
app.add_middleware(UsageTrackingMiddleware)

# --- Health Check ---

@app.get("/health")
async def health():
    return {"status": "ok", "service": "backend-fastapi", "edition": "2030"}

@app.get("/api/health")
async def api_health():
    return {"status": "ok", "service": "backend-fastapi", "edition": "2030"}

@app.get("/api/health/extended")
async def extended_health():
    """Runs deep checks on binaries and integrations."""
    health_data = await get_system_health()
    return {
        "status": "ok" if all(health_data["binaries"].values()) else "degraded",
        "details": health_data
    }

@app.get("/")
async def root():
    return {"message": "Omni Platform Backend API"}

@app.get("/api/metrics")
async def get_system_metrics():
    import psutil
    return [
        {"name": "CPU Usage", "value": psutil.cpu_percent(), "unit": "%"},
        {"name": "Memory Usage", "value": psutil.virtual_memory().percent, "unit": "%"},
        {"name": "Disk Usage", "value": psutil.disk_usage('/').percent, "unit": "%"}
    ]

@app.get("/static/win-install.ps1")
async def serve_win_install():
    file_path = os.path.join(os.path.dirname(__file__), "static", "win-install.ps1")
    if os.path.exists(file_path):
        from fastapi.responses import FileResponse
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

# ─────────────────────────────────────────────────────────────────────────────
# API ROUTER CONSOLIDATION (Phases 1-12)
# ─────────────────────────────────────────────────────────────────────────────

# --- Core Infrastructure ---
try:
    from agent_endpoints import router as agent_router
    app.include_router(agent_router)
    from asset_endpoints import router as asset_router
    app.include_router(asset_router)
    from user_endpoints import router as user_router
    app.include_router(user_router)
    from tenant_endpoints import router as tenant_router
    app.include_router(tenant_router)
    from role_endpoints import router as role_router
    app.include_router(role_router)
    from authentication_endpoints import router as auth_endpoints_router
    app.include_router(auth_endpoints_router)
    from audit_endpoints import router as audit_router
    app.include_router(audit_router)
    from cache_endpoints import router as cache_router
    app.include_router(cache_router)
    from repo_endpoints import router as repo_router
    app.include_router(repo_router)
    from mfa_endpoints import router as mfa_router
    app.include_router(mfa_router)
    from sso_endpoints import router as sso_router
    app.include_router(sso_router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] Core router load failed: {e}")

# --- Security & Threat Management ---
try:
    import edr_telemetry_endpoints
    app.include_router(edr_telemetry_endpoints.router)
    import response_endpoints
    app.include_router(response_endpoints.router)
    import security_endpoints
    app.include_router(security_endpoints.router)
    import vuln_endpoints
    app.include_router(vuln_endpoints.router)
    import threat_endpoints
    app.include_router(threat_endpoints.router)
    import threat_intel_endpoints
    app.include_router(threat_intel_endpoints.router)
    import correlation_endpoints
    app.include_router(correlation_endpoints.router)
    import siem_endpoints
    app.include_router(siem_endpoints.router)
    import itdr_endpoints
    app.include_router(itdr_endpoints.router)
    import attack_path_endpoints
    app.include_router(attack_path_endpoints.router)
    import pentest_endpoints
    app.include_router(pentest_endpoints.router)
    import zero_trust_service
    app.include_router(zero_trust_service.router)
    import trust_endpoints
    app.include_router(trust_endpoints.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"ERROR: Security router load failed: {e}")

# --- Patch & Software Management ---
try:
    from patch_endpoints import router as patch_router
    app.include_router(patch_router)
    import sbom_endpoints
    app.include_router(sbom_endpoints.router)
    import software_endpoints
    app.include_router(software_endpoints.router)
    import update_endpoints
    app.include_router(update_endpoints.router)
    import agent_download_endpoints
    app.include_router(agent_download_endpoints.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] Patch router load failed: {e}")

# --- Compliance & Governance ---
try:
    import compliance_endpoints
    app.include_router(compliance_endpoints.router)
    import ai_auditor_endpoints
    app.include_router(ai_auditor_endpoints.router, prefix="/api/compliance", tags=["Compliance AI"])
    import compliance_automation_api
    app.include_router(compliance_automation_api.router)
    import ai_governance_endpoints
    app.include_router(ai_governance_endpoints.router)
    import cissp_oracle_endpoints
    app.include_router(cissp_oracle_endpoints.router)
    import risk_endpoints
    app.include_router(risk_endpoints.router)
    import vendor_endpoints
    app.include_router(vendor_endpoints.router)
    import trust_endpoints
    app.include_router(trust_endpoints.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] Compliance router load failed: {e}")

# --- AI & Data Science ---
try:
    import ai_endpoints
    app.include_router(ai_endpoints.router)
    from ai_services.training_endpoints import router as training_router
    app.include_router(training_router)
    import ai_system_endpoints
    app.include_router(ai_system_endpoints.router)
    import xai_endpoints
    app.include_router(xai_endpoints.router)
    import ml_monitoring_endpoints
    app.include_router(ml_monitoring_endpoints.router)
    import prompt_endpoints
    app.include_router(prompt_endpoints.router)
    import llm_proxy
    app.include_router(llm_proxy.router)
    app.include_router(llm_proxy.chat_router)
    import model_retraining_endpoints
    app.include_router(model_retraining_endpoints.router)
    import automl_endpoints
    app.include_router(automl_endpoints.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] AI router load failed: {e}")

# --- Operations & Automation ---
try:
    import future_ops_endpoints
    app.include_router(future_ops_endpoints.router)
    import ticketing_endpoints
    app.include_router(ticketing_endpoints.router)
    import soar_endpoints
    app.include_router(soar_endpoints.router, prefix="/api/soar")
    import playbook_endpoints
    app.include_router(playbook_endpoints.router)
    import enhanced_playbook_endpoints
    app.include_router(enhanced_playbook_endpoints.router)
    import automation_endpoints
    app.include_router(automation_endpoints.router)
    import alert_endpoints
    app.include_router(alert_endpoints.router)
    import jobs_endpoints
    app.include_router(jobs_endpoints.router)
    import remediation_endpoints
    app.include_router(remediation_endpoints.router)
    import simulation_endpoints
    app.include_router(simulation_endpoints.router)
    import chaos_engineering_service
    app.include_router(chaos_engineering_service.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] Ops router load failed: {e}")

# --- FinOps & Sustainability ---
try:
    import finops_endpoints
    app.include_router(finops_endpoints.router)
    import billing_endpoints
    app.include_router(billing_endpoints.router)
    import payment_endpoints
    app.include_router(payment_endpoints.router)
    import sustainability_service
    app.include_router(sustainability_service.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] FinOps router load failed: {e}")

# --- Data Platform ---
try:
    import data_lake_endpoints
    app.include_router(data_lake_endpoints.router)
    import etl_endpoints
    app.include_router(etl_endpoints.router)
    import warehouse_endpoints
    app.include_router(warehouse_endpoints.router)
    import stream_processing_endpoints
    app.include_router(stream_processing_endpoints.router)
    import data_governance_endpoints
    app.include_router(data_governance_endpoints.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] Data Platform router load failed: {e}")

# --- Special Features ---
try:
    import network_endpoints
    app.include_router(network_endpoints.router)
    import cloud_account_endpoints
    app.include_router(cloud_account_endpoints.router)
    import integrations_v2
    app.include_router(integrations_v2.router)
    import webhook_endpoints
    app.include_router(webhook_endpoints.router)
    import notification_endpoints
    app.include_router(notification_endpoints.router)
    import analytics_endpoints
    app.include_router(analytics_endpoints.router)
    import settings_endpoints
    app.include_router(settings_endpoints.router)
    import log_endpoints
    app.include_router(log_endpoints.router)
    import kpi_endpoints
    app.include_router(kpi_endpoints.router)
    import tracing_endpoints
    app.include_router(tracing_endpoints.router)
    import apm_endpoints
    app.include_router(apm_endpoints.router)
    import voice_endpoints
    app.include_router(voice_endpoints.router)
    import agent_metrics_endpoints
    app.include_router(agent_metrics_endpoints.router)
    import asset_metrics_endpoints
    app.include_router(asset_metrics_endpoints.router)
    import digital_twin_service
    app.include_router(digital_twin_service.router)
    import swarm_endpoints
    app.include_router(swarm_endpoints.router)
    import knowledge_endpoints
    app.include_router(knowledge_endpoints.router)
    import system_endpoints
    app.include_router(system_endpoints.router)
    import final_endpoints
    app.include_router(final_endpoints.router)
    import export_report_endpoint
    app.include_router(export_report_endpoint.router)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"[CRITICAL] Special router load failed: {e}")

# --- Final Initialization ---
socket_app = socketio.ASGIApp(sio, app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(socket_app, host="0.0.0.0", port=5010)
