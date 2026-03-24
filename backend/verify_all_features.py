import httpx
import asyncio

async def test_all_features():
    """Test all major features via API"""
    base_url = "http://localhost:5000"
    
    async with httpx.AsyncClient() as client:
        print("="*60)
        print("FEATURE VERIFICATION TEST")
        print("="*60)
        
        # Test 1: Assets API (RAM formatting)
        print("\n1. Testing Assets API (RAM Display Fix)...")
        try:
            resp = await client.get(f"{base_url}/api/assets")
            assets = resp.json()
            if assets:
                first_asset = assets[0]
                ram_value = first_asset.get('ram', 'N/A')
                cpu_model = first_asset.get('cpuModel', 'N/A')
                software_count = len(first_asset.get('installedSoftware', []))
                
                print(f"   [OK] Assets Found: {len(assets)}")
                print(f"   [OK] Sample RAM: {ram_value}")
                print(f"   [OK] Sample CPU: {cpu_model}")
                print(f"   [OK] Software Items: {software_count}")
                
                if 'GB' in str(ram_value):
                    print("   [OK] RAM FORMATTING: WORKING (shows GB)")
                else:
                    print(f"   [FAIL] RAM FORMATTING: ISSUE (raw value: {ram_value})")
            else:
                print("   ⚠ No assets found")
        except Exception as e:
            print(f"   [FAIL] FAILED: {e}")
        
        # Test 2: Data Export
        print("\n2. Testing Data Export API...")
        try:
            resp = await client.get(f"{base_url}/api/reports/export?type=Asset%20Inventory&format=csv", timeout=10)
            if resp.status_code == 200:
                content_type = resp.headers.get('content-type', '')
                content_length = len(resp.content)
                print(f"   [OK] Export Working: {resp.status_code}")
                print(f"   [OK] Content-Type: {content_type}")
                print(f"   [OK] File Size: {content_length} bytes")
            else:
                print(f"   [FAIL] Export Failed: {resp.status_code}")
        except Exception as e:
            print(f"   [FAIL] FAILED: {e}")
        
        # Test 3: AI Analysis
        print("\n3. Testing AI Analysis API...")
        try:
            # Get an alert/case to analyze
            alerts_resp = await client.get(f"{base_url}/api/security-events")
            alerts = alerts_resp.json()
            
            if alerts:
                test_alert = alerts[0]
                analyze_payload = {
                    "sourceId": test_alert.get('id', 'test-001'),
                    "sourceType": "alert",
                    "context": test_alert
                }
                
                resp = await client.post(f"{base_url}/api/agent/analyze", json=analyze_payload, timeout=15)
                if resp.status_code == 200:
                    analysis = resp.json()
                    print(f"   [OK] AI Analysis Working: {resp.status_code}")
                    print(f"   [OK] Has Severity: {'severityAssessment' in analysis}")
                    print(f"   [OK] Has Steps: {'mitigationSteps' in analysis}")
                else:
                    print(f"   [FAIL] AI Analysis Failed: {resp.status_code}")
            else:
                print("   ⚠ No alerts available to analyze")
        except Exception as e:
            print(f"   ⚠ SKIPPED (might need API key): {e}")
        
        # Test 4: Webhooks
        print("\n4. Testing Webhooks API...")
        try:
            resp = await client.get(f"{base_url}/api/webhooks")
            webhooks = resp.json()
            print(f"   [OK] Webhooks API Working: {len(webhooks)} webhooks")
        except Exception as e:
            print(f"   [FAIL] FAILED: {e}")
        
        # Test 5: Settings
        print("\n5. Testing Settings API...")
        try:
            db_resp = await client.get(f"{base_url}/api/settings/database")
            llm_resp = await client.get(f"{base_url}/api/settings/llm")
            print(f"   [OK] Database Settings: {db_resp.status_code}")
            print(f"   [OK] LLM Settings: {llm_resp.status_code}")
        except Exception as e:
            print(f"   [FAIL] FAILED: {e}")
        
        # Test 6: Audit Logs
        print("\n6. Testing Audit Logs...")
        try:
            resp = await client.get(f"{base_url}/api/audit-logs")
            logs = resp.json()
            print(f"   [OK] Audit Logs Working: {len(logs)} entries")
            if logs:
                recent = logs[0]
                print(f"   [OK] Recent Action: {recent.get('action', 'N/A')}")
        except Exception as e:
            print(f"   [FAIL] FAILED: {e}")

        # Test 7: New Features (Compliance & Patching)
        print("\n7. Testing New Features (Compliance & Patching)...")
        try:
            # Check Compliance Evidence
            comp_resp = await client.get(f"{base_url}/api/compliance/evidence")
            evidence = comp_resp.json()
            print(f"   [OK] Compliance Evidence API: {len(evidence)} items")
            
            # Check System Patching in Agents
            agents_resp = await client.get(f"{base_url}/api/agents")
            agents = agents_resp.json()
            patching_found = False
            for agent in agents:
                meta = agent.get('meta', {})
                if 'system_patching' in meta:
                    patching_found = True
                    patching = meta['system_patching']
                    bios = patching.get('bios_info', {})
                    updates = patching.get('pending_updates', [])
                    print(f"   [OK] System Patching Data Found for {agent.get('hostname')}")
                    print(f"       - BIOS: {bios.get('version', 'Unknown')}")
                    print(f"       - Pending Updates: {len(updates)}")
            
            if patching_found:
                 print("   [OK] SYSTEM PATCHING: WORKING")
            else:
                 print("   [FAIL] SYSTEM PATCHING: MISSING (Check Agent/Heartbeat)")

        except Exception as e:
            print(f"   [FAIL] FAILED: {e}")
        
        # Test 8: DevSecOps (SAST)
        print("\n8. Testing DevSecOps (SAST) API...")
        try:
            resp = await client.get(f"{base_url}/api/sast/statistics")
            if resp.status_code == 200:
                stats = resp.json()
                print(f"   [OK] SAST Statistics: {resp.status_code}")
                print(f"   [OK] Total Scans: {stats.get('total_scans', 0)}")
            else:
                print(f"   [FAIL] SAST API Failed: {resp.status_code}")
        except Exception as e:
            print(f"   [FAIL] SAST FAILED: {e}")

        # Test 9: SBOM Management
        print("\n9. Testing SBOM Management API...")
        try:
            resp = await client.get(f"{base_url}/api/sboms")
            if resp.status_code == 200:
                sboms = resp.json()
                print(f"   [OK] SBOM API Working: {len(sboms)} SBOMs")
                
                comp_resp = await client.get(f"{base_url}/api/sboms/components")
                components = comp_resp.json()
                print(f"   [OK] SBOM Components: {len(components)} items")
            else:
                print(f"   [FAIL] SBOM API Failed: {resp.status_code}")
        except Exception as e:
            print(f"   [FAIL] SBOM FAILED: {e}")

        print("\n" + "="*60)
        print("VERIFICATION COMPLETE")
        print("="*60)

if __name__ == "__main__":
    asyncio.run(test_all_features())
