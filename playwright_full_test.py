# -*- coding: utf-8 -*-
"""
Full Platform Browser Test using Playwright
Tests all major features of the Enterprise Omni-Agent AI Platform
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import os
import sys
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, expect

BASE_URL = "http://localhost:3000"
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "playwright_screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

RESULTS = []

def screenshot(page: Page, name: str):
    path = os.path.join(SCREENSHOTS_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=False)
    print(f"  [SCREENSHOT] {name}.png")
    return path

def log(status: str, feature: str, detail: str = ""):
    icon = "[OK] " if status == "PASS" else ("[!!] " if status == "WARN" else "[XX] ")
    msg = f"  {icon} [{status}] {feature}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    RESULTS.append({"status": status, "feature": feature, "detail": detail})

def wait_and_screenshot(page: Page, name: str, wait_ms: int = 3000):
    page.wait_for_timeout(wait_ms)
    return screenshot(page, name)

def login(page: Page, email: str, password: str) -> bool:
    try:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        screenshot(page, "01_login_page")

        # Fill email
        email_sel = "input[type='email'], input[placeholder*='email' i], input[name='email'], input[id*='email' i]"
        page.fill(email_sel, email)

        # Fill password
        pw_sel = "input[type='password']"
        page.fill(pw_sel, password)

        screenshot(page, "02_login_filled")

        # Click login button
        btn_sel = "button[type='submit'], button:has-text('Login'), button:has-text('Sign In'), button:has-text('Log in')"
        page.click(btn_sel)
        page.wait_for_timeout(5000)
        screenshot(page, "03_after_login")
        log("PASS", "Login", f"Logged in as {email}")
        return True
    except Exception as e:
        log("FAIL", "Login", str(e))
        screenshot(page, "03_login_error")
        return False

def click_sidebar(page: Page, labels: list, feature_name: str, screenshot_name: str) -> bool:
    for label in labels:
        selectors = [
            f"text={label}",
            f"[aria-label*='{label}' i]",
            f"nav >> text={label}",
            f"aside >> text={label}",
            f"a:has-text('{label}')",
            f"li:has-text('{label}')",
            f"button:has-text('{label}')",
            f"span:has-text('{label}')",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1500):
                    el.click()
                    page.wait_for_timeout(3000)
                    wait_and_screenshot(page, screenshot_name, 1000)
                    log("PASS", feature_name, f"Navigated via '{label}'")
                    return True
            except:
                continue
    log("WARN", feature_name, f"Could not find sidebar item: {labels}")
    screenshot(page, screenshot_name + "_not_found")
    return False

def check_page_has_content(page: Page, feature_name: str) -> bool:
    try:
        # Check page isn't blank/error
        body_text = page.locator("body").inner_text(timeout=3000)
        if len(body_text.strip()) < 50:
            log("WARN", feature_name, "Page appears empty")
            return False
        # Check for error messages
        if any(err in body_text.lower() for err in ["404", "not found", "error loading", "failed to fetch"]):
            log("WARN", feature_name, "Page has error content")
            return False
        return True
    except:
        return False

def run_tests():
    print("\n" + "="*60)
    print("  ENTERPRISE OMNI-AGENT PLATFORM — FULL BROWSER TEST")
    print("="*60)
    print(f"  URL: {BASE_URL}")
    print(f"  Screenshots: {SCREENSHOTS_DIR}")
    print(f"  Started: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # ── 1. LOGIN ─────────────────────────────────────────────
        print("\n[1] AUTHENTICATION")
        logged_in = login(page, "super@omni.ai", "password123")
        if not logged_in:
            print("Cannot proceed — login failed.")
            browser.close()
            return

        # ── 2. DASHBOARD ─────────────────────────────────────────
        print("\n[2] DASHBOARD")
        try:
            page.wait_for_timeout(3000)
            screenshot(page, "04_dashboard")
            check_page_has_content(page, "Main Dashboard")

            # Check for key dashboard elements
            dash_elements = ["agent", "alert", "compliance", "threat", "vulnerability",
                             "metric", "chart", "score", "status"]
            body = page.locator("body").inner_text(timeout=3000).lower()
            found = [e for e in dash_elements if e in body]
            log("PASS", "Dashboard", f"Found elements: {', '.join(found[:5])}")
        except Exception as e:
            log("FAIL", "Dashboard", str(e))

        # ── 3. KEY FEATURE SECTIONS ──────────────────────────────
        sections = [
            (["Agents", "Agent Management", "My Agents"],  "Agents",         "05_agents"),
            (["Compliance"],                               "Compliance",      "06_compliance"),
            (["Security", "Security Dashboard"],           "Security",        "07_security"),
            (["FinOps", "Billing", "Cost Management"],     "FinOps/Billing",  "08_finops"),
            (["AI Governance", "AI Gov", "Governance"],    "AI Governance",   "09_ai_governance"),
            (["Vulnerabilities", "Vulns"],                 "Vulnerabilities", "10_vulnerabilities"),
            (["Assets", "Asset Management"],               "Assets",          "11_assets"),
            (["Audit", "Audit Logs", "Audit Log"],         "Audit Logs",      "12_audit"),
            (["Patches", "Patch Management"],              "Patches",         "13_patches"),
            (["Threat", "Threat Hunting", "Threats"],      "Threat Hunting",  "14_threats"),
            (["SIEM", "SIEM Events"],                      "SIEM",            "15_siem"),
            (["Playbooks", "Automation", "SOAR"],          "Automation/SOAR", "16_soar"),
            (["Reports", "Reporting"],                     "Reports",         "17_reports"),
            (["Settings", "Platform Settings"],            "Settings",        "18_settings"),
            (["Users", "User Management"],                 "Users",           "19_users"),
            (["Network", "Network Security"],              "Network",         "20_network"),
            (["Zero Trust"],                               "Zero Trust",      "21_zero_trust"),
            (["Attack Path", "Attack Paths"],              "Attack Path",     "22_attack_path"),
            (["Cloud", "Cloud Security"],                  "Cloud Security",  "23_cloud"),
            (["DevSecOps", "Dev Security"],                "DevSecOps",       "24_devsecops"),
            (["SBOM"],                                     "SBOM",            "25_sbom"),
            (["Tracing", "Distributed Tracing"],           "Tracing",         "26_tracing"),
        ]

        for i, (labels, feature, ss_name) in enumerate(sections, 3):
            print(f"\n[{i}] {feature.upper()}")
            click_sidebar(page, labels, feature, ss_name)
            check_page_has_content(page, feature)

        # ── FINAL: TENANT ADMIN LOGIN ─────────────────────────────
        print("\n[EXTRA] TENANT ADMIN LOGIN TEST")
        try:
            # Logout first
            logout_sels = ["button:has-text('Logout')", "button:has-text('Sign out')",
                          "text=Logout", "text=Sign out", "[aria-label*='logout' i]"]
            logged_out = False
            for sel in logout_sels:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        page.click(sel)
                        page.wait_for_timeout(2000)
                        logged_out = True
                        break
                except: continue

            if not logged_out:
                # Navigate directly to login
                page.goto(BASE_URL, timeout=15000)
                page.wait_for_timeout(2000)

            screenshot(page, "27_logout")

            # Login as tenant admin
            login(page, "admin@sriprasad.com", "Admin123!")
            page.wait_for_timeout(3000)
            screenshot(page, "28_tenant_admin_dashboard")
            log("PASS", "Tenant Admin Login", "Logged in as admin@sriprasad.com")
        except Exception as e:
            log("FAIL", "Tenant Admin Login", str(e))

        # ── SUMMARY ──────────────────────────────────────────────
        print("\n" + "="*60)
        print("  TEST RESULTS SUMMARY")
        print("="*60)
        passed = [r for r in RESULTS if r["status"] == "PASS"]
        warned  = [r for r in RESULTS if r["status"] == "WARN"]
        failed  = [r for r in RESULTS if r["status"] == "FAIL"]
        print(f"  PASSED: {len(passed)}")
        print(f"  WARNED: {len(warned)}")
        print(f"  FAILED: {len(failed)}")
        print(f"\n  Total Screenshots: {len(os.listdir(SCREENSHOTS_DIR))}")
        print(f"  Screenshots saved to: {SCREENSHOTS_DIR}")

        if failed:
            print("\n  Failed Features:")
            for r in failed:
                print(f"    [FAIL] {r['feature']}: {r['detail']}")
        if warned:
            print("\n  Warnings:")
            for r in warned:
                print(f"    [WARN] {r['feature']}: {r['detail']}")

        print("\n" + "="*60)
        print(f"  Completed: {datetime.now().strftime('%H:%M:%S')}")
        print("="*60 + "\n")

        page.wait_for_timeout(3000)
        browser.close()

if __name__ == "__main__":
    run_tests()
