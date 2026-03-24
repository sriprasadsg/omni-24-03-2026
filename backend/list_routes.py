import sys
import os

backend_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_path)

from app import app

def list_filtered_routes():
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and "ai-governance" in route.path:
            routes.append(f"Path: {route.path}, Methods: {getattr(route, 'methods', 'N/A')}")
    
    with open("backend/routes_diag.txt", "w") as f:
        f.write("\n".join(routes))

if __name__ == "__main__":
    list_filtered_routes()
