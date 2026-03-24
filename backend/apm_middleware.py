"""
APM Middleware

FastAPI middleware for automatic performance monitoring of all requests.
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
from typing import Callable
import uuid

from apm_service import get_apm_service
from database import get_database


class APMMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically track request performance"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate trace ID
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id
        
        # Record start time
        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Record error
            status_code = 500
            raise
        finally:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Extract metadata
            endpoint = request.url.path
            method = request.method
            
            # Get tenant and user from request state (if available)
            tenant_id = getattr(request.state, "tenant_id", None)
            user_id = getattr(request.state, "user_id", None)
            
            # Record metrics (async, non-blocking)
            try:
                db = get_database()
                apm_service = get_apm_service(db)
                
                await apm_service.record_request(
                    endpoint=endpoint,
                    method=method,
                    duration_ms=duration_ms,
                    status_code=status_code,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    trace_id=trace_id
                )
            except Exception as e:
                # Don't fail the request if APM recording fails
                print(f"APM recording error: {e}")
        
        # Add trace ID to response headers
        response.headers["X-Trace-ID"] = trace_id
        
        return response
