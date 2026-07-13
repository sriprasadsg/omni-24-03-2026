
import os
from database import connect_to_mongo, close_mongo_connection, get_database
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
from contextlib import asynccontextmanager
from logging_config import configure_logging

logger = logging.getLogger(__name__)
from tenant_context import set_tenant_id
from health_service import get_system_health

from rate_limiter import limiter

from websocket_manager import sio
import socketio

from app_startup import _validate_startup_config, seed_database, run_startup_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    try:
        _validate_startup_config()
        await connect_to_mongo()

        set_tenant_id("platform-admin")
        await seed_database()
        await run_startup_services()

        yield

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

from error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


from app_middleware import register_middleware
register_middleware(app, limiter)

# dr_endpoints registered AFTER middleware so rate-limiting and security headers apply
import dr_endpoints
app.include_router(dr_endpoints.router)

from tunnel_endpoints import register_tunnel_routes
register_tunnel_routes(app)

_reports_dir = os.path.join(os.path.dirname(__file__), "static", "reports")
os.makedirs(_reports_dir, exist_ok=True)
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt():
    """Serve RFC 9116 security disclosure policy."""
    from fastapi.responses import FileResponse
    _path = os.path.join(os.path.dirname(__file__), "static", ".well-known", "security.txt")
    return FileResponse(_path, media_type="text/plain")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "backend-fastapi", "edition": "2030"}


@app.get("/api/health")
async def api_health():
    return {"status": "ok", "service": "backend-fastapi", "edition": "2030"}


@app.get("/api/demo-mode")
async def demo_mode_status():
    """Return whether the backend is running in demo/mock-DB mode."""
    from database import is_demo_mode
    return {"demo_mode": is_demo_mode()}


@app.get("/api/health/extended")
async def extended_health(
    _user=Depends(__import__("authentication_service").get_current_user),
):
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
async def get_system_metrics(
    _user=Depends(__import__("authentication_service").get_current_user),
):
    import psutil
    return [
        {"id": "sys-cpu", "name": "CPU Usage", "value": psutil.cpu_percent(), "unit": "%"},
        {"id": "sys-mem", "name": "Memory Usage", "value": psutil.virtual_memory().percent, "unit": "%"},
        {"id": "sys-disk", "name": "Disk Usage", "value": psutil.disk_usage("/").percent, "unit": "%"},
    ]


@app.get("/static/win-install.ps1")
async def serve_win_install():
    file_path = os.path.join(os.path.dirname(__file__), "static", "win-install.ps1")
    if os.path.exists(file_path):
        from fastapi.responses import FileResponse
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "File not found"})


from router_registry import register_all_routers
register_all_routers(app)

_fastapi_app = app
socket_app = socketio.ASGIApp(sio, _fastapi_app)
app = socket_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

from graphql_endpoints import router as graphql_router
app.include_router(graphql_router)
