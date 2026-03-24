import asyncio
import os
import datetime
from playwright.async_api import async_playwright

LOG_FILE = "browser_audit.log"
SCREENSHOT_DIR = "audit_screenshots"

if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

def log(msg, status="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{status}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

async def take_screenshot(page, name):
    path = os.path.join(SCREENSHOT_DIR, f"{name.lower().replace(' ', '_')}.png")
    await page.wait_for_timeout(1000) # Buffer for rendering
    await page.screenshot(path=path)
    log(f"Captured: {name}", "IMAGE")

async def run_audit():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    log("Starting Comprehensive Platform Governance Audit", "INIT")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        # 1. LOGIN
        log("Testing Module: Authentication", "START")
        await page.goto("http://localhost:3000")
        await page.wait_for_selector('input[type="email"]', timeout=30000)
        await page.fill('input[type="email"]', 'super@omni.ai')
        await page.fill('input[type="password"]', 'password123')
        await page.click('button[type="submit"]')
        await page.wait_for_selector('text=Welcome back', timeout=30000)
        await take_screenshot(page, "01_Login_Success")

        # 2. DASHBOARD
        log("Testing Module: Executive Dashboard", "START")
        await page.goto("http://localhost:3000/#dashboard")
        await page.wait_for_selector('text=Welcome back', timeout=15000)
        await take_screenshot(page, "02_Dashboard")

        # 3. PROACTIVE INSIGHTS
        log("Testing Module: Proactive Insights", "START")
        await page.goto("http://localhost:3000/#insights")
        await page.wait_for_selector('text=AI Proactive Insights', timeout=10000)
        await take_screenshot(page, "03_Insights")

        # 4. REPORTING
        log("Testing Module: Global Reporting", "START")
        await page.goto("http://localhost:3000/#reporting")
        await page.wait_for_selector('text=Platform Reporting', timeout=10000)
        await take_screenshot(page, "04_Reporting")

        # 5. AGENTS (Smart Heuristics Check)
        log("Testing Module: Agent Fleet Management", "START")
        await page.goto("http://localhost:3000/#agents")
        await page.wait_for_selector('text=Agent Fleet Management', timeout=10000)
        await take_screenshot(page, "05_Agents")

        # 6. ASSETS
        log("Testing Module: Asset Inventory", "START")
        await page.goto("http://localhost:3000/#assets")
        await page.wait_for_selector('text=Asset Management', timeout=10000)
        await take_screenshot(page, "06_Assets")

        # 7. PATCHING (ML Prediction Check)
        log("Testing Module: Patch & Vulnerability Management", "START")
        await page.goto("http://localhost:3000/#patching")
        await page.wait_for_selector('text=Vulnerability Management', timeout=10000)
        await take_screenshot(page, "07_Patching")

        # 8. SECURITY (Vulnerability Scan & Governance)
        log("Testing Module: Security Operations", "START")
        await page.goto("http://localhost:3000/#security")
        await page.wait_for_selector('text=Security Operations', timeout=10000)
        await take_screenshot(page, "08_Security_Ops")

        # 9. AI GOVERNANCE (Shadow AI)
        log("Testing Module: AI Governance (ISO 42001)", "START")
        await page.goto("http://localhost:3000/#aigovernance")
        await page.wait_for_selector('text=AI Governance', timeout=10000)
        await page.click('text=Shadow AI')
        await take_screenshot(page, "09_AI_Governance_Shadow")

        # 10. COMPLIANCE (Evidence Collection Trigger)
        log("Testing Module: Compliance (Evidence Collection)", "START")
        await page.goto("http://localhost:3000/#compliance")
        await page.wait_for_selector('text=Compliance Management', timeout=10000)
        
        # Click Evidence tab
        evidence_tab = page.locator('text=Evidence')
        if await evidence_tab.count() > 0:
            await evidence_tab.first.click()
            await page.wait_for_timeout(1000)
        
        await take_screenshot(page, "10_Compliance_Overview")
        
        # Trigger Collection
        collect_btn = page.locator('button:has-text("Collect Evidence")')
        if await collect_btn.count() > 0:
            await collect_btn.first.click()
            log("Triggered Evidence Collection", "ACTION")
            await page.wait_for_timeout(3000) # Wait for confirmation
            await take_screenshot(page, "11_Evidence_Collection_Triggered")
        else:
            log("Collect Evidence button not found", "WARN")

        # 11. TENANT MANAGEMENT
        log("Testing Module: Multi-Tenancy", "START")
        await page.goto("http://localhost:3000/#tenantManagement")
        await page.wait_for_selector('text=Tenant Management', timeout=10000)
        await take_screenshot(page, "12_Tenant_Management")

        # 12. SETTINGS
        log("Testing Module: Settings & Configuration", "START")
        await page.goto("http://localhost:3000/#settings")
        await page.wait_for_selector('text=Settings & Configuration', timeout=10000)
        await take_screenshot(page, "13_Settings")

        log("Comprehensive Audit Completed.", "FINISH")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_audit())
