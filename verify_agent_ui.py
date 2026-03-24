import asyncio
from playwright.async_api import async_playwright
import time

async def verify_agent_ui():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        # Login
        print("Logging in...")
        await page.goto("http://localhost:3000/login")
        await page.fill('input[type="email"]', "admin@example.com")
        await page.fill('input[type="password"]', "password")
        await page.click('button[type="submit"]')
        
        # Wait for navigation to dashboard
        await page.wait_for_url("http://localhost:3000/")
        print("Logged in successfully.")

        # Navigate to Agents
        print("Navigating to Agents...")
        await page.click('a[href="/agents"]')
        await page.wait_for_selector('h1:has-text("Agent Fleet Management")')
        
        # Take screenshot of Agent Fleet View
        print("Capturing Agent Fleet View...")
        await asyncio.sleep(2) # Wait for animations
        await page.screenshot(path="agent_fleet_view.png")
        print("Saved agent_fleet_view.png")

        # Click on Agent EILT0197
        print("Opening Agent Details...")
        try:
             # Find the row or card for EILT0197. It might be in a list or grid.
             # Based on previous AgentList.tsx, it renders cards.
             # We look for valid text "EILT0197"
             await page.click('text=EILT0197')
             await asyncio.sleep(2) # Wait for modal
             
             # Take screenshot of Agent Details Overview
             await page.screenshot(path="agent_details_overview.png")
             print("Saved agent_details_overview.png")

             # Switch to Compliance Tab if it exists
             # The tabs might be buttons.
             # "Compliance"
             if await page.is_visible('button:has-text("Compliance")'):
                 await page.click('button:has-text("Compliance")')
                 await asyncio.sleep(2)
                 await page.screenshot(path="agent_details_compliance.png")
                 print("Saved agent_details_compliance.png")
             else:
                 print("Compliance tab not found.")

        except Exception as e:
            print(f"Error interacting with agent details: {e}")
            await page.screenshot(path="error_state.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify_agent_ui())
