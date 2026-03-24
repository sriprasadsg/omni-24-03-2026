import asyncio
from playwright.async_api import async_playwright
import os

async def debug_ui():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        # Capture console logs
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"PAGE ERROR: {exc}"))

        try:
            print("Navigating to Dashboard...")
            await page.goto("http://localhost:3000/", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path="debug_dashboard.png", full_page=True)
            print("Saved debug_dashboard.png")

            print("Navigating to Agents...")
            await page.goto("http://localhost:3000/agents", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await page.screenshot(path="debug_agents.png", full_page=True)
            print("Saved debug_agents.png")

        except Exception as e:
            print(f"Error: {e}")
            await page.screenshot(path="debug_error.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_ui())
