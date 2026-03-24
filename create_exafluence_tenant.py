"""
Create Exafluence tenant and user
This script creates the Exafluence tenant if it doesn't exist
"""
import requests
import json

# Backend API URL
API_URL = "http://localhost:5000"

# Exafluence company details
tenant_data = {
    "companyName": "Exafluence",
    "name": "Exafluence Admin",
    "email": "admin@exafluence.com",
    "password": "ExafluenceSecure123!"
}

def create_tenant():
    """Create Exafluence tenant via signup API"""
    print("Creating Exafluence tenant...")
    
    try:
        response = requests.post(
            f"{API_URL}/api/auth/signup",
            json=tenant_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ Exafluence tenant created successfully!")
                print(f"\nTenant ID: {result['tenant']['id']}")
                print(f"Tenant Name: {result['tenant']['name']}")
                print(f"Registration Key: {result['tenant']['registrationKey']}")
                print(f"\nUser Email: {result['user']['email']}")
                print(f"User Name: {result['user']['name']}")
                print(f"User Role: {result['user']['role']}")
                
                # Save tenant ID to file for agent configuration
                with open('exafluence_tenant_id.txt', 'w') as f:
                    f.write(result['tenant']['id'])
                print(f"\n📝 Tenant ID saved to: exafluence_tenant_id.txt")
                
                return result['tenant']['id']
            else:
                error = result.get('error', 'Unknown error')
                if 'already registered' in error.lower():
                    print(f"ℹ️  Exafluence tenant already exists: {error}")
                    print("\nTo get the tenant ID, you can:")
                    print("1. Login to the platform as admin@exafluence.com")
                    print("2. Go to Administration → Tenant Management")
                    print("3. View the tenant details")
                else:
                    print(f"❌ Error: {error}")
                return None
        else:
            print(f"❌ HTTP Error {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend API at", API_URL)
        print("Please ensure the backend is running:")
        print("  cd backend")
        print("  .\\venv\\Scripts\\activate")
        print("  python -m uvicorn app:app --reload --port 5000")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    tenant_id = create_tenant()
    
    if tenant_id:
        print("\n" + "="*60)
        print("NEXT STEPS:")
        print("="*60)
        print(f"1. Update agent/config.yaml with:")
        print(f'   tenant_id: "{tenant_id}"')
        print("\n2. Run the agent:")
        print("   cd agent")
        print("   python agent.py")
        print("\n3. Login to platform:")
        print(f"   Email: {tenant_data['email']}")
        print(f"   Password: {tenant_data['password']}")
        print("="*60)
