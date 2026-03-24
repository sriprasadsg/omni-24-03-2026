import requests
import json
import time

BASE_URL = "http://localhost:5000/api/compliance_oracle"

def verify_oracle():
    print("--- Verifying Generative Compliance Oracle ---")

    # 1. Analyze Policy
    try:
        print("\n1. Analyzing Policy Text...")
        text = """
        Security Policy v1.2
        1. All S3 buckets must have server-side encryption enabled (AES256).
        2. Root user access must be protected with MFA.
        3. Audit logs must be retained for legal hold (90 days).
        """
        payload = {"policy_text": text}
        
        res = requests.post(f"{BASE_URL}/analyze", json=payload)
        
        if res.status_code == 200:
            data = res.json()
            print(f"   -> Success. Confidence: {data['confidence_score']:.2f}")
            print(f"   -> Summary: {data['summary']}")
            print("   -> Generated Technical Rules:")
            for rule in data.get('generated_rules', []):
                print(f"      [{rule['severity']}] {rule['rule_name']}")
                print(f"         Code: {rule['technical_implementation'][:60]}...")
        else:
            print(f"   -> Failed: {res.status_code} {res.text}")
            
    except Exception as e:
        print(f"   -> Error: {e}")

if __name__ == "__main__":
    verify_oracle()
