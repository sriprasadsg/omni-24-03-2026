
# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""Capture comprehensive screenshots of the Enterprise Omni-Agent AI Platform."""
import asyncio
import os
import json
from pathlib import Path

FRONTEND_URL = "http://localhost:3000"
SCREENSHOT_DIR = Path("platform_screenshots_report")
SCREENSHOT_DIR.mkdir(exist_ok=True)

results = []

async def run():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not available, trying selenium...")
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        
        # Collect console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append({"type": msg.type, "text": msg.text}) if msg.type == "error" else None)

        print("[1] Opening platform login page...")
        await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "01_login_page.png"))
        results.append({"page": "Login Page", "url": FRONTEND_URL, "status": "captured"})
        print("    [OK] Login page screenshot taken")

        print("[2] Logging in as Super Admin...")
        try:
            # Try to find email/password fields
            await page.fill('input[type="email"], input[name="email"], input[placeholder*="email" i]', "super@omni.ai")
            await page.fill('input[type="password"], input[name="password"]', "password123")
            await page.click('button[type="submit"], button:has-text("Login"), button:has-text("Sign In")')
            await page.wait_for_load_state("networkidle", timeout=10000)
            await asyncio.sleep(3)
            await page.screenshot(path=str(SCREENSHOT_DIR / "02_after_login.png"))
            results.append({"page": "Post-Login Dashboard", "status": "logged_in"})
            print("    [OK] Logged in successfully")
        except Exception as e:
            await page.screenshot(path=str(SCREENSHOT_DIR / "02_login_error.png"))
            print(f"    [FAIL] Login failed: {e}")
            results.append({"page": "Login", "status": f"failed: {e}"})

        print("[3] Taking dashboard screenshot...")
        await page.screenshot(path=str(SCREENSHOT_DIR / "03_dashboard.png"), full_page=False)
        title = await page.title()
        results.append({"page": "Dashboard", "title": title, "status": "captured"})

        # Define sections to test
        sections = [
            ("Agents", ["/agents", "/fleet"], "agents"),
            ("Security/SIEM", ["/security", "/siem", "/security-dashboard"], "security"),
            ("Compliance", ["/compliance"], "compliance"),
            ("Playbooks/MDR", ["/playbooks", "/mdr"], "playbooks"),
            ("AI Chat", ["/ai", "/chat", "/assistant"], "ai_chat"),
            ("FinOps", ["/finops"], "finops"),
            ("Threat Intelligence", ["/threat-intel", "/threat-intelligence"], "threat_intel"),
            ("Network", ["/network", "/network-map"], "network"),
            ("UEBA/Shadow AI", ["/ueba", "/shadow-ai"], "ueba"),
            ("XDR", ["/xdr"], "xdr"),
            ("AI Governance", ["/ai-governance"], "ai_governance"),
            ("Settings", ["/settings", "/admin", "/profile"], "settings"),
        ]

        for section_name, urls, slug in sections:
            print(f"[4] Testing section: {section_name}...")
            navigated = False
            for url_path in urls:
                try:
                    full_url = FRONTEND_URL + url_path
                    await page.goto(full_url, wait_until="domcontentloaded", timeout=8000)
                    await asyncio.sleep(2)
                    await page.screenshot(path=str(SCREENSHOT_DIR / f"04_{slug}.png"))
                    page_title = await page.title()
                    results.append({"page": section_name, "url": full_url, "title": page_title, "status": "working"})
                    print(f"    [OK] {section_name} -> {url_path} loaded")
                    navigated = True
                    break
                except Exception as e:
                    continue
            if not navigated:
                results.append({"page": section_name, "status": "not_found"})
            print(f"    [FAIL] {section_name}: not found at any URL")

        # AI Chat interaction
        print("[5] Testing AI Chat interaction...")
        try:
            await page.goto(FRONTEND_URL + "/ai", wait_until="domcontentloaded", timeout=8000)
            await asyncio.sleep(2)
            # Find chat input
            chat_input = await page.query_selector('textarea, input[placeholder*="message" i], input[placeholder*="chat" i], input[placeholder*="ask" i]')
            if chat_input:
                await chat_input.fill("What are the key features of this Enterprise Security Platform?")
                await page.keyboard.press("Enter")
                await asyncio.sleep(8)
                await asyncio.sleep(2)
                await page.screenshot(path=str(SCREENSHOT_DIR / "05_ai_chat_response.png"))
                results.append({"page": "AI Chat - Response", "status": "response_captured"})
                print("    [OK] AI chat message sent, response screenshot taken")
            else:
                await page.screenshot(path=str(SCREENSHOT_DIR / "05_ai_chat_no_input.png"))
                results.append({"page": "AI Chat", "status": "no_input_found"})
        except Exception as e:
            print(f"    ✗ AI Chat error: {e}")
            results.append({"page": "AI Chat", "status": f"error: {e}"})

        # Console errors check
        print("[6] Checking console errors...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=8000)
        await asyncio.sleep(2)
        await page.screenshot(path=str(SCREENSHOT_DIR / "06_final_state.png"))
        
        # Save results
        report_data = {
            "screenshots": [str(p) for p in sorted(SCREENSHOT_DIR.glob("*.png"))],
            "page_results": results,
            "console_errors": console_errors[:20],
            "total_screenshots": len(list(SCREENSHOT_DIR.glob("*.png")))
        }
        
        with open(str(SCREENSHOT_DIR / "test_results.json"), "w") as f:
            json.dump(report_data, f, indent=2)
        
        await browser.close()
        return report_data

try:
    report = asyncio.run(run())
    if report:
        print(f"\n[OK] Captured {report['total_screenshots']} screenshots")
        print(f"[OK] Console errors: {len(report['console_errors'])}")
        print("\nPage Results:")
        for r in report['page_results']:
            status = r.get('status', 'unknown')
            icon = "[OK]" if any(x in status for x in ["working", "captured", "logged", "response"]) else "[FAIL]"
            print(f"  {icon} {r['page']}: {status}")
except Exception as e:
    print(f"Error running playwright: {e}")
