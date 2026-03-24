import sys
import logging

logging.basicConfig(level=logging.DEBUG)

modules_to_test = [
    "fastapi",
    "fastapi.middleware.cors",
    "fastapi.staticfiles",
    "database",
    "auth_utils",
    "email_service",
    "agentic_api",
    "models",
    "threat_endpoints",
    "audit_endpoints",
    "new_playbook_api",
    "vuln_endpoints",
    "job_service",
    "scapy.all",
    "google.generativeai",
    "motor.motor_asyncio",
    "pydantic",
    "bcrypt",
    "apscheduler.schedulers.asyncio",
    "scheduler",
    "compliance_endpoints",
    "software_endpoints",
    "update_endpoints",
    "agent_instruction_endpoints",
    "deployment_endpoints",
    "patch_endpoints",
    "reporting_endpoints",
    "security_endpoints",
    "authentication_endpoints",
    "automation_endpoints",
    "audit_endpoints"
]

for module in modules_to_test:
    print(f"Testing import: {module}...", flush=True)
    try:
        __import__(module)
        print(f"SUCCESS: {module}", flush=True)
    except Exception as e:
        print(f"FAILED: {module} - {e}", flush=True)
    except BaseException as e:
        print(f"CRITICAL FAILURE during {module}: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)

print("All imports tested successfully.")
