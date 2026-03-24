import asyncio
import os
import datetime
from playwright.async_api import async_playwright

LOG_FILE = "robust_audit.log"
SCREENSHOT_DIR = "audit_screenshots"

if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

def log(msg, status="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{status}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

async def test_module(page, module_name, url_hash):
    log(f"Testing Module: {module_name}", "START")
    try:
        await page.goto(f"http://localhost:3000/{url_hash}")
        await page.wait_for_timeout(3000) # Simple fixed wait for rendering
        path = os.path.join(SCREENSHOT_DIR, f"{module_name.lower().replace(' ', '_')}.png")
        await page.screenshot(path=path)
        log(f"Captured: {module_name}", "IMAGE")
        return True
    except Exception as e:
        log(f"Error in {module_name}: {e}", "FAIL")
        return False

async def run_audit():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    log("Starting Robust Platform Audit", "INIT")
    
    async with async_playwright() as p:
        extension_path = r"C:\Users\srihari\.gemini\antigravity-browser-profile\Default\Extensions\eeijfnjmjelapkebgockoeaadonbchdd\1.11.3_0"
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=os.path.join(os.getcwd(), "test_profile"),
            headless=False, # Extensions usually require non-headless mode
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}"
            ],
            viewport={'width': 1920, 'height': 1080}
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # 1. LOGIN
        log("Logging in...", "INIT")
        await page.goto("http://localhost:3000")
        try:
            await page.wait_for_selector('input[type="email"]', timeout=30000)
            await page.fill('input[type="email"]', 'super@omni.ai')
            await page.fill('input[type="password"]', 'password123')
            await page.click('button[type="submit"]')
            await page.wait_for_selector('text=Welcome back', timeout=30000)
        except:
            log("Login wait failed, continuing anyway...", "WARN")

        # Define modules to test
        modules = [
            ("01_Executive_Dashboard", "#dashboard"),
            ("02_Proactive_Insights", "#insights"),
            ("03_Distributed_Tracing", "#tracing"),
            ("04_Global_Reporting", "#reporting"),
            ("05_Log_Explorer", "#logs"),
            ("06_Network_Observability", "#network"),
            ("07_Agent_Fleet", "#agents"),
            ("08_Asset_Inventory", "#assets"),
            ("09_Patch_Management", "#patching"),
            ("10_Cloud_Security", "#cloudSecurity"),
            ("11_Security_Operations", "#security"),
            ("12_Threat_Hunting", "#threatHunting"),
            ("13_AI_Governance", "#aigovernance"),
            ("14_Tenant_Management", "#tenantManagement"),
            ("15_Compliance_Board", "#compliance"),
            ("16_Settings", "#settings")
        ]

        for name, url in modules:
            await test_module(page, name, url)
            
            # Special action for Compliance
            if "Compliance" in name:
                try:
                    log("Attempting Evidence Collection Trigger", "ACTION")
                    # Click Evidence tab by text or position
                    evidence_btn = page.locator('text=Evidence')
                    if await evidence_btn.count() > 0:
                        await evidence_btn.first.click()
                        await page.wait_for_timeout(1000)
                    
                    collect_btn = page.locator('button:has-text("Collect Evidence"), button:has-text("Evidence")')
                    if await collect_btn.count() > 0:
                        await collect_btn.first.click()
                        await page.wait_for_timeout(3000)
                        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "17_Evidence_Triggered.png"))
                        log("Evidence Collection triggered and screenshotted", "IMAGE")
                except Exception as e:
                    log(f"Special action failed: {e}", "WARN")

        log("Robust Audit Completed.", "FINISH")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_audit())
