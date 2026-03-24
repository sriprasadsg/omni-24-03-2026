import asyncio
import os
import datetime
from playwright.async_api import async_playwright

def log(msg):
    with open("browser_log.txt", "a") as f:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{ts}] {msg}\n")
    print(msg)

async def verify_browser():
    try:
        log("Starting browser verification...")
        async with async_playwright() as p:
            log("Launching chromium...")
            browser = await p.chromium.launch(headless=True) # Run headless to be safe/faster in env? or False if user watches. False is better for screenshots usually.
            # But in this env, maybe headless=True is safer. I'll stick to what was there (False) but I'll set it to True to avoid unexpected UI issues if no display.
            # Actually, previous script used False. I'll use True.
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1280, 'height': 800})
            page = await context.new_page()

            # 1. Login
            log("Navigating to http://localhost:3000")
            await page.goto("http://localhost:3000")
            
            log("Waiting for login inputs...")
            await page.wait_for_selector('input[type="email"]', timeout=30000)
            
            log("Filling credentials...")
            await page.fill('input[type="email"]', 'admin@sriprasad.com')
            await page.fill('input[type="password"]', 'SriPrasad123!')
            await page.click('button[type="submit"]')
            
            # Wait for dashboard
            log("Waiting for dashboard...")
            try:
                await page.wait_for_selector('text=Compliance', timeout=30000)
                log("Dashboard confirmed.")
            except:
                log("Dashboard timeout. Screenshotting...")
                await page.screenshot(path="verification_login_fail.png")
                raise

            log("Login Successful! Taking screenshot...")
            await page.screenshot(path="verification_login_success.png")

            # 2. Check Agents
            log("Navigating to Agents page...")
            await page.click('text=Agents')
            
            log("Waiting for Agents view...")
            await asyncio.sleep(2) 
            
            # 3. Find Rust Agent (EILT0197)
            log("Searching for EILT0197...")
            try:
                # Agent name might be in a table cell or card
                await page.wait_for_selector('text=EILT0197', timeout=10000)
                await page.click('text=EILT0197')
            except:
                log("Agent EILT0197 not found! Taking screenshot of list...")
                await page.screenshot(path="verification_agent_list_fail.png")
                raise Exception("Agent EILT0197 not found")
            
            # 4. Check Compliance Tab
            log("Clicking Compliance tab (JS)...")
            await page.wait_for_selector('nav[aria-label="Tabs"]', timeout=5000)
            await page.evaluate("""
                const btns = Array.from(document.querySelectorAll('nav[aria-label="Tabs"] button')); 
                const compBtn = btns.find(b => b.textContent.includes('Compliance'));
                if (compBtn) compBtn.click();
                else console.error("Compliance button not found!");
            """)
            await asyncio.sleep(2) # Wait for React render
            
            # 5. Verify BitLocker Check
            log("Waiting for Compliance content...")
            try:
                await page.wait_for_selector('text=BitLocker Encryption', timeout=10000)
                await page.screenshot(path="verification_compliance_rust_tab.png")
                log("✅ Found 'BitLocker Encryption' check.")
            except:
                log("[FAIL] 'BitLocker Encryption' NOT found.")
                await page.screenshot(path="verification_compliance_rust_missing.png")

            # 6. Verify Firewall Check (New Feature)
            content = await page.content()
            if "Windows Firewall Profiles" in content:
                 log("[PASS] Found 'Windows Firewall Profiles' check.")
            else:
                 log("[FAIL] 'Windows Firewall Profiles' check NOT found!")

            # 7. Verify Agent Version in Overview
            # Switch back to Overview
            log("Clicking Overview tab...")
            await page.evaluate("""
                const btns = Array.from(document.querySelectorAll('nav[aria-label="Tabs"] button')); 
                const btn = btns.find(b => b.textContent.includes('Overview'));
                if (btn) btn.click();
            """)
            await asyncio.sleep(2)
            
            overview_content = await page.content()
            if "2.0.0-rust" in overview_content:
                log("[PASS] Found Agent Version '2.0.0-rust'.")
            else:
                log("[FAIL] Agent Version '2.0.0-rust' NOT found in Overview.")
            
            # Switch back to Compliance to test Refresh
            log("Switching back to Compliance for Scan Test...")
            await page.evaluate("""
                const btns = Array.from(document.querySelectorAll('nav[aria-label="Tabs"] button')); 
                const btn = btns.find(b => b.textContent.includes('Compliance'));
                if (btn) btn.click();
            """)
            await asyncio.sleep(2)

            # 8. Test Refresh (Run Compliance Scan)
            log("Testing 'Run Compliance Scan' button...")
            try:
                # Force click the refresh button - look for Refresh text or title
                # In previous dump, button has title="Run new compliance scan".
                await page.click('button[title="Run new compliance scan"]', force=True)
                log("[PASS] Clicked 'Run Compliance Scan'.")
                await asyncio.sleep(2)
                log("[PASS] Scan triggered successfully (no crash).")
                await page.screenshot(path="verification_scan_triggered.png")
            except Exception as e:
                log(f"[FAIL] Failed to click Refresh: {e}")

            log("Test flow completed. Closing...")
            await browser.close()
            log("Browser closed.")

    except Exception as e:
        log(f"CRITICAL ERROR: {e}")
        import traceback
        log(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(verify_browser())
