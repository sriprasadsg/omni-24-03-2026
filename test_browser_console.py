import asyncio
from playwright.async_api import async_playwright
import time
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Log all console messages
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.type} {msg.text}"))
        
        # Login
        await page.goto("http://localhost:3000")
        await page.wait_for_selector('input[type="email"]', timeout=60000)
        await page.fill('input[type="email"]', 'super@omni.ai')
        await page.fill('input[type="password"]', 'password123')
        await page.click('button[type="submit"]')
        await page.wait_for_selector('text=Welcome back', timeout=30000)
        
        # Go to agents dashboard
        await page.goto("http://localhost:3000/#agents")
        
        # Wait to let polling and health checks run
        print("Waiting 15 seconds to collect logs...")
        await asyncio.sleep(15)
        
        # Check DOM for offline badge
        offline_count = await page.locator("text=Offline").count()
        online_count = await page.locator("text=Online").count()
        print(f"Badges found - Offline: {offline_count}, Online: {online_count}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
