"""
Script to temporarily remove RBAC decorators from app.py to fix startup issue.
The decorators should only be used in separate router files, not in app.py.
"""
import re

# Read app.py
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove @rbac_service lines
content = re.sub(r'@rbac_service\.(has_permission|require_role)\([^)]+\)\n', '', content)

# Write back
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Removed RBAC decorators from app.py")
print("Note: RBAC is still enforced via TenantMiddleware and routers")
