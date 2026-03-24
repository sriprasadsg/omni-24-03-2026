import sys
import os

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app import app

print("\n--- REGISTERED ROUTES ---")
for route in app.routes:
    # Handle different route types (APIRoute, Mount, etc.)
    path = getattr(route, 'path', 'N/A')
    name = getattr(route, 'name', 'N/A')
    methods = getattr(route, 'methods', 'N/A')
    print(f"Path: {path} | Name: {name} | Methods: {methods}")
