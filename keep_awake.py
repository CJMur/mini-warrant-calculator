from playwright.sync_api import sync_playwright

# --- MINI WARRANT APP URL ---
APP_URL = "https://mini-warrant-calculator-tc.streamlit.app/"

def ping_streamlit():
    print(f"Spinning up Headless Chrome to visit {APP_URL}...")
    with sync_playwright() as p:
        # Launch Chrome invisibly
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 1. Go to the app
        page.goto(APP_URL)
        
        try:
            # 2. Wait for the main title to prove the JavaScript rendered
            page.wait_for_selector("text=MINI Warrant Search", timeout=15000)
            print("App loaded successfully. Simulating human interaction...")
            
            # 3. Physically click the title to trigger a generic interaction
            page.click("text=MINI Warrant Search", timeout=5000)
            print("Simulated human click. 12-hour sleep timer reset.")
            
            # 4. Wait 5 seconds to ensure the server registers the connection
            page.wait_for_timeout(5000) 
            
        except Exception as e:
            print(f"Interaction failed, but site was visited: {e}")
            
        browser.close()

if __name__ == "__main__":
    ping_streamlit()
