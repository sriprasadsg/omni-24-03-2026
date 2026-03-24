#!/usr/bin/env python3
"""
Frontend Connectivity Diagnostic Script

Tests backend API endpoints to diagnose the "Backend connection lost" error
and verify Performance Metrics data availability.
"""

import requests
import json
from datetime import datetime

BACKEND_URL = "http://localhost:5000"
ASSET_ID = "asset-EILT0197"

def test_health_endpoint():
    """Test the /health endpoint that frontend uses for connection checks"""
    print("\n" + "="*60)
    print("1. Testing Health Endpoint")
    print("="*60)
    
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        print(f"✅ Status Code: {response.status_code}")
        print(f"✅ Response: {response.text}")
        return True
    except requests.exceptions.Timeout:
        print("❌ TIMEOUT: Health check timed out after 5 seconds")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ CONNECTION ERROR: Cannot connect to backend")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_api_health():
    """Test the /api/health endpoint"""
    print("\n" + "="*60)
    print("2. Testing API Health Endpoint")
    print("="*60)
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        print(f"✅ Status Code: {response.status_code}")
        data = response.json()
        print(f"✅ Response: {json.dumps(data, indent=2)}")
        return True
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_assets_endpoint():
    """Test the assets endpoint that provides metrics data"""
    print("\n" + "="*60)
    print("3. Testing Assets Endpoint")
    print("="*60)
    
    try:
        response = requests.get(f"{BACKEND_URL}/api/assets/{ASSET_ID}", timeout=5)
        print(f"✅ Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for currentMetrics
            if 'currentMetrics' in data:
                print("\n✅ currentMetrics FOUND:")
                metrics = data['currentMetrics']
                print(f"  CPU Usage: {metrics.get('cpuUsage')}%")
                print(f"  Memory Usage: {metrics.get('memoryUsage')}%")
                print(f"  Disk Usage: {metrics.get('diskUsage')}%")
                print(f"  Total Memory: {metrics.get('totalMemoryGB')} GB")
                print(f"  Available Memory: {metrics.get('availableMemoryGB')} GB")
                print(f"  Collected At: {metrics.get('collectedAt')}")
                
                # Check data freshness
                collected_at = metrics.get('collectedAt', '')
                if collected_at:
                    print(f"\n📊 Data Age: {collected_at}")
                    print("   (Check if this is recent)")
                
                return True
            else:
                print("\n❌ currentMetrics NOT FOUND in response")
                print(f"Available keys: {list(data.keys())}")
                return False
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_cors_headers():
    """Check CORS headers in response"""
    print("\n" + "="*60)
    print("4. Checking CORS Headers")
    print("="*60)
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/assets/{ASSET_ID}",
            headers={"Origin": "http://localhost:3000"},
            timeout=5
        )
        
        cors_headers = {
            k: v for k, v in response.headers.items() 
            if k.lower().startswith('access-control')
        }
        
        if cors_headers:
            print("✅ CORS Headers Found:")
            for header, value in cors_headers.items():
                print(f"  {header}: {value}")
            return True
        else:
            print("⚠️  No CORS headers found in response")
            print("   This may cause frontend connection issues")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    print("\n" + "🔍" * 30)
    print("  BACKEND CONNECTIVITY DIAGNOSTIC")
    print("🔍" * 30)
    print(f"\nBackend URL: {BACKEND_URL}")
    print(f"Asset ID: {ASSET_ID}")
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "Health Endpoint": test_health_endpoint(),
        "API Health": test_api_health(),
        "Assets/Metrics Data": test_assets_endpoint(),
        "CORS Configuration": test_cors_headers()
    }
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("\nBackend is responsive and serving metrics data correctly.")
        print("The frontend 'Backend connection lost' error may be caused by:")
        print("  1. Vite proxy configuration issues")
        print("  2. Frontend timeout settings too aggressive")
        print("  3. WebSocket connection problems (if used)")
        print("  4. Browser cache or service worker issues")
    else:
        print("❌ SOME TESTS FAILED")
        print("\nCheck the failed tests above for details.")
        print("The backend may not be fully operational.")
    print("="*60)

if __name__ == "__main__":
    main()
