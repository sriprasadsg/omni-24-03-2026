import requests

dashboard = "http://localhost:5000/api/compliance/frameworks/pci-dss"
res = requests.get(dashboard)

if res.status_code == 200:
    data = res.json()
    metrics = data.get("metrics", {})
    score = metrics.get('complianceScore', 0)
    passed = metrics.get('passedControls', 0)
    failed = metrics.get('failedControls', 0)
    print(f"PCI-DSS Current Score: {score}% | Passed: {passed} | Failed: {failed}")
    
    # Check PCI 8.1.1 (Password Policy)
    controls = data.get("controls", [])
    for c in controls:
        if "8.1.8" in c.get("id", "") or "3.4" in c.get("id", "") or "8.1.1" in c.get("id", "") or "7.1" in c.get("id", ""):
            print(f"- Control {c.get('id')}: {c.get('status')}")
            if "evidence" in c and len(c["evidence"]) > 0:
                print(f"  -> Evidence Length: {len(c['evidence'][0].get('evidence_content', ''))}")
else:
    print(f"Error calling API: {res.status_code} - {res.text}")
