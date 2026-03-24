import re

# Read the file
with open('backend/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the authentication_endpoints router and add remote control after it
pattern = r'(from authentication_endpoints import router as auth_router\napp\.include_router\(auth_router\))'
replacement = r'\1\n\nfrom agent_remote_control import router as remote_control_router\napp.include_router(remote_control_router)'

content = re.sub(pattern, replacement, content)

# Write back
with open('backend/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully added remote control router to app.py")
