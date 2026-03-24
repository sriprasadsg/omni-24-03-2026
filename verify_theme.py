import sys
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def verify_theme_toggle():
    print("Starting Theme Toggle Verification...")
    
    # Configure Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # 1. Login
        print("Navigating to Login...")
        driver.get("http://localhost:3000")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "email")))
        
        driver.find_element(By.ID, "email").send_keys("super@omni.ai")
        driver.find_element(By.ID, "password").send_keys("password123") 
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        
        # Wait for Dashboard to load first
        print("Waiting for Dashboard...")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//h2[contains(text(), 'Welcome')]")))
        
        # 3. Capture Dark Mode (Default)
        print("Capturing Dark Mode Dashboard...")
        driver.save_screenshot("verify_dark_mode.png")
        
        # 4. Force Light Mode via JS
        print("Forcing Light Mode via JS...")
        driver.execute_script("document.documentElement.classList.remove('dark');")
        time.sleep(1)
        
        # 5. Capture Light Mode
        print("Capturing Light Mode Dashboard...")
        driver.save_screenshot("verify_light_mode.png")
        
        print("Verification Complete!")
        
    except Exception as e:
        print(f"Verification Failed: {e}")
        driver.save_screenshot("verify_error.png")
    finally:
        driver.quit()

if __name__ == "__main__":
    verify_theme_toggle()
