"""
One browser, all jobs — bulk_apply test.
"""
from dotenv import load_dotenv
load_dotenv()

from modules.database import init_db, get_db
from modules.job_scraper import scrape_linkedin
from modules.auto_apply import bulk_apply
import os

init_db()
db   = get_db()
user = dict(db.execute("SELECT * FROM users WHERE email='safwanshafiq123@gmail.com'").fetchone())
cv_path = os.path.join("uploads", "cvs", user["cv_filename"]) if user.get("cv_filename") else ""

print("Scraping Easy Apply jobs...")
jobs = scrape_linkedin("UI/UX Designer, Web Developer", "Lahore")
print(f"Found: {len(jobs)} Easy Apply jobs")

# Build job list for bulk_apply
bulk_jobs = [
    {
        "id":           i + 1,
        "url":          j["url"],
        "cover_letter": "I am excited about this opportunity. My UI/UX and web development skills make me a great fit.",
        "title":        j["title"],
        "company":      j["company"],
    }
    for i, j in enumerate(jobs[:10])
]

print(f"\nRunning bulk_apply on {len(bulk_jobs)} jobs (ONE browser)...")
results = bulk_apply(bulk_jobs, cv_path, user)

print(f"\n{'='*55}")
applied = sum(1 for r in results if r["success"])
print(f"Applied: {applied}/{len(results)}")
for r in results:
    icon = "✅" if r["success"] else "❌"
    job  = next((j for j in bulk_jobs if j["id"] == r["id"]), {})
    print(f"  {icon} {job.get('title','?')} @ {job.get('company','?')}")
    print(f"     {r['message'][:80]}")
