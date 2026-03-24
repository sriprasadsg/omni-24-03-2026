from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from database import get_database
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger("usage_middleware")

class UsageTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Continue with request
        response = await call_next(request)
        
        # After response, log usage if it's an API call
        if request.url.path.startswith("/api/"):
            try:
                # We do this after the response to avoid blocking the main request path
                # Ideally, this would be a background task or emitted to a queue
                
                # Try to get tenant_id from context
                from tenant_context import get_tenant_id
                tenant_id = get_tenant_id()

                if tenant_id:
                    await self.log_usage(request, response, tenant_id)
            except Exception as e:
                logger.error(f"Error logging usage: {e}")
        
        return response

    async def log_usage(self, request, response, tenant_id: str):
        db = get_database()
        if not db:
            return

        service_id = self.identify_service(request.url.path)
        if not service_id:
            return

        usage_record = {
            "tenantId": tenant_id,
            "serviceId": service_id,
            "path": request.url.path,
            "method": request.method,
            "statusCode": response.status_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "amount": 1, # Default base unit
            "unit": "request"
        }

        # Special handling for potentially large usage (e.g., data transfer)
        content_length = response.headers.get("content-length")
        if content_length:
            usage_record["bytes"] = int(content_length)
            # If it's a large download, maybe log as bandwidth
            if "/download" in request.url.path:
                usage_record["amount"] = int(content_length) / (1024 * 1024) # MB
                usage_record["unit"] = "MB_transfer"

        await db.usage_records.insert_one(usage_record)

    def identify_service(self, path: str) -> str:
        if "/api/ai" in path or "/api/llm" in path:
            return "ai_services"
        if "/api/agents" in path:
            return "agent_management"
        if "/api/security" in path or "/api/vuln" in path:
            return "security_operations"
        if "/api/compliance" in path:
            return "compliance_monitoring"
        if "/api/finops" in path:
            return "finops_analytics"
        return "general_api"
