import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))

modules = [
    "fastapi",
    "database",
    "auth_utils",
    "email_service",
    "agentic_api",
    "models",
    "threat_endpoints",
    "audit_endpoints",
    "job_service"
]

for mod in modules:
    print(f"Importing {mod}...")
    __import__(mod)
    print(f"{mod} OK")

print("All modules OK. Importing app...")
import app
print("App OK")
