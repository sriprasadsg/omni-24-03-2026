import httpx
import asyncio
import json

async def test_vt():
    async with httpx.AsyncClient() as client:
        # Test 1: Check if configured
        config_resp = await client.get('http://localhost:5000/api/threat-intelligence/config')
        config = config_resp.json()
        print("VirusTotal Configuration:")
        print(f"  Configured: {config.get('configured')}")
        print(f"  Message: {config.get('message')}\n")
        
        if not config.get('configured'):
            print("⚠️ API key not detected. Make sure .env is loaded.")
            return
        
        # Test 2: Scan a known safe IP (Google DNS)
        print("Testing IP scan (8.8.8.8)...")
        scan_payload = {"artifact": "8.8.8.8", "type": "ip"}
        scan_resp = await client.post('http://localhost:5000/api/threat-intelligence/scan', json=scan_payload, timeout=15)
        result = scan_resp.json()
        
        print(f"  Verdict: {result.get('verdict')}")
        print(f"  Detection Ratio: {result.get('detectionRatio')}")
        print(f"  Malicious: {result.get('malicious', 0)}")
        print(f"  Suspicious: {result.get('suspicious', 0)}")
        print(f"  Harmless: {result.get('harmless', 0)}")
        
        if 'message' in result and 'MOCK' in result['message']:
            print("\n⚠️ Still using mock data - API key may not be loaded properly")
        else:
            print("\n✅ VirusTotal integration working with real API!")

if __name__ == "__main__":
    asyncio.run(test_vt())
