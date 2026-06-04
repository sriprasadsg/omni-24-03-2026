
import sys
import traceback

print("Testing imports...")
try:
    print("Importing os, sys...")
    import sys
    print("Importing database...")
    print("Importing fastapi...")
    print("Importing other core libs...")
    print("Importing tenant_context...")
    print("Importing authentication_service...")
    print("Importing auth_utils...")
    print("Importing email_service...")
    print("Importing audit_service...")
    print("Importing security_service...")
    print("Importing deployment_service...")
    print("Importing authentication_endpoints...")
    print("Importing bi_analytics_service...")
    print("Importing jobs_endpoints...")
    print("Importing health_service...")
    print("Importing slowapi...")
    print("Importing network_traffic_simulator...")
    print("Importing websocket_manager...")
    print("All imports SUCCESSFUL")
except Exception as e:
    print(f"FAILED on import: {e}")
    traceback.print_exc()
    sys.exit(1)
except SystemExit as e:
    print(f"SystemExit caught: {e}")
    sys.exit(1)
