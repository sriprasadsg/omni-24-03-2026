import asyncio
from playwright.async_api import async_playwright
import os

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Opening http://localhost:3000...")
        await page.goto("http://localhost:3000")
        await asyncio.sleep(2)
        
        print("Logging in...")
        await page.fill('input[type="email"]', "super@omni.ai")
        await page.fill('input[type="password"]', "password123")
        await page.click('button:has-text("Sign In"), button[type="submit"]')
        
        await asyncio.sleep(5)
        await page.screenshot(path="dashboard_v4.png")
        print("Screenshot saved: dashboard_v4.png")
        
        # Check for frameworks
        print("Checking Compliance page...")
        await page.goto("http://localhost:3000/#/compliance")
        await asyncio.sleep(5)
        await page.screenshot(path="compliance_v4.png")
        print("Screenshot saved: compliance_v4.png")
        
        # Check Swarm
        print("Checking Swarm page...")
        await page.goto("http://localhost:3000/#/swarm-coordinator")
        await asyncio.sleep(5)
        await page.screenshot(path="swarm_v4.png")
        print("Screenshot saved: swarm_v4.png")
        
        # Check FinOps
        print("Checking FinOps page...")
        await page.goto("http://localhost:3000/#/finops")
        await asyncio.sleep(5)
        await page.screenshot(path="finops_v4.png")
        print("Screenshot saved: finops_v4.png")

        # Check Capabilities
        print("Checking Capabilities page...")
        await page.goto("http://localhost:3000/#/capabilities")
        await asyncio.sleep(5)
        await page.screenshot(path="capabilities_v4.png")
        print("Screenshot saved: capabilities_v4.png")

        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_test())
