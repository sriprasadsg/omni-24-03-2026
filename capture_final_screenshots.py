import asyncio
from playwright.async_api import async_playwright
import os
import time

async def capture():
    async with async_playwright() as p:
        # Using a fixed browser to ensure consistent rendering
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 900})
        page = await context.new_page()
        
        print("Logging in...")
        await page.goto('http://localhost:3000')
        await page.wait_for_selector('input[type="email"]')
        await page.fill('input[type="email"]', 'super@omni.ai')
        await page.fill('input[type="password"]', 'password123')
        await page.click('button[type="submit"]')
        
        await page.wait_for_selector('text=Welcome back', timeout=60000)
        await asyncio.sleep(3) # Wait for animations to settle
        print("Capturing Dashboard...")
        await page.screenshot(path='flashy_dashboard_final.png')
        
        views = {
            'agents': 'flashy_agents_final.png',
            'compliance': 'flashy_compliance_final.png',
            'security': 'flashy_security_final.png',
            'aigovernance': 'flashy_ai_gov_final.png'
        }
        
        for hash_route, filename in views.items():
            print(f"Capturing {hash_route}...")
            await page.goto(f'http://localhost:3000/#{hash_route}')
            await asyncio.sleep(2)
            await page.screenshot(path=filename)
            
        await browser.close()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(capture())
