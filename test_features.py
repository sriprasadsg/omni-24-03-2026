#!/usr/bin/env python3
"""
Comprehensive feature testing script for the Enterprise Omni-Agent AI Platform.
Tests authentication, permissions, and agent installation features.
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5000"
session = requests.Session()

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def test_health():
    """Test if backend is healthy"""
    print_section("1. Backend Health Check")
    try:
        response = session.get(f"{BASE_URL}/health")
        print(f"✓ Status: {response.status_code}")
        print(f"✓ Response: {response.json()}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_signup():
    """Test user signup"""
    print_section("2. User Signup")
    signup_data = {
        "companyName": "Test Corporation",
        "name": "Test Admin",
        "email": "testadmin@testcorp.com",
        "password": "TestPass123!"
    }
    
    try:
        response = session.post(f"{BASE_URL}/api/auth/signup", json=signup_data)
        print(f"Status: {response.status_code}")
        
        if response.status_code in [200, 201]:
            data = response.json()
            print(f"✓ User created successfully")
            print(f"  User ID: {data.get('user', {}).get('id', 'N/A')}")
            print(f"  Email: {data.get('user', {}).get('email', 'N/A')}")
            print(f"  Role: {data.get('user', {}).get('role', 'N/A')}")
            print(f"  Token: {data.get('token', 'N/A')[:50]}...")
            return data
        else:
            print(f"✗ Signup failed: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def test_login(email, password):
    """Test user login"""
    print_section("3. User Login")
    login_data = {
        "email": email,
        "password": password
    }
    
    try:
        response = session.post(f"{BASE_URL}/api/auth/login", json=login_data)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Login successful")
            print(f"  User: {data.get('user', {}).get('name', 'N/A')}")
            print(f"  Role: {data.get('user', {}).get('role', 'N/A')}")
            print(f"  Tenant: {data.get('user', {}).get('tenantName', 'N/A')}")
            
            # Store token for subsequent requests
            token = data.get('token')
            if token:
                session.headers.update({'Authorization': f'Bearer {token}'})
                print(f"  Token saved for subsequent requests")
            
            return data
        else:
            print(f"✗ Login failed: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def test_tenant_info(user_data):
    """Test getting tenant information"""
    print_section("4. Tenant Information")
    
    try:
        tenant_id = user_data.get('user', {}).get('tenantId')
        if not tenant_id:
            print("✗ No tenant ID found")
            return None
            
        response = session.get(f"{BASE_URL}/api/tenants/{tenant_id}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Tenant retrieved")
            print(f"  ID: {data.get('id', 'N/A')}")
            print(f"  Name: {data.get('name', 'N/A')}")
            print(f"  Subscription: {data.get('subscriptionTier', 'N/A')}")
            print(f"  Registration Key: {data.get('registrationKey', 'N/A')}")
            return data
        else:
            print(f"✗ Failed to get tenant: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def test_agents_list():
    """Test getting agents list"""
    print_section("5. Agents List")
    
    try:
        response = session.get(f"{BASE_URL}/api/agents")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            agents = response.json()
            print(f"✓ Retrieved {len(agents)} agents")
            
            if agents:
                for i, agent in enumerate(agents[:3], 1):  # Show first 3
                    print(f"\n  Agent {i}:")
                    print(f"    Name: {agent.get('name', 'N/A')}")
                    print(f"    Status: {agent.get('status', 'N/A')}")
                    print(f"    Platform: {agent.get('platform', 'N/A')}")
            else:
                print("  No agents registered yet")
            
            return agents
        else:
            print(f"✗ Failed to get agents: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def test_user_permissions(user_data):
    """Check user permissions"""
    print_section("6. User Permissions Check")
    
    try:
        role = user_data.get('user', {}).get('role')
        print(f"User Role: {role}")
        
        # Try to get role permissions from database
        response = session.get(f"{BASE_URL}/api/roles")
        
        if response.status_code == 200:
            roles = response.json()
            user_role = next((r for r in roles if r.get('name') == role), None)
            
            if user_role:
                permissions = user_role.get('permissions', [])
                print(f"\n✓ Role '{role}' has {len(permissions)} permissions")
                
                # Check critical permissions
                critical_perms = ['view:agents', 'remediate:agents', 'view:dashboard']
                print(f"\nCritical permissions:")
                for perm in critical_perms:
                    has_perm = perm in permissions
                    symbol = "✓" if has_perm else "✗"
                    print(f"  {symbol} {perm}")
                
                return permissions
            else:
                print(f"✗ Role '{role}' not found")
                return None
        else:
            print(f"Note: Could not fetch roles (status {response.status_code})")
            return None
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  ENTERPRISE OMNI-AGENT AI PLATFORM - FEATURE TESTING")
    print("="*60)
    print(f"  Test Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Test 1: Health Check
    if not test_health():
        print("\n✗ Backend is not healthy. Cannot proceed with tests.")
        return
    
    # Test 2: Signup
    signup_result = test_signup()
    if not signup_result:
        print("\n⚠ Signup failed or user already exists. Trying login...")
        login_result = test_login("testadmin@testcorp.com", "TestPass123!")
    else:
        login_result = signup_result
    
    if not login_result:
        print("\n✗ Could not authenticate. Cannot proceed with authenticated tests.")
        return
    
    # Test 3: Login (if signup worked, we already have token)
    if signup_result:
        print_section("3. User Login")
        print("✓ Already logged in from signup")
    
    # Test 4: Tenant Info
    tenant_info = test_tenant_info(login_result)
    
    # Test 5: Agents List
    agents = test_agents_list()
    
    # Test 6: Permissions
    permissions = test_user_permissions(login_result)
    
    # Summary
    print_section("TEST SUMMARY")
    print(f"✓ Backend: Running")
    print(f"✓ Authentication: {'Working' if login_result else 'Failed'}")
    print(f"✓ Tenant System: {'Working' if tenant_info else 'Failed'}")
    print(f"✓ Agent System: {'Working' if agents is not None else 'Failed'}")
    print(f"✓ Permissions: {'Working' if permissions else 'Failed'}")
    
    if tenant_info and tenant_info.get('registrationKey'):
        print(f"\n📝 AGENT INSTALLATION")
        print(f"   Registration Key: {tenant_info.get('registrationKey')}")
        print(f"   \n   Linux/macOS:")
        print(f"   curl -sSL http://localhost:5000/static/linux-install.sh | sudo bash -s -- --registration-key {tenant_info.get('registrationKey')}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
