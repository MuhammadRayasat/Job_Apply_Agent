"""
Auto Apply Module — Playwright
One browser session for ALL jobs.
Login once → apply to all → close.
"""

import os
import time
import random
import json

COOKIES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "linkedin_session.json"
)

# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def auto_apply_job(job_url: str, cv_path: str, cover_letter: str, user_info: dict) -> dict:
    """Apply to a single job. Each call opens/closes its own browser."""
    if not job_url:
        return {"success": False, "message": "Job URL missing."}
    if "linkedin.com" in job_url:
        return _apply_linkedin(job_url, cv_path, cover_letter, user_info)
    return {"success": False, "message": "Platform supported nahi — manual apply karo."}


def bulk_apply(jobs: list, cv_path: str, user_info: dict) -> list:
    """
    Apply to multiple jobs in ONE browser session.
    jobs = [{"url":..., "cover_letter":..., "id":...}, ...]
    Returns list of {"id", "success", "message"}
    """
    if not jobs:
        return []

    li_email    = user_info.get("linkedin_email", "")
    li_password = user_info.get("linkedin_password", "")
    if not li_email or not li_password:
        return [{"id": j.get("id"), "success": False,
                 "message": "LinkedIn credentials missing."} for j in jobs]

    results = []

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
            )
            page = context.new_page()

            # ── Login once ────────────────────────────────────────────────
            if not _login(page, context, li_email, li_password):
                browser.close()
                return [{"id": j.get("id"), "success": False,
                         "message": "LinkedIn login fail."} for j in jobs]

            # ── Apply to each job ─────────────────────────────────────────
            for job in jobs:
                url          = job.get("url", "")
                cover_letter = job.get("cover_letter", "")
                job_id       = job.get("id")

                if not url:
                    results.append({"id": job_id, "success": False, "message": "URL missing."})
                    continue

                result = _apply_one(page, url, cv_path, cover_letter, user_info)
                result["id"] = job_id
                results.append(result)
                print(f"[AutoApply] {'✅' if result['success'] else '❌'} "
                      f"{job.get('title','?')} @ {job.get('company','?')} — {result['message'][:60]}")
                _human_delay(2, 4)

            browser.close()

    except Exception as e:
        print(f"[AutoApply] Fatal error: {e}")
        for job in jobs:
            if not any(r.get("id") == job.get("id") for r in results):
                results.append({"id": job.get("id"), "success": False,
                                "message": f"Error: {str(e)[:80]}"})

    return results


def clear_session():
    """Force fresh login next time."""
    if os.path.exists(COOKIES_FILE):
        os.remove(COOKIES_FILE)
        print("[AutoApply] Session cleared.")


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _login(page, context, email: str, password: str) -> bool:
    """Login to LinkedIn. Returns True if successful."""

    # Try saved cookies first
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r") as f:
                context.add_cookies(json.load(f))
            page.goto("https://www.linkedin.com/feed/",
                      timeout=30000, wait_until="domcontentloaded")
            _human_delay(3, 4)
            # Real check: Sign in button should NOT be visible if logged in
            sign_in_visible = False
            try:
                sign_in_visible = page.locator("a.nav__button-secondary").first.is_visible()
            except Exception:
                pass
            if not sign_in_visible and "feed" in page.url.lower():
                print("[AutoApply] Saved session OK")
                return True
            else:
                print("[AutoApply] Session expired — fresh login")
                # Clear bad cookies
                if os.path.exists(COOKIES_FILE):
                    os.remove(COOKIES_FILE)
        except Exception:
            pass

    # Fresh login
    page.goto("https://www.linkedin.com/login",
              timeout=60000, wait_until="domcontentloaded")
    _human_delay(3, 4)

    # Dismiss any popup
    _dismiss_popup(page)

    # "Sign in with Email" button if present
    for sel in ["button:has-text('Sign in with Email')",
                "a:has-text('Sign in with Email')"]:
        try:
            b = page.locator(sel).first
            if b.count() > 0 and b.is_visible():
                b.click(); _human_delay(2, 3); break
        except Exception:
            pass

    # Fill credentials
    ei = next((i for i in page.locator("input[type='email']").all()    if i.is_visible()), None)
    pi = next((i for i in page.locator("input[type='password']").all() if i.is_visible()), None)
    if not ei or not pi:
        print("[AutoApply] Login fields not found")
        return False

    ei.click(); ei.fill(email);    _human_delay(0.8, 1.2)
    pi.click(); pi.fill(password); _human_delay(0.8, 1.2)
    page.keyboard.press("Enter")
    _human_delay(6, 8)

    if "checkpoint" in page.url:
        print("[AutoApply] Security checkpoint")
        return False

    title = page.title()
    if "Login" in title and "Feed" not in title and "feed" not in page.url:
        print("[AutoApply] Login failed")
        return False

    # Save cookies
    try:
        os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
        with open(COOKIES_FILE, "w") as f:
            json.dump(context.cookies(), f)
        print("[AutoApply] Session saved")
    except Exception:
        pass

    return True


def _apply_one(page, job_url: str, cv_path: str, cover_letter: str,
               user_info: dict) -> dict:
    """Apply to one job on an already-logged-in page."""
    try:
        clean_url = job_url.replace("pk.linkedin.com", "www.linkedin.com")
        page.goto(clean_url, timeout=60000, wait_until="domcontentloaded")
        _human_delay(4, 6)

        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

        # Dismiss popup that blocks the page (Sign in to see who you know)
        _dismiss_popup(page)
        _human_delay(1, 2)

        # Find Easy Apply button (only visible when logged in)
        ea_btn = _find_easy_apply(page)
        if not ea_btn:
            # Check if "Apply" button exists (means not Easy Apply — external form)
            apply_btn = page.locator("button:has-text('Apply')").first
            if apply_btn.count() > 0 and apply_btn.is_visible():
                return {"success": False, "message": "Easy Apply nahi — external form hai."}
            return {"success": False, "message": "Easy Apply button nahi mila."}

        ea_btn.click()
        _human_delay(3, 4)

        # Walk form steps
        for step in range(10):
            _human_delay(2, 2.5)

            _upload_cv(page, cv_path)
            _fill_inputs(page, user_info)
            _fill_textareas(page, cover_letter)
            _handle_radios(page)
            _handle_dropdowns(page)

            if _submit(page):
                return {"success": True, "message": "LinkedIn Easy Apply ho gaya!"}

            if not _click_next(page):
                break

        return {"success": False, "message": "Form complete nahi hua — manual: " + job_url}

    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)[:100]}"}


def _find_easy_apply(page):
    """Return Easy Apply button locator or None."""
    for sel in [
        "button:has-text('Easy Apply')",
        "button[aria-label*='Easy Apply']",
        "button[aria-label*='easy apply']",
    ]:
        try:
            b = page.locator(sel).first
            if b.count() > 0 and b.is_visible():
                return b
        except Exception:
            pass
    return None


def _dismiss_popup(page):
    """Close any modal/popup that may block the page."""
    for sel in ["button[aria-label='Dismiss']",
                "button[aria-label='Close']",
                "button.modal__dismiss"]:
        try:
            d = page.locator(sel).first
            if d.count() > 0 and d.is_visible():
                d.click(); _human_delay(1, 1.5); return
        except Exception:
            pass


def _upload_cv(page, cv_path: str):
    if not cv_path or not os.path.exists(cv_path):
        return
    upload_btn = page.locator("button:has-text('Upload resume')").first
    if upload_btn.count() > 0 and upload_btn.is_visible():
        try:
            with page.expect_file_chooser(timeout=5000) as fc:
                upload_btn.click()
            fc.value.set_files(cv_path)
            _human_delay(2, 3)
        except Exception:
            pass


def _fill_inputs(page, user_info: dict):
    phone    = user_info.get("phone_number", "").strip()
    salary   = user_info.get("expected_salary", "").strip()
    exp      = user_info.get("years_experience", "").strip()
    location = user_info.get("location", "").strip()
    name     = user_info.get("name", "").strip()

    for inp in page.locator(
        "input[type='text'], input[type='tel'], input[type='number']"
    ).all():
        try:
            if not inp.is_visible() or inp.input_value():
                continue
            lbl = (inp.get_attribute("aria-label") or
                   inp.get_attribute("placeholder") or "").lower()
            if any(x in lbl for x in ["phone", "mobile", "contact"]):
                inp.fill(phone or "+92300000000")
            elif any(x in lbl for x in ["city", "location", "address"]):
                inp.fill(location or "Lahore")
            elif any(x in lbl for x in ["year", "experience"]):
                inp.fill(exp or "1")
            elif any(x in lbl for x in ["first name"]):
                parts = name.split()
                inp.fill(parts[0] if parts else name)
            elif any(x in lbl for x in ["last name"]):
                parts = name.split()
                inp.fill(parts[-1] if len(parts) > 1 else name)
            elif any(x in lbl for x in ["name"]):
                inp.fill(name)
            elif any(x in lbl for x in ["salary", "expected", "ctc", "compensation"]):
                inp.fill(salary or "50000")
            _human_delay(0.2, 0.4)
        except Exception:
            continue


def _fill_textareas(page, cover_letter: str):
    for ta in page.locator("textarea").all():
        try:
            if ta.is_visible() and not ta.input_value():
                text = cover_letter or "I am excited about this opportunity."
                ta.fill(text[:1000])
                _human_delay(0.3, 0.5)
        except Exception:
            continue


def _handle_radios(page):
    for radio in page.locator("input[type='radio']").all():
        try:
            if radio.is_visible() and not radio.is_checked():
                radio.click(); _human_delay(0.2, 0.3); break
        except Exception:
            continue


def _handle_dropdowns(page):
    for sel_el in page.locator("select").all():
        try:
            if sel_el.is_visible():
                opts = sel_el.locator("option").all()
                if len(opts) > 1:
                    sel_el.select_option(index=1); _human_delay(0.2, 0.3)
        except Exception:
            continue


def _submit(page) -> bool:
    for sel in ["button[aria-label='Submit application']",
                "button:has-text('Submit application')"]:
        sub = page.locator(sel).first
        if sub.count() > 0 and sub.is_visible():
            sub.click(); _human_delay(3, 4); return True
    return False


def _click_next(page) -> bool:
    for sel in ["button[aria-label='Continue to next step']",
                "button[aria-label='Review your application']",
                "button:has-text('Next')",
                "button:has-text('Review')",
                "button:has-text('Continue')"]:
        b = page.locator(sel).first
        if b.count() > 0 and b.is_visible():
            b.click(); return True
    return False


# Legacy single-job wrapper using bulk_apply internally
def _apply_linkedin(job_url: str, cv_path: str, cover_letter: str,
                    user_info: dict) -> dict:
    results = bulk_apply(
        [{"url": job_url, "cover_letter": cover_letter, "id": 1}],
        cv_path, user_info
    )
    return results[0] if results else {"success": False, "message": "No result."}


def _human_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    time.sleep(random.uniform(min_sec, max_sec))
