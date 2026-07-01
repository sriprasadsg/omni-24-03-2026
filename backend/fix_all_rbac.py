"""
Fix RBAC decorator usage across all endpoint files.
The decorator should be used in Depends(), not as a separate @decorator.
"""
import re
import os

endpoint_files = [
    "vuln_endpoints.py",
    "threat_endpoints.py",
    "notification_endpoints.py",
    "maintenance_endpoints.py",
    "kpi_endpoints.py",
    "deployment_endpoints.py",
    "audit_endpoints.py",
    "ai_endpoints.py",
]

def fix_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if this is an RBAC decorator
        if '@rbac_service.has_permission' in line or '@rbac_service.require_role' in line:
            # Extract the permission
            match = re.search(r'@rbac_service\.(has_permission|require_role)\(([^)]+)\)', line)
            if match:
                method = match.group(1)
                permission = match.group(2)
                
                # Skip this decorator line
                i += 1
                
                # Find the async def line
                while i < len(lines) and 'async def' not in lines[i]:
                    fixed_lines.append(lines[i])
                    i += 1
                
                if i < len(lines):
                    # This is the async def line
                    func_line = lines[i]
                    i += 1
                    
                    # Find the parameters
                    params = []
                    param_line = ""
                    paren_count = func_line.count('(') - func_line.count(')')
                    param_line += func_line
                    
                    while paren_count > 0 and i < len(lines):
                        param_line += lines[i]
                        paren_count += lines[i].count('(') - lines[i].count(')')
                        i += 1
                    
                    # Check if current_user is already in params with Depends(get_current_user)
                    if 'current_user' in param_line and 'Depends(get_current_user)' in param_line:
                        # Replace Depends(get_current_user) with the RBAC dependency
                        param_line = param_line.replace(
                            'Depends(get_current_user)',
                            f'Depends(rbac_service.{method}({permission}))'
                        )
                    
                    # Write the modified function
                    fixed_lines.append(param_line)
                    continue
        
        fixed_lines.append(line)
        i += 1
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print(f"✅ Fixed {filename}")

# Fix all files
for filename in endpoint_files:
    if os.path.exists(filename):
        try:
            fix_file(filename)
        except Exception as e:
            print(f"❌ Error fixing {filename}: {e}")
    else:
        print(f"⚠️  {filename} not found")

print("\n✅ All endpoint files fixed!")
