from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright
from modules.job_scraper import scrape_linkedin
import json, os, time

COOKIES_FILE = "data/linkedin_session.json"

jobs = scrape_linkedin("UI/UX Designer", "Lahore")
print(f"Jobs: {len(jobs)}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
    )
    page = context.new_page()

    # Load cookies
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE) as f:
            context.add_cookies(json.load(f))

    # Go directly to a job
    url = jobs[0]["url"].replace("pk.linkedin.com", "www.linkedin.com")
    print(f"Opening: {jobs[0]['title']} @ {jobs[0]['company']}")
    print(f"URL: {url}")
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    time.sleep(6)
    try: page.wait_for_load_state("networkidle", timeout=6000)
    except: pass

    # Screenshot
    page.screenshot(path="debug_job.png", full_page=False)
    print("Screenshot saved: debug_job.png")

    # Print ALL visible buttons
    print("\nALL visible buttons:")
    for b in page.locator("button").all():
        try:
            if b.is_visible():
                txt  = b.inner_text().strip()[:40]
                aria = (b.get_attribute("aria-label") or "")[:50]
                if txt or aria:
                    print(f"  text='{txt}' aria='{aria}'")
        except: pass

    time.sleep(3)
    browser.close()
