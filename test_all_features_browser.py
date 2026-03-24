import asyncio
import os
import datetime
from playwright.async_api import async_playwright

LOG_FILE = "feature_report_screenshots.txt"
SCREENSHOT_DIR = "platform_screenshots_final"

if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

async def run_screenshot_suite():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        # 1. Login
        print("Logging in...")
        await page.goto("http://localhost:3000")
        await page.wait_for_selector('input[type="email"]', timeout=30000)
        await page.fill('input[type="email"]', 'super@omni.ai')
        await page.fill('input[type="password"]', 'password123')
        await page.click('button:has-text("Sign In")')
        await asyncio.sleep(8) # Wait for dashboard
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "01_dashboard.png"))

        # 2. CXO Insights
        print("Capturing CXO Insights...")
        await page.click('text="CXO Insights"')
        await asyncio.sleep(4)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "02_cxo_insights.png"))

        # 3. Proactive Insights
        print("Capturing Proactive Insights...")
        await page.click('text="Proactive Insights"')
        await asyncio.sleep(4)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "03_proactive_insights.png"))

        # 4. Agents
        print("Capturing Agents...")
        await page.click('text="Infrastructure & Assets"')
        await asyncio.sleep(2)
        await page.click('text="Agents"')
        await asyncio.sleep(4)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "04_agents.png"))

        # 5. Compliance
        print("Capturing Compliance...")
        await page.click('text="Governance & Compliance"')
        await asyncio.sleep(2)
        await page.click('text="Compliance"')
        await asyncio.sleep(4)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "05_compliance.png"))

        # 6. Shadow AI
        print("Capturing Shadow AI...")
        await page.click('text="AI Governance"')
        await asyncio.sleep(2)
        await page.click('text="Shadow AI"')
        await asyncio.sleep(4)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "06_shadow_ai.png"))

        # 7. Sustainability
        print("Capturing Sustainability...")
        await page.click('text="Sustainability"')
        await asyncio.sleep(4)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "07_sustainability.png"))

        # 8. Settings
        print("Capturing Settings...")
        await page.click('text="Management & Settings"')
        await asyncio.sleep(2)
        await page.click('text="Settings"')
        await asyncio.sleep(4)
        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "08_settings.png"))

        await browser.close()
        print("Screenshot suite complete.")

if __name__ == "__main__":
    asyncio.run(run_screenshot_suite())
