import os, re

backend = r'd:\Downloads\enterprise-omni-agent-ai-platform\backend'
app_py = open(os.path.join(backend, 'app.py')).read()

endpoint_files = [f for f in os.listdir(backend) if f.endswith('_endpoints.py') or f.endswith('_service.py')]

print("=== Endpoint files NOT imported in app.py ===")
missing_with_router = []
for f in sorted(endpoint_files):
    mod = f.replace('.py', '')
    if mod not in app_py:
        path = os.path.join(backend, f)
        content = open(path).read()
        if 'APIRouter' in content:
            lines = content.split('\n')
            prefix_line = next((l for l in lines if 'prefix=' in l and 'APIRouter' in l), None)
            prefix = prefix_line.strip() if prefix_line else "no prefix"
            print(f"  MISSING: {f}  => {prefix}")
            missing_with_router.append(f)

print(f"\nTotal missing routers with APIRouter: {len(missing_with_router)}")
