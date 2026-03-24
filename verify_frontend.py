from playwright.sync_api import sync_playwright
import time
import os

BASE_URL = "http://localhost:3000"
LOGIN_URL = f"{BASE_URL}/login"
EVIDENCE_DIR = "frontend_evidence"

if not os.path.exists(EVIDENCE_DIR):
    os.makedirs(EVIDENCE_DIR)

def verify_frontend():
    print("--- Starting Frontend Verification (Playwright) ---")
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        try:
            # 1. Login
            print("1. Logging in...")
            page.goto(LOGIN_URL)
            page.wait_for_selector("input[type='email']", state="visible", timeout=10000)
            
            page.fill("input[type='email']", "super@omni.ai")
            page.fill("input[type='password']", "password123")
            page.click("button:has-text('Sign In')")
            
            # Wait for dashboard (look for "Dashboard" text or sidebar)
            print("   -> Waiting for Dashboard access...")
            page.wait_for_selector("text=Dashboard", timeout=15000)
            page.wait_for_timeout(2000) # Let animations finish
            page.screenshot(path=f"{EVIDENCE_DIR}/01_dashboard.png")
            print("   -> Dashboard Access: PASSED")

            # 2. MLOps
            print("2. Verifying MLOps Dashboard...")
            page.goto(f"{BASE_URL}/#mlops")
            page.wait_for_timeout(2000)
            page.screenshot(path=f"{EVIDENCE_DIR}/02_mlops.png")
            print("   -> MLOps Page: CAPTURED")

            # 3. XAI
            print("3. Verifying XAI Dashboard...")
            page.goto(f"{BASE_URL}/#xai")
            page.wait_for_timeout(2000)
            page.screenshot(path=f"{EVIDENCE_DIR}/03_xai.png")
            print("   -> XAI Page: CAPTURED")
            
            # 4. A/B Testing
            print("4. Verifying A/B Testing...")
            page.goto(f"{BASE_URL}/#abTesting")
            page.wait_for_timeout(2000)
            page.screenshot(path=f"{EVIDENCE_DIR}/04_ab_testing.png")
            print("   -> A/B Testing Page: CAPTURED")

            # 5. AI Governance (Shadow AI)
            print("5. Verifying AI Governance...")
            page.goto(f"{BASE_URL}/#aiGovernance")
            page.wait_for_timeout(2000)
            page.screenshot(path=f"{EVIDENCE_DIR}/05_ai_governance.png")
            print("   -> AI Governance Page: CAPTURED")
            
            # 6. Integrations (Settings)
            print("6. Verifying Integrations...")
            page.goto(f"{BASE_URL}/#settings")
            page.wait_for_timeout(2000)
            page.screenshot(path=f"{EVIDENCE_DIR}/06_settings.png")
            print("   -> Settings Page: CAPTURED")

            print("\nFrontend Verification Complete. Screenshots saved.")
            
        except Exception as e:
            print(f"\nFrontend Verification Failed: {e}")
            page.screenshot(path=f"{EVIDENCE_DIR}/error_state.png")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_frontend()
