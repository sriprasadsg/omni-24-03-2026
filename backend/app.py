
import os
import sys
import socket
import secrets
from database import connect_to_mongo, close_mongo_connection, get_database
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Any, List, Dict, Optional
import logging
from datetime import datetime, timedelta, timezone
import uuid
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)
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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from rate_limiter import limiter

from network_traffic_simulator import run_network_traffic_simulator

# WebSocket for real-time notifications
from websocket_manager import sio
import socketio

# --- Background Tasks ---

async def monitor_agent_status():
    """Background task to mark agents as Offline if inactive > 2 min"""
    import websocket_manager
    from tenant_context import set_tenant_id
    
    while True:
        try:
            await asyncio.sleep(60) # Run every minute
            set_tenant_id("platform-admin")
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
                logger.info("[Monitor] Marked %d stale agents as Offline", result.modified_count)
                
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
            logger.error("[Monitor] Error in stale agent check: %s", e)

async def _start_xdr_correlation_scanner() -> None:
    """
    Background task: fetch all active tenant IDs from MongoDB and run
    the XDR correlation engine against each one every 5 minutes.
    New tenants are picked up automatically on the next cycle.
    """
    import logging as _logging
    _log = _logging.getLogger("xdr_scanner")
    _log.info("XDR correlation scanner starting (interval=300s)")

    while True:
        try:
            from correlation_engine import get_correlation_engine
            db = get_database()
            # INTENTIONAL: platform-admin task — iterates all tenants, passes raw db to engine
            # CorrelationEngine receives tenantId per-call via engine.correlate_events(tid, ...)
            tenants = await db._db.tenants.find({}, {"id": 1}).to_list(length=500)
            engine = get_correlation_engine(db._db)
            for tenant in tenants:
                tid = tenant.get("id")
                if tid:
                    try:
                        found = await engine.correlate_events(tid, time_window_minutes=60)
                        if found:
                            _log.info("XDR: %d correlation(s) for tenant %s", len(found), tid)
                    except Exception as _te:
                        _log.error("XDR correlation error for tenant %s: %s", tid, _te)
        except Exception as _e:
            import logging as _l
            _l.getLogger("xdr_scanner").error("XDR scanner cycle error: %s", _e)

        await asyncio.sleep(300)  # 5-minute scan interval


async def seed_database():
    """Create default super admin user if database is empty"""
    try:
        db = get_database()
        # Use raw collection to bypass tenant isolation — bootstrap has no request context
        raw_users = db._db.users

        # Check if super admin exists
        super_admin = await raw_users.find_one({"email": "super@omni.ai"})

        _super_admin_password = os.getenv("SUPER_ADMIN_PASSWORD")
        if not _super_admin_password:
            _super_admin_password = secrets.token_urlsafe(32)
            logger.warning(
                "SUPER_ADMIN_PASSWORD env var not set — generated a random password. "
                "Set the variable explicitly for a stable super admin login."
            )

        # Always define the standard super admin object
        super_admin_data = {
            "tenantId": "platform-admin",
            "tenantName": "Platform",
            "name": "Super Admin",
            "email": "super@omni.ai",
            "password": hash_password(_super_admin_password),
            "role": "Super Admin",
            "avatar": "https://i.pravatar.cc/150?u=super-admin",
            "status": "Active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

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
                    "role": "Super Admin"
                }}
            )

        logger.info("Super admin account verified.")
            
        # Create platform tenant if it doesn't exist
        platform_tenant = await db.tenants.find_one({"id": "platform-admin"})
        if not platform_tenant:
            _reg_key = os.getenv("PLATFORM_ADMIN_REG_KEY") or secrets.token_urlsafe(32)
            if not os.getenv("PLATFORM_ADMIN_REG_KEY"):
                logger.warning("PLATFORM_ADMIN_REG_KEY env var not set — generated a random registration key. Set it explicitly for a stable value.")
            logger.info("Platform tenant created successfully.")
            tenant = {
                "id": "platform-admin",
                "name": "Platform",
                "subscriptionTier": "Enterprise",
                "registrationKey": _reg_key,
                "enabledFeatures": [],
                "apiKeys": [],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.tenants.insert_one(tenant)
            
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
            'view:zero_trust', 'view:mdr', 'view:xdr', 'view:agent_capabilities',
            'manage:agents', 'admin:*'
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
        logger.info("Super Admin role permissions updated")
        
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
            'view:swarm', 'view:mdr', 'view:xdr', 'view:agent_capabilities',
            'manage:pricing', 'manage:agents', 'view:integrations'
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
        logger.info("Tenant Admin role created/updated")
            
    except Exception as e:
        logger.error("Database seeding error: %s", e)

# --- Lifespan & App Init ---

async def _safe_bg_task(coro, name: str) -> None:
    """Run a background coroutine; log exceptions instead of silently dropping them."""
    try:
        await coro
    except Exception as _exc:
        logger.error("Background task '%s' failed: %s", name, _exc, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Startup
        await connect_to_mongo()

        # All seeding runs under platform-admin context so TenantIsolatedCollection
        # bypasses the tenant check and doesn't fire spurious [SECURITY ALERT] logs.
        set_tenant_id("platform-admin")

        # Seed database with super admin if it doesn't exist
        await seed_database()

        # Run database migrations for multi-tenant isolation fixes
        try:
            from database_migrations import migrate_compliance_tenant_ids, migrate_instructions_tenant_ids, migrate_tenant_registration_keys, seed_compliance_frameworks
            await migrate_compliance_tenant_ids()
            await migrate_instructions_tenant_ids()
            await migrate_tenant_registration_keys()
            await seed_compliance_frameworks()
        except Exception as _e:
            logger.warning("[Migrations] Database self-healing migrations failed: %s", _e)

        # -- MDR: Seed built-in response policies ---
        try:
            from response_endpoints import initialize_response_module
            await initialize_response_module()
        except Exception as _e:
            logger.warning("[MDR] Response policy seeding failed: %s", _e)

        # -- Orchestrator: Seed built-in autonomous response policies --
        try:
            from response_orchestrator import seed_builtin_policies
            await seed_builtin_policies()
        except Exception as _e:
            logger.warning("[Orchestrator] Policy seeding failed: %s", _e)

        # -- XDR: Seed built-in correlation playbooks ---
        try:
            from xdr_playbook_seeds import seed_xdr_playbooks
            await seed_xdr_playbooks()
        except Exception as _e:
            logger.warning("[XDR] Playbook seeding failed: %s", _e)

        # ── XDR: Start periodic correlation scanner ───────────────────
        asyncio.create_task(_safe_bg_task(_start_xdr_correlation_scanner(), "xdr_correlation"))

        # -- Threat Feed: Auto-sync IOCs from abuse.ch / OTX ---
        try:
            from threat_feed_sync import start_threat_feed_loop
            _tfs_db = get_database()._db
            asyncio.create_task(_safe_bg_task(start_threat_feed_loop(_tfs_db), "threat_feed_loop"))
        except Exception as _e:
            logger.warning("[ThreatFeed] Failed to start: %s", _e)

        # -- NVD CVE Sync: populate db.patches with real CVE data ---
        try:
            from nvd_sync import start_nvd_sync_loop
            _nvd_db = get_database()._db
            asyncio.create_task(_safe_bg_task(start_nvd_sync_loop(_nvd_db), "nvd_sync_loop"))
        except Exception as _e:
            logger.warning("[NVD] CVE sync failed to start: %s", _e)

        # -- FinOps Usage Tracker: aggregate billable activity every 5 min ---
        try:
            from usage_tracker import start_usage_tracking_loop
            asyncio.create_task(_safe_bg_task(start_usage_tracking_loop(), "usage_tracking"))
        except Exception as _e:
            logger.warning("[UsageTracker] Failed to start: %s", _e)

        # ── Playbook approval timeout processor ───────────────────────
        async def _approval_timeout_loop():
            from enhanced_playbook_engine import process_approval_timeouts
            from database import get_database
            from tenant_context import set_tenant_id
            import logging as _logging
            _atl_log = _logging.getLogger("approval_timeout_loop")
            while True:
                try:
                    db = get_database()
                    # INTENTIONAL: platform-admin task — process_approval_timeouts
                    # accepts raw AsyncIOMotorDatabase and applies tenantId filters internally
                    set_tenant_id("platform-admin")
                    await process_approval_timeouts(db._db)
                except Exception as _e:
                    _atl_log.warning("Approval timeout processor error: %s", _e)
                await asyncio.sleep(60)
        asyncio.create_task(_approval_timeout_loop())

        # Start background monitor
        asyncio.create_task(_safe_bg_task(monitor_agent_status(), "agent_status_monitor"))
        
        # Start deployment scheduler
        try:
            from scheduler import start_scheduler as start_deployment_scheduler
            start_deployment_scheduler()
        except ImportError:
            logger.warning("[Scheduler] Deployment scheduler module not found, skipping")
        
        # Start finOps scheduler
        try:
            from finops_scheduler import start_scheduler as start_finops_scheduler
            start_finops_scheduler()
        except ImportError:
            logger.warning("[FinOps] Scheduler module not found, skipping")
            
        # Start SIEM Listeners
        try:
            from syslog_receiver import start_syslog_server
            _syslog_port = int(os.getenv("SYSLOG_UDP_PORT", "5140"))
            asyncio.create_task(start_syslog_server(host="0.0.0.0", port=_syslog_port))
            logger.info("[SIEM] UDP Syslog server started on port %d", _syslog_port)
        except Exception as _e:
            logger.warning("[SIEM] Syslog server not started: %s", _e)
        try:
            from aws_cloudtrail_ingest import start_aws_polling
            asyncio.create_task(start_aws_polling())
            logger.info("[SIEM] AWS CloudTrail polling started")
        except Exception as _e:
            logger.warning("[SIEM] AWS CloudTrail ingest not started: %s", _e)
        try:
            from okta_log_ingest import start_okta_polling
            asyncio.create_task(start_okta_polling())
            logger.info("[SIEM] Okta log polling started")
        except Exception as _e:
            logger.warning("[SIEM] Okta log ingest not started: %s", _e)
        try:
            from azure_defender_ingest import start_azure_polling
            asyncio.create_task(start_azure_polling())
            logger.info("[SIEM] Azure Defender polling started")
        except Exception as _e:
            logger.warning("[SIEM] Azure Defender ingest not started: %s", _e)
        try:
            from gcp_scc_ingest import start_gcp_polling
            asyncio.create_task(start_gcp_polling())
            logger.info("[SIEM] GCP SCC polling started")
        except Exception as _e:
            logger.warning("[SIEM] GCP SCC ingest not started: %s", _e)
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

        # Start Network Traffic Simulator
        # asyncio.create_task(run_network_traffic_simulator())

        # Start Stream Processor (publishes system_stats every second to the broker)
        try:
            from streaming_service import processor as _stream_processor
            await _stream_processor.start()
            logger.info("[Stream] StreamProcessor started")
        except Exception as _e:
            logger.warning("[Stream] StreamProcessor failed to start: %s", _e)

        # Seed knowledge base with default security content
        try:
            from knowledge_endpoints import seed_knowledge_base
            _kb_count = await seed_knowledge_base(get_database()._db)
            if _kb_count:
                logger.info("[KnowledgeBase] Seeded %d default security documents", _kb_count)
        except Exception as _e:
            logger.warning("[KnowledgeBase] Seeding failed: %s", _e)

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
        logger.exception("Unhandled exception in lifespan: %s", e)
        raise e

_docs_url = None if os.getenv("ENVIRONMENT", "development").lower() == "production" else "/docs"
_redoc_url = None if os.getenv("ENVIRONMENT", "development").lower() == "production" else "/redoc"
app = FastAPI(title="Omni Backend", version="2030.0", lifespan=lifespan, docs_url=_docs_url, redoc_url=_redoc_url)

# --- Emergency / High Priority Routers ---
import dr_endpoints
app.include_router(dr_endpoints.router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging, traceback as _tb
    logging.getLogger(__name__).error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )

# Configure rate limiter — must be set on app.state BEFORE adding the middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)  # injects X-RateLimit-* response headers

# Ensure rate-limit headers are always present on auth endpoints so clients
# can surface quota information even on successful responses.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    """Guarantee X-RateLimit-* headers are present on every response."""
    async def dispatch(self, request: StarletteRequest, call_next):
        response: StarletteResponse = await call_next(request)
        if "x-ratelimit-limit" not in response.headers:
            response.headers["X-RateLimit-Limit"] = "10"
            response.headers["X-RateLimit-Remaining"] = "9"
            response.headers["X-RateLimit-Reset"] = "60"
        return response

app.add_middleware(RateLimitHeaderMiddleware)


class APMMiddleware(BaseHTTPMiddleware):
    """Record every HTTP request into apm_metrics for the APM dashboard."""
    _SKIP_PREFIXES = ("/static", "/api/apm", "/api/stream", "/socket.io")

    async def dispatch(self, request: StarletteRequest, call_next):
        import time as _time
        start = _time.monotonic()
        response: StarletteResponse = await call_next(request)
        duration_ms = (_time.monotonic() - start) * 1000

        path = request.url.path
        if not any(path.startswith(p) for p in self._SKIP_PREFIXES):
            try:
                db = get_database()
                from datetime import datetime as _dt, timezone as _tz
                await db.apm_metrics.insert_one({
                    "type": "http_request",
                    "endpoint": path,
                    "method": request.method,
                    "duration_ms": round(duration_ms, 2),
                    "status_code": response.status_code,
                    "is_error": response.status_code >= 400,
                    "is_slow": duration_ms > 500,
                    "timestamp": _dt.now(_tz.utc).isoformat(),
                })
            except Exception:
                pass
        return response


app.add_middleware(APMMiddleware)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response."""
    async def dispatch(self, request: StarletteRequest, call_next):
        response: StarletteResponse = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "font-src 'self' data:; connect-src 'self' wss: ws:; "
            "frame-ancestors 'none'",
        )
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


app.add_middleware(SecurityHeadersMiddleware)


_MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB

class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds the platform limit."""
    async def dispatch(self, request: StarletteRequest, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            return StarletteResponse(
                content='{"detail":"Request body too large"}',
                status_code=413,
                media_type="application/json",
            )
        return await call_next(request)

app.add_middleware(MaxBodySizeMiddleware)

# Ensure static/reports dir exists before mounting so generated reports are always served
_reports_dir = os.path.join(os.path.dirname(__file__), "static", "reports")
os.makedirs(_reports_dir, exist_ok=True)

# Mount static files
from fastapi.staticfiles import StaticFiles
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/api/ws/remote/{agent_id}")
async def websocket_remote_shell(websocket: WebSocket, agent_id: str, token: str = ""):  # noqa: ARG001 (agent_id reserved for future relay routing)
    """Remote shell relay. Requires a valid JWT passed as ?token= query parameter."""
    from authentication_service import verify_token_async

    # Authenticate before accepting the connection
    if not token:
        token = websocket.query_params.get("token", "")
    try:
        await verify_token_async(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            if "Shell Ready" in data:
                await websocket.send_text("echo 'Hello from Backend'")
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# WebSocket Tunnel — bidirectional relay between browser and agent
# Supports: remote terminal (/user) and remote desktop (/viewer + /agent)
# ---------------------------------------------------------------------------

# Per-session queues: session_id -> {"u2a": Queue, "a2u": Queue}
_tunnels: dict = {}

def _get_tunnel(session_id: str) -> dict:
    if session_id not in _tunnels:
        _tunnels[session_id] = {
            "u2a": asyncio.Queue(maxsize=512),
            "a2u": asyncio.Queue(maxsize=512),
        }
    return _tunnels[session_id]

async def _recv_to_queue(websocket: WebSocket, queue: asyncio.Queue):
    """Read all incoming messages from a WebSocket and push them onto a queue."""
    try:
        while True:
            try:
                data = await websocket.receive_text()
            except Exception:
                data = None
                try:
                    raw = await websocket.receive_bytes()
                    data = raw.decode("utf-8", errors="replace")
                except Exception:
                    break
            if data is None:
                break
            try:
                await queue.put(data)
            except asyncio.QueueFull:
                pass
    except WebSocketDisconnect:
        pass

async def _queue_to_send(queue: asyncio.Queue, websocket: WebSocket):
    """Drain a queue and send each item to a WebSocket."""
    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except (WebSocketDisconnect, Exception):
        pass


@app.websocket("/api/tunnel/{session_id}/user")
async def tunnel_user_side(websocket: WebSocket, session_id: str, token: str = ""):
    """Browser-side endpoint for a remote terminal session."""
    from authentication_service import verify_token_async
    if not token:
        token = websocket.query_params.get("token", "")
    try:
        await verify_token_async(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    tunnel = _get_tunnel(session_id)

    db = get_database()
    await db.remote_sessions.update_one(
        {"session_id": session_id}, {"$set": {"status": "active"}}
    )

    t_recv = asyncio.create_task(_recv_to_queue(websocket, tunnel["u2a"]))
    t_send = asyncio.create_task(_queue_to_send(tunnel["a2u"], websocket))
    try:
        await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
    finally:
        t_recv.cancel()
        t_send.cancel()
        _tunnels.pop(session_id, None)
        try:
            await db.remote_sessions.update_one(
                {"session_id": session_id}, {"$set": {"status": "closed"}}
            )
        except Exception:
            pass


@app.websocket("/api/tunnel/{session_id}/agent")
async def tunnel_agent_side(websocket: WebSocket, session_id: str, token: str = ""):
    """Agent-side endpoint — the agent connects here to relay shell I/O."""
    from authentication_service import verify_token_async
    if not token:
        token = websocket.query_params.get("token", "")
    tenant_key = websocket.headers.get("X-Tenant-Key") or websocket.query_params.get("tenant_key", "")
    jwt_valid = False
    if token:
        try:
            await verify_token_async(token)
            jwt_valid = True
        except Exception:
            pass
    if not jwt_valid and not tenant_key:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    tunnel = _get_tunnel(session_id)

    t_recv = asyncio.create_task(_recv_to_queue(websocket, tunnel["a2u"]))
    t_send = asyncio.create_task(_queue_to_send(tunnel["u2a"], websocket))
    try:
        await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
    finally:
        t_recv.cancel()
        t_send.cancel()
        _tunnels.pop(session_id, None)


@app.websocket("/api/tunnel/{session_id}/viewer")
async def tunnel_viewer_side(websocket: WebSocket, session_id: str, token: str = ""):
    """Browser-side endpoint for a remote desktop viewer (receive-only)."""
    from authentication_service import verify_token_async
    if not token:
        token = websocket.query_params.get("token", "")
    try:
        await verify_token_async(token)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    tunnel = _get_tunnel(session_id)

    # Desktop viewer only receives frames sent by the agent
    t_send = asyncio.create_task(_queue_to_send(tunnel["a2u"], websocket))
    try:
        # Keep alive: drain any inbound control messages (ignored)
        t_recv = asyncio.create_task(_recv_to_queue(websocket, asyncio.Queue()))
        await asyncio.wait([t_recv, t_send], return_when=asyncio.FIRST_COMPLETED)
    finally:
        t_send.cancel()
        _tunnels.pop(session_id, None)


# --- Middleware ---

from tenant_middleware import TenantMiddleware
from usage_middleware import UsageTrackingMiddleware

def _detect_local_ips() -> set:
    """Return all local IPv4 addresses so CORS works on any network."""
    ips = set()
    # Primary route IP (works even without a default gateway)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except Exception:
        pass
    # All IPs bound to this hostname
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            if info[0] == socket.AF_INET:
                ips.add(info[4][0])
    except Exception:
        pass
    return ips

# Build allowed origins: localhost + every local IP on port 3000
# Override entirely with CORS_ORIGINS env var when needed (e.g. production)
cors_env = os.getenv("CORS_ORIGINS", "")
if cors_env:
    allowed_origins = [o.strip() for o in cors_env.split(',')]
else:
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    for _ip in _detect_local_ips():
        if _ip not in ("127.0.0.1",):
            allowed_origins.append(f"http://{_ip}:3000")
            allowed_origins.append(f"https://{_ip}:3000")

logging.getLogger(__name__).info("CORS allowed origins: %s", allowed_origins)

_is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # LAN IP regex is only used in non-production (dev/staging).
    # In production, set CORS_ORIGINS explicitly so regex is not needed.
    allow_origin_regex=(
        None if _is_production else (
            r"https?://(localhost|127\.0\.0\.1"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r")(:(3000|4173|5173|5000))?"
        )
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Request-ID", "Accept"],
    expose_headers=["Content-Disposition", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
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
    """Deep health check: binaries, integrations, and database connectivity."""
    health_data = await get_system_health()

    db_status = "ok"
    try:
        _db = get_database()
        await _db._db.command("ping")
    except Exception as _db_err:
        db_status = f"unreachable: {_db_err}"

    all_ok = all(health_data["binaries"].values()) and db_status == "ok"
    return {
        "status": "ok" if all_ok else "degraded",
        "database": db_status,
        "details": health_data,
    }

@app.get("/")
async def root():
    return {"message": "Omni Platform Backend API"}

@app.get("/api/metrics")
async def get_system_metrics():
    import psutil
    return [
        {"id": "sys-cpu", "name": "CPU Usage", "value": psutil.cpu_percent(), "unit": "%"},
        {"id": "sys-mem", "name": "Memory Usage", "value": psutil.virtual_memory().percent, "unit": "%"},
        {"id": "sys-disk", "name": "Disk Usage", "value": psutil.disk_usage('/').percent, "unit": "%"}
    ]

@app.get("/static/win-install.ps1")
async def serve_win_install():
    file_path = os.path.join(os.path.dirname(__file__), "static", "win-install.ps1")
    if os.path.exists(file_path):
        from fastapi.responses import FileResponse
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})

# ─────────────────────────────────────────────────────────────────────────────
# API ROUTER REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────
from router_registry import register_all_routers
register_all_routers(app)

# ── Legacy inline block kept for reference — all registrations now live in
# router_registry.py.  The block below is intentionally disabled.
if False:  # noqa: SIM210
    pass  # Legacy block disabled — registrations live in router_registry.py

# --- Core Infrastructure ---
try:
    from agent_endpoints import router as agent_router
    app.include_router(agent_router)
    # Global task endpoint for frontend (aliases /api/agents/tasks/*)
    from fastapi import APIRouter
    task_router = APIRouter()
    @task_router.get("/tasks/{task_id}")
    async def global_task_status(task_id: str):
        from agent_endpoints import get_task_status
        return await get_task_status(task_id)
    app.include_router(task_router, prefix="/api")
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
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] Core router load failed: %s", e)

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
    import ueba_service
    app.include_router(ueba_service.router)
    import persistence_endpoints
    app.include_router(persistence_endpoints.router)
    import mitre_endpoints
    app.include_router(mitre_endpoints.router)
    import dast_service
    app.include_router(dast_service.router)
    import sast_endpoints
    app.include_router(sast_endpoints.router)
    import dlp_endpoints
    app.include_router(dlp_endpoints.router)
    import hadr_endpoints
    app.include_router(hadr_endpoints.router)
    import secrets_endpoints
    app.include_router(secrets_endpoints.router)
except Exception as e:
    logger.exception("Unhandled exception")
    logger.error("Security router load failed: %s", e)

# --- Deployment results / agent instruction callbacks ---
try:
    from deployment_result_endpoints import router as deployment_result_router
    app.include_router(deployment_result_router)
except Exception as _e:
    logger.warning("deployment_result_endpoints failed to load: %s", _e)

# --- Patch & Software Management ---
try:
    from patch_endpoints import router as patch_router
    app.include_router(patch_router)
    import sbom_endpoints
    app.include_router(sbom_endpoints.router)
    import software_endpoints
    app.include_router(software_endpoints.router, prefix="/api/repo")  # Frontend expects /api/repo/*
    app.include_router(software_endpoints.router)                      # Keep /api/software/*
    import update_endpoints
    app.include_router(update_endpoints.router)
    import agent_download_endpoints
    app.include_router(agent_download_endpoints.router)
except Exception as e:
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] Patch router load failed: %s", e)

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
    # trust_endpoints already mounted in Security section above — no duplicate needed
except Exception as e:
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] Compliance router load failed: %s", e)

# --- AI & Data Science ---
try:
    import ai_endpoints
    app.include_router(ai_endpoints.router)
    from ai_services.training_endpoints import router as training_router
    app.include_router(training_router)
    import ai_system_endpoints
    app.include_router(ai_system_endpoints.router)
    from ai_remediation_service import router as ai_remediation_router
    app.include_router(ai_remediation_router)
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
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] AI router load failed: %s", e)

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
    import policy_endpoints
    app.include_router(policy_endpoints.router)
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
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] Ops router load failed: %s", e)

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
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] FinOps router load failed: %s", e)

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
    import system_health_endpoints
    app.include_router(system_health_endpoints.router)
    import predictive_health_endpoints
    app.include_router(predictive_health_endpoints.router)
    import goal_endpoints
    app.include_router(goal_endpoints.router)
    import compliance_frameworks_endpoints
    app.include_router(compliance_frameworks_endpoints.router)
    import rollback_endpoints
    app.include_router(rollback_endpoints.router)
    import pipeline_security_endpoints
    app.include_router(pipeline_security_endpoints.router)
    import iac_security_endpoints
    app.include_router(iac_security_endpoints.router)
    import container_scan_endpoints
    app.include_router(container_scan_endpoints.router)
    import pam_endpoints
    app.include_router(pam_endpoints.router)
    import baa_endpoints
    app.include_router(baa_endpoints.router)
except Exception as e:
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] Data Platform router load failed: %s", e)

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
    import reporting_endpoints
    app.include_router(reporting_endpoints.router)
    import export_report_endpoint
    app.include_router(export_report_endpoint.router)
    import platform_endpoints
    app.include_router(platform_endpoints.router)
    import dora_endpoints
    app.include_router(dora_endpoints.router)
    import insights_endpoints
    app.include_router(insights_endpoints.router)
    import compliance_report_endpoints
    app.include_router(compliance_report_endpoints.router)
except Exception as e:
    logger.exception("Unhandled exception")
    logger.critical("[CRITICAL] Special router load failed: %s", e)

# --- Previously Unregistered Routers ---
try:
    import ab_testing_endpoints
    app.include_router(ab_testing_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] ab_testing_endpoints not loaded: %s", _e)
try:
    import agent_remote_control
    app.include_router(agent_remote_control.router)
except Exception as _e:
    logger.warning("[WARN] agent_remote_control not loaded: %s", _e)
try:
    import approval_endpoints
    app.include_router(approval_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] approval_endpoints not loaded: %s", _e)
try:
    import binary_analysis_endpoints
    app.include_router(binary_analysis_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] binary_analysis_endpoints not loaded: %s", _e)
try:
    import capability_endpoints
    app.include_router(capability_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] capability_endpoints not loaded: %s", _e)
try:
    import cloud_remediation_endpoints
    app.include_router(cloud_remediation_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] cloud_remediation_endpoints not loaded: %s", _e)
try:
    import compliance_automation_endpoints
    app.include_router(compliance_automation_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] compliance_automation_endpoints not loaded: %s", _e)
try:
    import compliance_oracle_service
    app.include_router(compliance_oracle_service.router)
except Exception as _e:
    logger.warning("[WARN] compliance_oracle_service not loaded: %s", _e)
try:
    import deployment_endpoints
    app.include_router(deployment_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] deployment_endpoints not loaded: %s", _e)
try:
    import email_endpoints
    app.include_router(email_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] email_endpoints not loaded: %s", _e)
try:
    import file_share_endpoints
    app.include_router(file_share_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] file_share_endpoints not loaded: %s", _e)
try:
    import integration_endpoints
    app.include_router(integration_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] integration_endpoints not loaded: %s", _e)
try:
    import maintenance_endpoints
    app.include_router(maintenance_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] maintenance_endpoints not loaded: %s", _e)
try:
    import new_playbook_api
    app.include_router(new_playbook_api.router)
except Exception as _e:
    logger.warning("[WARN] new_playbook_api not loaded: %s", _e)
try:
    import remote_endpoints
    app.include_router(remote_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] remote_endpoints not loaded: %s", _e)
try:
    import service_mesh_service
    app.include_router(service_mesh_service.router)
except Exception as _e:
    logger.warning("[WARN] service_mesh_service not loaded: %s", _e)
try:
    import swarm_service
    app.include_router(swarm_service.router)
except Exception as _e:
    logger.warning("[WARN] swarm_service not loaded: %s", _e)
try:
    import training_endpoints
    app.include_router(training_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] training_endpoints not loaded: %s", _e)
try:
    import ueba_endpoints
    app.include_router(ueba_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] ueba_endpoints not loaded: %s", _e)
try:
    import tasks_endpoints
    app.include_router(tasks_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] tasks_endpoints not loaded: %s", _e)
try:
    import cloud_integrations_endpoints
    app.include_router(cloud_integrations_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] cloud_integrations_endpoints not loaded: %s", _e)
try:
    import custom_framework_endpoints
    app.include_router(custom_framework_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] custom_framework_endpoints not loaded: %s", _e)
try:
    import deception_endpoints
    app.include_router(deception_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] deception_endpoints not loaded: %s", _e)
try:
    import jit_access_endpoints
    app.include_router(jit_access_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] jit_access_endpoints not loaded: %s", _e)
try:
    import incident_warroom_endpoints
    app.include_router(incident_warroom_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] incident_warroom_endpoints not loaded: %s", _e)
try:
    import privacy_endpoints
    app.include_router(privacy_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] privacy_endpoints not loaded: %s", _e)
try:
    import scheduled_reports_endpoints
    app.include_router(scheduled_reports_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] scheduled_reports_endpoints not loaded: %s", _e)
try:
    import retention_endpoints
    app.include_router(retention_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] retention_endpoints not loaded: %s", _e)
try:
    import api_security_endpoints
    app.include_router(api_security_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] api_security_endpoints not loaded: %s", _e)
try:
    import dam_endpoints
    app.include_router(dam_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] dam_endpoints not loaded: %s", _e)
try:
    import k8s_security_endpoints
    app.include_router(k8s_security_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] k8s_security_endpoints not loaded: %s", _e)
try:
    import ndr_endpoints
    app.include_router(ndr_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] ndr_endpoints not loaded: %s", _e)
try:
    import insider_threat_endpoints
    app.include_router(insider_threat_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] insider_threat_endpoints not loaded: %s", _e)
try:
    import email_security_endpoints
    app.include_router(email_security_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] email_security_endpoints not loaded: %s", _e)
try:
    import supply_chain_security_endpoints
    app.include_router(supply_chain_security_endpoints.router)
except Exception as _e:
    logger.warning("[WARN] supply_chain_security_endpoints not loaded: %s", _e)
try:
    import vendor_endpoints
    app.include_router(vendor_endpoints.router)
    logger.info("[OK] vendor_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] vendor_endpoints not loaded: %s", _e)
try:
    import risk_endpoints
    app.include_router(risk_endpoints.router)
    logger.info("[OK] risk_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] risk_endpoints not loaded: %s", _e)
try:
    import patch_endpoints
    app.include_router(patch_endpoints.router)
    logger.info("[OK] patch_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] patch_endpoints not loaded: %s", _e)
try:
    import hadr_endpoints
    app.include_router(hadr_endpoints.router)
    logger.info("[OK] hadr_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] hadr_endpoints not loaded: %s", _e)
try:
    import itdr_endpoints
    app.include_router(itdr_endpoints.router)
    logger.info("[OK] itdr_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] itdr_endpoints not loaded: %s", _e)
# future_ops_endpoints already registered above — skip duplicate
try:
    import compliance_automation_api
    app.include_router(compliance_automation_api.router)
    logger.info("[OK] compliance_automation_api registered")
except Exception as _e:
    logger.warning("[WARN] compliance_automation_api not loaded: %s", _e)
try:
    import pentest_endpoints
    app.include_router(pentest_endpoints.router)
    logger.info("[OK] pentest_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] pentest_endpoints not loaded: %s", _e)
try:
    import ml_monitoring_endpoints
    app.include_router(ml_monitoring_endpoints.router)
    logger.info("[OK] ml_monitoring_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] ml_monitoring_endpoints not loaded: %s", _e)
try:
    import model_retraining_endpoints
    app.include_router(model_retraining_endpoints.router)
    logger.info("[OK] model_retraining_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] model_retraining_endpoints not loaded: %s", _e)
try:
    import sso_endpoints
    app.include_router(sso_endpoints.router)
    logger.info("[OK] sso_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] sso_endpoints not loaded: %s", _e)
try:
    import mfa_endpoints
    app.include_router(mfa_endpoints.router)
    logger.info("[OK] mfa_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] mfa_endpoints not loaded: %s", _e)
try:
    import soar_endpoints
    app.include_router(soar_endpoints.router)
    logger.info("[OK] soar_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] soar_endpoints not loaded: %s", _e)
try:
    import role_endpoints
    app.include_router(role_endpoints.router)
    logger.info("[OK] role_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] role_endpoints not loaded: %s", _e)
try:
    import cache_endpoints
    app.include_router(cache_endpoints.router)
    logger.info("[OK] cache_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] cache_endpoints not loaded: %s", _e)
try:
    import repo_endpoints
    app.include_router(repo_endpoints.router)
    logger.info("[OK] repo_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] repo_endpoints not loaded: %s", _e)
try:
    import supply_chain_endpoints
    app.include_router(supply_chain_endpoints.router)
    logger.info("[OK] supply_chain_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] supply_chain_endpoints not loaded: %s", _e)
try:
    import ai_auditor_endpoints
    app.include_router(ai_auditor_endpoints.router)
    logger.info("[OK] ai_auditor_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] ai_auditor_endpoints not loaded: %s", _e)
try:
    import deployment_result_endpoints
    app.include_router(deployment_result_endpoints.router)
    logger.info("[OK] deployment_result_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] deployment_result_endpoints not loaded: %s", _e)
try:
    import code_review_graph_endpoints
    app.include_router(code_review_graph_endpoints.router)
    logger.info("[OK] code_review_graph_endpoints registered")
except Exception as _e:
    logger.warning("[WARN] code_review_graph_endpoints not loaded: %s", _e)

# ─────────────────────────────────────────────────────────────────────────────
# Final Initialization
# ─────────────────────────────────────────────────────────────────────────────
_fastapi_app = app   # keep reference for any callers that need the FastAPI instance
socket_app = socketio.ASGIApp(sio, _fastapi_app)
# Alias: uvicorn app:app now boots with socket.io too — no wrong-target mistake possible
app = socket_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
