import asyncio
from playwright.async_api import async_playwright
import os

ARTIFACTS_DIR = r"C:\Users\srihari\.gemini\antigravity\brain\c2f9d45e-4cd4-49f1-8f58-fba51ba9fcaf"

async def test_governance():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        print("Navigating to platform...")
        await page.goto("http://localhost:3000")
        
        print("Logging in...")
        await page.fill('input[type="email"]', 'super@omni.ai')
        await page.fill('input[type="password"]', 'password123')
        await page.click('button:has-text("Sign In")')
        
        # Wait for dashboard to load
        await page.wait_for_selector('text=Overview', timeout=15000)
        print("Logged in successfully.")
        
        # Open Governance accordion
        print("Opening Governance & Compliance menu...")
        # To be safe, wait for sidebar
        await page.wait_for_selector('text=Governance & Compliance', timeout=10000)
        await page.click('text=Governance & Compliance')
        
        await asyncio.sleep(1) # wait for animation
        
        features_to_test = [
            "Compliance",
            "AI Governance",
            "Trust Center",
            "Data Governance",
            "Audit Log"
        ]
        
        for feature in features_to_test:
            print(f"Testing {feature}...")
            # Click the exact text matching the feature
            await page.click(f'text="{feature}"')
            # Wait a few seconds for data to load
            await asyncio.sleep(3)
            # Save screenshot
            path = os.path.join(ARTIFACTS_DIR, f"gov_test_{feature.replace(' ', '_').lower()}.png")
            await page.screenshot(path=path)
            print(f"Captured screenshot: {path}")

        await browser.close()
        print("All tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_governance())
