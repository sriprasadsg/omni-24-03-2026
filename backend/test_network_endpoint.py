import urllib.request
import json
import sys

def test_endpoint():
    # Login to get token
    req = urllib.request.Request('http://127.0.0.1:5000/api/auth/login', 
                                 data=json.dumps({'email':'admin@example.com', 'password':'admin123'}).encode('utf-8'), 
                                 headers={'Content-Type': 'application/json'})
    res = urllib.request.urlopen(req)
    token = json.loads(res.read())['access_token']
    
    # Call the broken endpoint
    req2 = urllib.request.Request('http://127.0.0.1:5000/api/agents/network-utilization', 
                                  headers={'Authorization': f'Bearer {token}'})
    try:
        print(urllib.request.urlopen(req2).read().decode())
    except Exception as e:
        print("ERROR:", e)

test_endpoint()
