
import sys
import traceback

print("Testing imports...")
try:
    print("Importing os, sys...")
    import os, sys
    print("Importing database...")
    from database import connect_to_mongo, close_mongo_connection, get_database
    print("Importing fastapi...")
    from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks, Query
    print("Importing other core libs...")
    from typing import Any, List, Dict, Optional
    import logging
    from datetime import datetime, timedelta, timezone
    import uuid
    import random
    from contextlib import asynccontextmanager
    print("Importing tenant_context...")
    from tenant_context import set_tenant_id, get_tenant_id
    print("Importing authentication_service...")
    from authentication_service import verify_token
    import jwt
    print("Importing auth_utils...")
    from auth_utils import hash_password, verify_password
    print("Importing email_service...")
    from email_service import email_service
    import re
    import asyncio
    print("Importing audit_service...")
    from audit_service import get_audit_service
    print("Importing security_service...")
    from security_service import get_security_service
    print("Importing deployment_service...")
    from deployment_service import get_deployment_service
    print("Importing authentication_endpoints...")
    import authentication_endpoints
    print("Importing bi_analytics_service...")
    from bi_analytics_service import get_bi_analytics_service
    print("Importing jobs_endpoints...")
    import jobs_endpoints
    print("Importing health_service...")
    from health_service import get_system_health
    print("Importing slowapi...")
    from slowapi import Limiter, _rate_limit_exceeded_handler
    print("Importing network_traffic_simulator...")
    from network_traffic_simulator import run_network_traffic_simulator
    print("Importing websocket_manager...")
    from websocket_manager import sio
    import socketio
    print("All imports SUCCESSFUL")
except Exception as e:
    print(f"FAILED on import: {e}")
    traceback.print_exc()
    sys.exit(1)
except SystemExit as e:
    print(f"SystemExit caught: {e}")
    sys.exit(1)
