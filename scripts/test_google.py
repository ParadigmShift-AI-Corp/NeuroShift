from playwright.sync_api import sync_playwright # type: ignore

def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox"]
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            # Open Google and search for Netflix
            page.goto("https://www.google.com")
            page.locator("input[name='q']").fill("Netflix")
            page.locator("input[name='btnK']").click()
            page.wait_for_selector("text=Netflix - Watch TV Shows Online")
            page.screenshot(path="/home/ubuntu/google_search.png")
            print("Search completed and screenshot saved!")

        except Exception as e:
            print(f"Error during test execution: {e}")

        finally:
            browser.close()

if __name__ == "__main__":
    run_test()
