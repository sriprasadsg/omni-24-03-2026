
import asyncio
from playwright.async_api import async_playwright
import datetime

async def verify_system():
    log_file = "full_system_verification_log.txt"
    
    def log(msg):
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        formatted_msg = f"{timestamp} {msg}"
        print(formatted_msg)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")

    log("Starting Full System Verification (Run 4)...")
    
    services = [
        # Core
        {"name": "Dashboard", "hash": "#dashboard", "selector": "text=Welcome back"},
        {"name": "Agents", "hash": "#agents", "selector": "text=Agent Fleet Management"}, # Assuming this exists, verify if failing
        {"name": "Assets", "hash": "#assets", "selector": "text=Asset Inventory"},
        {"name": "Patching", "hash": "#patching", "selector": "text=Patch Management Dashboard"},
        
        # Security
        {"name": "Security", "hash": "#security", "selector": "text=Security Operations Center"},
        
        # Advanced
        {"name": "Digital Twin", "hash": "#digitalTwin", "selector": "text=Digital Twin"}, 
        {"name": "Sustainability", "hash": "#sustainability", "selector": "text=Sustainability"},
        {"name": "Chaos Engineering", "hash": "#chaosEngineering", "selector": "text=Chaos Engineering"},
        
        # AI
        {"name": "AI Governance", "hash": "#aiGovernance", "selector": "text=AI Governance"},
        {"name": "Swarm Intelligence", "hash": "#swarm", "selector": "text=Swarm Intelligence"},
        
    ]

    async with async_playwright() as p:
        log("Launching browser...")
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080}, record_video_dir="videos")
        page = await context.new_page()

        # Capture Console Logs
        page.on("console", lambda msg: log(f"BROWSER CONSOLE: {msg.text}"))
        page.on("pageerror", lambda exc: log(f"BROWSER ERROR: {exc}"))

        try:
            # Login
            log("Navigating to Login...")
            await page.goto("http://localhost:3000")
            await page.wait_for_selector('input[type="email"]')
            await page.fill('input[type="email"]', "admin@example.com")
            await page.fill('input[type="password"]', "admin")
            await page.click('button[type="submit"]')
            
            log("Waiting for Dashboard load...")
            try:
                # Updated selector based on HTML dump
                await page.wait_for_selector('text=Welcome back', timeout=20000)
                log("[PASS] Login Successful.")
                await page.screenshot(path="verify_dashboard_success.png")
            except Exception as e:
                log(f"[FAIL] Login Timeout. Current URL: {page.url}")
                await page.screenshot(path="login_fail_debug_v4.png")
                raise e

            # Iterate Services
            for service in services:
                log(f"Verifying {service['name']} ({service['hash']})...")
                try:
                    # Navigate via URL hash
                    await page.goto(f"http://localhost:3000/{service['hash']}")
                    
                    # Wait for selector
                    try:
                        await page.wait_for_selector(service['selector'], timeout=10000)
                        log(f"[PASS] {service['name']} Loaded.")
                        
                        # Take Screenshot
                        safe_name = service['name'].replace(" ", "_").lower()
                        await page.screenshot(path=f"verify_{safe_name}.png")
                        
                    except Exception as e:
                        log(f"[FAIL] {service['name']} Timeout looking for '{service['selector']}'")
                        await page.screenshot(path=f"verify_fail_{safe_name}.png")
                        content = await page.content()
                        # Dump content on fail to debug selector
                        with open(f"verify_fail_{safe_name}.html", "w", encoding="utf-8") as f:
                            f.write(content)
                        
                except Exception as e:
                     log(f"[ERROR] Navigating to {service['name']}: {e}")

        except Exception as e:
            log(f"[CRITICAL] Unexpected Error: {e}")
            await page.screenshot(path="verify_critical_error.png")

        finally:
            await browser.close()
            log("Verification Complete.")

if __name__ == "__main__":
    asyncio.run(verify_system())
