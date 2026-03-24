"""
Test Rate Limiting on Login Endpoint
Verifies that login rate limiting prevents brute force attacks
"""
import requests
import time

BASE_URL = "http://localhost:5000"

def test_login_rate_limit():
    """Test that login endpoint rate limits after 5 attempts"""
    print("=" * 70)
    print("TESTING LOGIN RATE LIMITING (5 attempts/minute)")
    print("=" * 70)
    
    results = []
    
    for i in range(7):  # Try 7 login attempts
        print(f"\nAttempt {i+1}:")
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "nonexistent@test.com", "password": "wrongpassword"},
                timeout=5
            )
            
            status = response.status_code
            results.append(status)
            
            if status == 429:
                print(f"  ❌ Rate Limited! Status: {status}")
                print(f"  Response: {response.text[:200]}")
            elif status == 401:
                print(f"  🔒 Unauthorized (expected). Status: {status}")
            else:
                print(f"  ⚠️  Unexpected status: {status}")
                print(f"  Response: {response.text[:200]}")
            
            time.sleep(0.5)  # Small delay between requests
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append(None)
    
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    
    print(f"Total attempts: {len(results)}")
    print(f"Successful (401 - wrong password): {results.count(401)}")
    print(f"Rate limited (429): {results.count(429)}")
    print(f"Errors: {results.count(None)}")
    
    # Check if rate limiting kicked in
    rate_limited_count = results.count(429)
    
    print("\n" + "=" * 70)
    if rate_limited_count >= 2:  # 6th and 7th should be rate limited
        print("✅ PASS: Rate limiting is working correctly!")
        print(f"   First 5 attempts allowed (401), attempts 6-7 blocked (429)")
        return True
    elif rate_limited_count > 0:
        print("⚠️  PARTIAL: Rate limiting working but not consistent")
        return False
    else:
        print("❌ FAIL: No rate limiting detected")
        print("   All 7 attempts were allowed (should limit after 5)")
        return False

def test_signup_rate_limit():
    """Test that signup endpoint rate limits after 3 attempts"""
    print("\n\n" + "=" * 70)
    print("TESTING SIGNUP RATE LIMITING (3 attempts/minute)")
    print("=" * 70)
    
    results = []
    
    for i in range(5):  # Try 5 signup attempts
        print(f"\nAttempt {i+1}:")
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/signup",
                json={
                    "companyName": f"TestCorp{i}",
                    "name": "Test User",
                    "email": f"test{i}@example.com",
                    "password": "testpass123"
                },
                timeout=5
            )
            
            status = response.status_code
            results.append(status)
            
            if status == 429:
                print(f"  ❌ Rate Limited! Status: {status}")
            elif status == 200:
                print(f"  ✅ Signup successful. Status: {status}")
            else:
                print(f"  ⚠️  Status: {status}")
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append(None)
    
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    
    print(f"Total attempts: {len(results)}")
    print(f"Successful (200): {results.count(200)}")
    print(f"Rate limited (429): {results.count(429)}")
    
    rate_limited_count = results.count(429)
    
    print("\n" + "=" * 70)
    if rate_limited_count >= 2:  # 4th and 5th should be rate limited
        print("✅ PASS: Signup rate limiting is working!")
        return True
    else:
        print("⚠️  Signup rate limiting needs verification")
        return False

if __name__ == "__main__":
    print("\n\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "RATE LIMITING COMPREHENSIVE TEST" + " " * 21 + "║")
    print("╚" + "=" * 68 + "╝")
    
    # Test 1: Login rate limiting
    login_pass = test_login_rate_limit()
    
    # Allow rate limit to reset
    print("\n\n⏱️  Waiting 10 seconds for rate limit to partially reset...")
    time.sleep(10)
    
    # Test 2: Signup rate limiting
    signup_pass = test_signup_rate_limit()
    
    print("\n\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"Login Rate Limiting: {'✅ PASS' if login_pass else '❌ FAIL'}")
    print(f"Signup Rate Limiting: {'✅ PASS' if signup_pass else '⚠️  PARTIAL'}")
    
    if login_pass:
        print("\n🎉 Rate limiting is successfully protecting your authentication endpoints!")
    else:
        print("\n⚠️  Rate limiting may need adjustment or backend restart")
    
    print("=" * 70)
