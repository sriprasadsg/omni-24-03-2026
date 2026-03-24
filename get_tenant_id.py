import requests

try:
    response = requests.get("http://localhost:8000/api/tenants")
    tenants = response.json()
    acme = next((t for t in tenants if t['name'] == 'Acme Corp'), None)
    if acme:
        print(acme['id'])
    else:
        print("Acme Corp not found")
except Exception as e:
    print(f"Error: {e}")
