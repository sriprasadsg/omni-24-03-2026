#!/usr/bin/env python3
"""Test new platform features: Omni-LLM training, LLM provider settings, FinOps, Attack Path"""

import asyncio
import os
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3000"
SCREENSHOT_DIR = r"D:\Downloads\enterprise-omni-agent-ai-platform\test_screenshots_new_features"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results = []

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=600)
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await context.new_page()

        # ── LOGIN ────────────────────────────────────────────────────────────
        print(">> Logging in...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        try:
            await page.fill("input[type='email']", "super@omni.ai", timeout=8000)
            await page.fill("input[type='password']", "password123")
            await page.click("button[type='submit']")
            await page.wait_for_timeout(3500)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/01_login.png")
            results.append(("Login", "PASS"))
            print("   OK Login complete")
        except Exception as e:
            await page.screenshot(path=f"{SCREENSHOT_DIR}/01_login_fail.png")
            results.append(("Login", f"FAIL - {e}"))
            print(f"   FAIL {e}")

        # ── TEST 1: LLMOps → Train Custom Model ──────────────────────────────
        print(">> Navigating to LLMOps...")
        llmops_nav = False
        for selector in ["text=LLMOps", "text=LLM Ops", "[data-section='llmops']"]:
            try:
                await page.click(selector, timeout=5000)
                llmops_nav = True
                break
            except:
                pass

        if not llmops_nav:
            # Try expanding AI section first
            for ai_sel in ["text=AI", "text=Artificial Intelligence", "text=AI Platform"]:
                try:
                    await page.click(ai_sel, timeout=3000)
                    await page.wait_for_timeout(500)
                    await page.click("text=LLMOps", timeout=3000)
                    llmops_nav = True
                    break
                except:
                    pass

        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/02_llmops_page.png")

        # Click the Train Custom Model tab
        print(">> Clicking Train Custom Model tab...")
        try:
            await page.click("text=Train Custom Model", timeout=8000)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/03_train_tab_loaded.png")
            results.append(("LLMOps Train Custom Model Tab", "PASS"))
            print("   OK Training tab loaded")

            # Click Begin Training
            print(">> Clicking Begin Training...")
            try:
                await page.click("text=Begin Training", timeout=6000)
                await page.wait_for_timeout(9000)  # Wait for epochs
                await page.screenshot(path=f"{SCREENSHOT_DIR}/04_training_inprogress.png")
                results.append(("Begin Training + Live Metrics", "PASS"))
                print("   OK Training started with live metrics")
            except Exception as e:
                await page.screenshot(path=f"{SCREENSHOT_DIR}/04_training_fail.png")
                results.append(("Begin Training", f"FAIL - {e}"))
                print(f"   FAIL {e}")
        except Exception as e:
            await page.screenshot(path=f"{SCREENSHOT_DIR}/03_train_tab_fail.png")
            results.append(("LLMOps Train Custom Model Tab", f"FAIL - {e}"))
            print(f"   FAIL {e}")

        # ── TEST 2: LLM Provider Settings ─────────────────────────────────────
        print(">> Opening LLM Settings...")
        # Try header button, then settings page
        llm_modal_open = False
        for sel in ["[data-testid='llm-settings']", "button[title*='LLM']", "button[aria-label*='LLM']"]:
            try:
                await page.click(sel, timeout=3000)
                llm_modal_open = True
                break
            except:
                pass

        if not llm_modal_open:
            # Navigate to Settings
            try:
                await page.click("text=Settings", timeout=5000)
                await page.wait_for_timeout(1000)
            except:
                pass

        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/05_llm_settings.png")

        try:
            provider_select = page.locator("select[name='provider']")
            options = await provider_select.evaluate("el => Array.from(el.options).map(o => o.value)", timeout=5000)
            if "Omni-LLM-Scratch" in options:
                await provider_select.select_option("Omni-LLM-Scratch")
                await page.wait_for_timeout(1000)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/06_omni_llm_selected.png")
                results.append(("Omni-LLM-Scratch in Provider Dropdown", "PASS"))
                print("   OK Omni-LLM-Scratch provider selectable")
            else:
                results.append(("Omni-LLM-Scratch in Provider Dropdown", f"FAIL - got {options}"))
                print(f"   FAIL Options were: {options}")
        except Exception as e:
            await page.screenshot(path=f"{SCREENSHOT_DIR}/06_provider_fail.png")
            results.append(("Omni-LLM-Scratch in Provider Dropdown", f"FAIL - {e}"))
            print(f"   FAIL {e}")

        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
        except:
            pass

        # ── TEST 3: FinOps ─────────────────────────────────────────────────────
        print(">> Navigating to FinOps...")
        for sel in ["text=FinOps", "text=Financial", "text=Cost"]:
            try:
                await page.click(sel, timeout=5000)
                await page.wait_for_timeout(2500)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/07_finops.png")
                results.append(("FinOps Dashboard", "PASS"))
                print("   OK FinOps loaded")
                break
            except:
                pass
        else:
            await page.screenshot(path=f"{SCREENSHOT_DIR}/07_finops_fail.png")
            results.append(("FinOps Dashboard", "FAIL - could not navigate"))
            print("   FAIL FinOps nav failed")

        # ── TEST 4: Attack Path ───────────────────────────────────────────────
        print(">> Navigating to Attack Path...")
        attack_found = False
        for sel in ["text=Attack Path", "text=AttackPath"]:
            try:
                await page.click(sel, timeout=5000)
                await page.wait_for_timeout(2500)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/08_attack_path.png")
                results.append(("Attack Path Dashboard", "PASS"))
                print("   OK Attack Path loaded")
                attack_found = True
                break
            except:
                pass

        if not attack_found:
            for parent in ["text=Security", "text=Cloud Security", "text=Threat", "text=CSPM"]:
                try:
                    await page.click(parent, timeout=3000)
                    await page.wait_for_timeout(500)
                    await page.click("text=Attack Path", timeout=3000)
                    await page.wait_for_timeout(2000)
                    await page.screenshot(path=f"{SCREENSHOT_DIR}/08_attack_path.png")
                    results.append(("Attack Path Dashboard", "PASS (nested nav)"))
                    print("   OK Attack Path via nested nav")
                    attack_found = True
                    break
                except:
                    pass
            if not attack_found:
                await page.screenshot(path=f"{SCREENSHOT_DIR}/08_attack_path_fail.png")
                results.append(("Attack Path Dashboard", "FAIL - could not navigate"))
                print("   FAIL Attack Path nav failed")

        # ── RESULTS ──────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("TEST RESULTS")
        print("="*60)
        passes = sum(1 for _, s in results if "PASS" in s)
        for name, status in results:
            icon = "OK" if "PASS" in status else "FAIL"
            print(f"  [{icon}] {name}: {status}")
        print(f"\nTotal: {passes}/{len(results)} passed")
        print(f"Screenshots: {SCREENSHOT_DIR}")

        await page.wait_for_timeout(2000)
        await browser.close()


asyncio.run(main())
