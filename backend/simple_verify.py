import httpx
import asyncio
import sys

async def test_all_features():
    base_url = "http://localhost:5000"
    
    async with httpx.AsyncClient() as client:
        print("FEATURE VERIFICATION TEST", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        
        # Test 1: Assets
        print("\n1. Assets API (RAM Display)...", file=sys.stderr)
        try:
            resp = await client.get(f"{base_url}/api/assets")
            assets = resp.json()
            if assets:
                ram = assets[0].get('ram', 'N/A')
                cpu = assets[0].get('cpuModel', 'N/A')
                sw_count = len(assets[0].get('installedSoftware', []))
                
                print(f"Assets: {len(assets)}, RAM: {ram}, CPU: {cpu}, Software: {sw_count}")
                if 'GB' in str(ram):
                    print("RAM_FORMAT:OK")
                else:
                    print(f"RAM_FORMAT:BAD:{ram}")
        except Exception as e:
            print(f"ASSETS:ERROR:{e}")
        
        # Test 2: Export
        print("\n2. Data Export...", file=sys.stderr)
        try:
            resp = await client.get(f"{base_url}/api/reports/export?type=Asset%20Inventory&format=csv", timeout=10)
            print(f"EXPORT:{'OK' if resp.status_code == 200 else 'FAIL'}:{resp.status_code}")
        except Exception as e:
            print(f"EXPORT:ERROR:{e}")
        
        # Test 3: Webhooks
        print("\n3. Webhooks...", file=sys.stderr)
        try:
            resp = await client.get(f"{base_url}/api/webhooks")
            print(f"WEBHOOKS:OK:{len(resp.json())}_hooks")
        except Exception as e:
            print(f"WEBHOOKS:ERROR:{e}")
        
        # Test 4: Settings
        print("\n4. Settings...", file=sys.stderr)
        try:
            db_resp = await client.get(f"{base_url}/api/settings/database")
            llm_resp = await client.get(f"{base_url}/api/settings/llm")
            print(f"SETTINGS:OK:DB_{db_resp.status_code}_LLM_{llm_resp.status_code}")
        except Exception as e:
            print(f"SETTINGS:ERROR:{e}")

        # Test 5: Security Modules (SAST/SBOM)
        print("\n5. Security Modules...", file=sys.stderr)
        try:
            sast_resp = await client.get(f"{base_url}/api/sast/statistics")
            sbom_resp = await client.get(f"{base_url}/api/sboms")
            print(f"SECURITY:SAST_{sast_resp.status_code}_SBOM_{sbom_resp.status_code}")
        except Exception as e:
            print(f"SECURITY:ERROR:{e}")

if __name__ == "__main__":
    asyncio.run(test_all_features())
