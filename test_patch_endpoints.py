
import requests

def test_patch_endpoints():
    base_url = "http://127.0.0.1:5000"
    endpoints = [
        "/api/patches/outdated",
        "/api/patches/os",
        "/api/patches/scan"
    ]
    
    print(f"Testing endpoints on {base_url}...")
    for ep in endpoints:
        try:
            url = f"{base_url}{ep}"
            # Using GET for scan too just to check if it returns 404 or 405
            res = requests.get(url, timeout=5)
            print(f"GET {ep}: Status={res.status_code}")
            
            if ep == "/api/patches/scan":
                res_post = requests.post(url, timeout=5)
                print(f"POST {ep}: Status={res_post.status_code}")
        except Exception as e:
            print(f"Error testing {ep}: {e}")

if __name__ == "__main__":
    test_patch_endpoints()
