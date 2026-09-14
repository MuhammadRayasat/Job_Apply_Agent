"""
Job Scraper Module
Scrapes jobs from:
- Indeed (RSS feed)
- Rozee.pk (RSS feed)
- LinkedIn (RSS feed)
- Mustakbil.com (RSS feed)
- SimplyHired (RSS feed)
"""

import feedparser
import requests
from bs4 import BeautifulSoup
import time
import re
from urllib.parse import quote_plus


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Individual Scrapers
# ---------------------------------------------------------------------------

def scrape_indeed(job_titles: str, location: str = "") -> list:
    """Scrape Indeed via direct HTML (RSS blocked)."""
    jobs = []
    titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    for title in titles:
        try:
            query = quote_plus(title)
            loc   = quote_plus(location) if location else ""
            url   = f"https://www.indeed.com/jobs?q={query}&l={loc}&sort=date&fromage=7"

            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")

            for card in soup.find_all("div", class_="job_seen_beacon")[:10]:
                title_tag   = card.find("h2", class_="jobTitle")
                company_tag = card.find("span", {"data-testid": "company-name"})
                loc_tag     = card.find("div",  {"data-testid": "text-location"})
                link_tag    = card.find("a",    class_="jcs-JobTitle")

                job_url = ""
                if link_tag and link_tag.get("href"):
                    href = link_tag["href"]
                    job_url = f"https://www.indeed.com{href}" if href.startswith("/") else href

                jobs.append({
                    "title":       title_tag.get_text(strip=True)   if title_tag   else "N/A",
                    "company":     company_tag.get_text(strip=True) if company_tag else "N/A",
                    "location":    loc_tag.get_text(strip=True)     if loc_tag     else location or "N/A",
                    "description": "",
                    "url":         job_url,
                    "source":      "Indeed"
                })
            time.sleep(2)
        except Exception as e:
            print(f"[Indeed Scraper] Error for '{title}': {e}")

    return jobs


def scrape_rozee(job_titles: str, location: str = "") -> list:
    """Scrape Rozee.pk via Playwright (site is JavaScript-heavy)."""
    jobs = []
    titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    for title in titles:
        try:
            from playwright.sync_api import sync_playwright
            query = title.replace(" ", "+")
            url   = f"https://www.rozee.pk/job/jsearch/q/{query}"

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page    = browser.new_page()
                page.goto(url, timeout=40000)
                page.wait_for_timeout(4000)  # Wait for JS to load jobs

                cards = page.query_selector_all(".job-listing, .jlisting, [class*='job-post'], .ajob")
                for card in cards[:10]:
                    title_el   = card.query_selector("h3, h2, .jobtitle, [class*='title']")
                    company_el = card.query_selector("[class*='company'], [class*='employer']")
                    link_el    = card.query_selector("a")

                    job_title   = title_el.inner_text().strip()   if title_el   else "N/A"
                    company     = company_el.inner_text().strip()  if company_el else "N/A"
                    href        = link_el.get_attribute("href")    if link_el    else ""
                    job_url     = f"https://www.rozee.pk{href}" if href and href.startswith("/") else href or ""

                    if job_title != "N/A":
                        jobs.append({
                            "title":       job_title,
                            "company":     company,
                            "location":    location or "Pakistan",
                            "description": "",
                            "url":         job_url,
                            "source":      "Rozee.pk"
                        })
                browser.close()
        except Exception as e:
            print(f"[Rozee Scraper] Error for '{title}': {e}")

    return jobs


def scrape_remoteok(job_titles: str) -> list:
    """Scrape RemoteOK via JSON API — reliable and free."""
    jobs = []
    titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    try:
        resp = requests.get(
            "https://remoteok.com/api",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15
        )
        if resp.status_code != 200:
            return jobs

        data = resp.json()
        # First item is a legal notice, skip it
        postings = [d for d in data if isinstance(d, dict) and d.get("position")]

        for title in titles:
            kw_words = title.lower().split()
            for post in postings:
                position = post.get("position", "").lower()
                tags     = " ".join(post.get("tags", [])).lower()
                combined = position + " " + tags
                # Match if ANY keyword word found
                if any(word in combined for word in kw_words):
                    jobs.append({
                        "title":       post.get("position", "N/A"),
                        "company":     post.get("company", "N/A"),
                        "location":    post.get("location", "Remote") or "Remote",
                        "description": BeautifulSoup(post.get("description", ""), "html.parser").get_text()[:500],
                        "url":         post.get("url", "") or f"https://remoteok.com/remote-jobs/{post.get('id','')}",
                        "source":      "RemoteOK"
                    })
                    if len(jobs) >= 10:
                        break

        time.sleep(1)
    except Exception as e:
        print(f"[RemoteOK Scraper] Error: {e}")

    return jobs


def scrape_linkedin(job_titles: str, location: str = "") -> list:
    """Scrape LinkedIn Jobs — Easy Apply only (f_AL=true filter)."""
    jobs = []
    titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    for title in titles:
        try:
            query = quote_plus(title)
            loc   = quote_plus(location) if location else ""

            # f_AL=true = Easy Apply only
            url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={query}&location={loc}&f_AL=true&start=0"
            )

            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            for card in soup.find_all("div", class_="base-card")[:15]:
                title_tag   = card.find("h3", class_="base-search-card__title")
                company_tag = card.find("h4", class_="base-search-card__subtitle")
                loc_tag     = card.find("span", class_="job-search-card__location")
                link_tag    = card.find("a", class_="base-card__full-link")

                job_url = ""
                if link_tag and link_tag.get("href"):
                    job_url = link_tag["href"].split("?")[0]  # clean URL

                if title_tag and title_tag.get_text(strip=True):
                    jobs.append({
                        "title":       title_tag.get_text(strip=True),
                        "company":     company_tag.get_text(strip=True) if company_tag else "N/A",
                        "location":    loc_tag.get_text(strip=True)     if loc_tag     else location or "N/A",
                        "description": "",
                        "url":         job_url,
                        "source":      "LinkedIn",
                        "easy_apply":  True
                    })
            time.sleep(2)

        except Exception as e:
            print(f"[LinkedIn Scraper] Error for '{title}': {e}")

    return jobs


def scrape_mustakbil(job_titles: str, location: str = "") -> list:
    """Scrape Mustakbil.com RSS feed."""
    jobs = []
    titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    for title in titles:
        try:
            query = quote_plus(title)
            url   = f"https://www.mustakbil.com/jobs/rss/?q={query}"

            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                jobs.append({
                    "title":       entry.get("title", "N/A"),
                    "company":     entry.get("author", "N/A"),
                    "location":    location or "Pakistan",
                    "description": _clean_html(entry.get("summary", "")),
                    "url":         entry.get("link", ""),
                    "source":      "Mustakbil"
                })
            time.sleep(1)
        except Exception as e:
            print(f"[Mustakbil Scraper] Error for '{title}': {e}")

    return jobs


def scrape_simplyhired(job_titles: str, location: str = "") -> list:
    """Scrape SimplyHired RSS feed."""
    jobs = []
    titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    for title in titles:
        try:
            query = quote_plus(title)
            loc   = quote_plus(location) if location else ""
            url   = f"https://www.simplyhired.com/search?q={query}&l={loc}&job-types=&sb=dd&pn=1&fdb=5&rss=1"

            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                jobs.append({
                    "title":       entry.get("title", "N/A"),
                    "company":     entry.get("author", "N/A"),
                    "location":    location or "N/A",
                    "description": _clean_html(entry.get("summary", "")),
                    "url":         entry.get("link", ""),
                    "source":      "SimplyHired"
                })
            time.sleep(1)
        except Exception as e:
            print(f"[SimplyHired Scraper] Error for '{title}': {e}")

    return jobs


# ---------------------------------------------------------------------------
# Master scraper — calls all sources
# ---------------------------------------------------------------------------

def scrape_all_jobs(job_titles: str, location: str = "") -> list:
    """Run all scrapers and return combined deduplicated list."""
    print(f"[Scraper] Starting scrape for: {job_titles} | Location: {location}")

    all_jobs = []
    all_jobs += scrape_indeed(job_titles, location)
    all_jobs += scrape_rozee(job_titles, location)
    all_jobs += scrape_linkedin(job_titles, location)
    all_jobs += scrape_mustakbil(job_titles, location)
    all_jobs += scrape_simplyhired(job_titles, location)
    all_jobs += scrape_remoteok(job_titles)

    # Deduplicate by URL
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        if job["url"] and job["url"] not in seen:
            seen.add(job["url"])
            unique_jobs.append(job)

    print(f"[Scraper] Total unique jobs found: {len(unique_jobs)}")
    return unique_jobs


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    """Remove HTML tags and clean up text."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=" ")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:2000]  # Limit to 2000 chars for DB
