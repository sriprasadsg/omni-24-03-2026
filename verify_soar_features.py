import time
from playwright.sync_api import sync_playwright

def verify_soar():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 1. Login
        print("Logging in...")
        try:
            page.goto("http://localhost:3000/login", timeout=30000)
            page.fill("input[type='email']", "testadmin@example.com")
            page.fill("input[type='password']", "password123")
            page.click("button:has-text('Sign In')")
            page.wait_for_selector("text=Overview", timeout=30000)
            print("Login Check: OK")
        except Exception as e:
            print(f"Login Failed: {e}")
            page.screenshot(path="soar_verification_failure_login.png")
            return

        # 2. Verify Playbooks Route
        print("Navigating to Playbooks...")
        page.goto("http://localhost:3000/#playbooks")
        try:
            # Check for unique elements in PlaybookBuilder.tsx
            page.wait_for_selector("text=Playbook Builder (SOAR)", timeout=10000)
            # Check trigger dropdown
            page.wait_for_selector("text=Define Trigger", timeout=5000)
            
            # Interact: Click "Add Action Step"
            page.click("text=+ Add Action Step")
            page.wait_for_selector("text=Action #1", timeout=2000)
            page.screenshot(path="playbook_builder_verify.png")
            print("Playbooks UI Check: OK")
        except Exception as e:
             print(f"Playbooks Check Failed: {e}")
             page.screenshot(path="playbook_builder_failure.png")

        # 3. Verify AI Governance Route & Tab
        print("Navigating to AI Governance...")
        page.goto("http://localhost:3000/#aiGovernance")
        try:
            page.wait_for_selector("text=AI Governance (ISO 42001)", timeout=10000)
            
            # Click "LLM Firewall" tab (updated name from Guardrails to Firewall in code)
            page.click("button:has-text('LLM Firewall')")
            page.wait_for_selector("text=Generative AI Firewall", timeout=5000)
            
            # Verify toggles exist (PII Redaction)
            if page.locator("text=PII Redaction").is_visible():
                print("Guardrails: PII Redaction toggle found")
            else:
                print("Guardrails: PII Redaction toggle MISSING")

            page.screenshot(path="ai_guardrails_verify.png")
            print("AI Guardrails UI Check: OK")
        except Exception as e:
             print(f"AI Governance Check Failed: {e}")
             page.screenshot(path="ai_guardrails_failure.png")
        
        browser.close()

if __name__ == "__main__":
    verify_soar()
