import re

# Read the file
with open('App.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the handleSignup function and update it to store refresh_token
in_signup = False
for i, line in enumerate(lines):
    # Find handleSignup function
    if 'const handleSignup = async' in line:
        in_signup = True
    
    # Update setCurrentUser line in handleSignup to also store tokens
    if in_signup and 'setCurrentUser(data.user)' in line:
        # Add lines to store tokens before setCurrentUser
        lines[i] = '''        // Store authentication tokens\n        if (data.access_token) localStorage.setItem('token', data.access_token);\n        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);\n        \n''' + line
        in_signup = False

# Find the other login handler (around line 375-404)
in_login = False
for i, line in enumerate(lines):
    # Look for login function (pattern: data.success && data.user)
    if i > 370 and i < 410 and 'data.success && data.user' in line:
        in_login = True
        # Check if tokens are being set
        if i+1 < len(lines) and 'setCurrentUser' in lines[i+1]:
            # Insert token storage before setCurrentUser
            lines[i+1] = '''        // Store authentication tokens\n        if (data.access_token) localStorage.setItem('token', data.access_token);\n        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);\n        \n''' + lines[i+1]
            break

# Also update handleLogout to clear refresh_token
for i, line in enumerate(lines):
    if 'const handleLogout = () => {' in line:
        # Find the next line and add refresh_token clearing
        if i+1 < len(lines):
            lines[i+1] = lines[i+1].rstrip() + '\n    localStorage.removeItem(\'token\');\n    localStorage.removeItem(\'refresh_token\');\n'

# Write back
with open('App.tsx', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Successfully updated App.tsx login/signup/logout handlers")
