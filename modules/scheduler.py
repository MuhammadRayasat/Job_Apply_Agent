"""
Auto Scheduler Module — APScheduler
Runs automatically in background:
- Every 6 hours: scrape new jobs for ALL users
- Every 6 hours: AI match + auto apply for ALL users
- Every day at 8 PM: send daily summary email
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz

_scheduler = None


def get_scheduler():
    global _scheduler
    return _scheduler


def start_scheduler(app):
    """Initialize and start the background scheduler."""
    global _scheduler

    _scheduler = BackgroundScheduler(timezone=pytz.utc)

    # Job 1: Scrape + Match + Apply — every 15 minutes
    _scheduler.add_job(
        func=lambda: _run_auto_cycle(app),
        trigger=IntervalTrigger(minutes=15),
        id="auto_cycle",
        name="Auto Scrape + Match + Apply",
        replace_existing=True,
        misfire_grace_time=60
    )

    # Job 2: Daily summary email — every day at 8 PM PKT (3 PM UTC)
    _scheduler.add_job(
        func=lambda: _send_daily_summaries(app),
        trigger=CronTrigger(hour=15, minute=0),
        id="daily_summary",
        name="Daily Summary Emails",
        replace_existing=True,
        misfire_grace_time=300
    )

    _scheduler.start()
    print(f"[Scheduler] Started. Next auto-cycle: {_get_next_run()}")
    return _scheduler


def _get_next_run():
    """Return next scheduled run time as string."""
    global _scheduler
    if _scheduler:
        job = _scheduler.get_job("auto_cycle")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%d %b %Y, %I:%M %p UTC")
    return "N/A"


def get_scheduler_status() -> dict:
    """Return scheduler status for dashboard display."""
    global _scheduler
    if not _scheduler or not _scheduler.running:
        return {"running": False, "next_run": "N/A", "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "name":     job.name,
            "next_run": job.next_run_time.strftime("%d %b %Y, %I:%M %p UTC") if job.next_run_time else "N/A"
        })

    return {
        "running":  True,
        "next_run": _get_next_run(),
        "jobs":     jobs
    }


# ---------------------------------------------------------------------------
# Core auto cycle — runs for ALL active users
# ---------------------------------------------------------------------------

def _run_auto_cycle(app):
    """Main automation: scrape jobs → AI match → auto apply → notify."""
    print(f"\n[Scheduler] Auto cycle started at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    with app.app_context():
        try:
            from modules.database    import get_db
            from modules.job_scraper import scrape_all_jobs
            from modules.ai_matcher  import match_jobs_with_cv
            from modules.auto_apply  import bulk_apply
            from modules.email_notify import notify_job_applied, notify_new_matches
            import os

            db = get_db()

            # Get all active users who have CV + API key + job titles
            users = db.execute("""
                SELECT * FROM users
                WHERE is_active = 1
                  AND gemini_api_key IS NOT NULL
                  AND cv_text IS NOT NULL
                  AND job_titles IS NOT NULL
            """).fetchall()

            print(f"[Scheduler] Processing {len(users)} active users...")

            for user in users:
                user = dict(user)
                print(f"[Scheduler] User: {user['name']} ({user['email']})")

                try:
                    # Step 1: Scrape new jobs
                    new_jobs = scrape_all_jobs(
                        user["job_titles"],
                        user.get("location", "") or ""
                    )

                    # Save new jobs to DB
                    saved_count = 0
                    for job in new_jobs:
                        existing = db.execute(
                            "SELECT id FROM jobs WHERE url = ?", (job["url"],)
                        ).fetchone()
                        if not existing and job["url"]:
                            db.execute(
                                "INSERT INTO jobs (title, company, location, description, url, source, scraped_at) "
                                "VALUES (?,?,?,?,?,?,?)",
                                (job["title"], job["company"], job["location"],
                                 job["description"], job["url"], job["source"],
                                 datetime.utcnow().isoformat())
                            )
                            saved_count += 1
                    db.commit()
                    print(f"  Saved {saved_count} new jobs")

                    # Step 2: Get all unprocessed jobs for this user
                    unprocessed = db.execute("""
                        SELECT j.* FROM jobs j
                        WHERE j.id NOT IN (
                            SELECT job_id FROM applications WHERE user_id = ?
                        )
                        ORDER BY j.scraped_at DESC
                        LIMIT 50
                    """, (user["id"],)).fetchall()

                    if not unprocessed:
                        print("  No new jobs to process")
                        continue

                    print(f"  AI matching {len(unprocessed)} jobs...")

                    # Step 3: AI match
                    matched = match_jobs_with_cv(
                        cv_text=user["cv_text"],
                        jobs=[dict(j) for j in unprocessed],
                        api_key=user["gemini_api_key"],
                        job_titles=user["job_titles"]
                    )

                    if not matched:
                        print("  No matches above threshold")
                        continue

                    print(f"  {len(matched)} jobs matched!")

                    # Notify new matches
                    if user.get("notify_email"):
                        notify_new_matches(user["name"], user["notify_email"], matched)

                    # Save pending applications + build bulk list
                    upload_folder = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)), "uploads", "cvs"
                    )
                    cv_path = os.path.join(upload_folder, user["cv_filename"]) \
                              if user.get("cv_filename") else ""

                    bulk_jobs = []
                    for job in matched:
                        try:
                            db.execute(
                                "INSERT OR IGNORE INTO applications "
                                "(user_id,job_id,status,match_score,cover_letter,applied_at) "
                                "VALUES (?,?,?,?,?,?)",
                                (user["id"], job["id"], "pending",
                                 job["match_score"], job.get("cover_letter",""),
                                 datetime.utcnow().isoformat())
                            )
                            db.commit()
                            app_row = db.execute(
                                "SELECT id FROM applications WHERE user_id=? AND job_id=?",
                                (user["id"], job["id"])
                            ).fetchone()
                            if app_row:
                                bulk_jobs.append({
                                    "id":           app_row["id"],
                                    "url":          job.get("url",""),
                                    "cover_letter": job.get("cover_letter",""),
                                    "title":        job.get("title",""),
                                    "company":      job.get("company",""),
                                })
                        except Exception as e:
                            print(f"  Error saving: {e}")

                    # One browser — apply to all matched jobs
                    if bulk_jobs:
                        results = bulk_apply(bulk_jobs, cv_path, user)
                        applied_count = 0
                        for r in results:
                            status = "applied" if r["success"] else "failed"
                            db.execute(
                                "UPDATE applications SET status=?, apply_note=? WHERE id=?",
                                (status, r["message"], r["id"])
                            )
                            if r["success"]:
                                applied_count += 1
                                if user.get("notify_email"):
                                    matched_job = next(
                                        (j for j in matched
                                         if bulk_jobs[results.index(r)]["url"] == j.get("url","")),
                                        {}
                                    )
                                    notify_job_applied(user["name"], user["notify_email"], matched_job)
                        db.commit()
                        print(f"  Done. Applied: {applied_count}/{len(bulk_jobs)}")

                except Exception as e:
                    print(f"[Scheduler] Error for user {user['name']}: {e}")
                    continue

        except Exception as e:
            print(f"[Scheduler] Critical error: {e}")

    print(f"[Scheduler] Cycle complete at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")


def _send_daily_summaries(app):
    """Send daily summary emails to all active users."""
    print(f"[Scheduler] Sending daily summaries...")

    with app.app_context():
        try:
            from modules.database     import get_db
            from modules.email_notify import notify_daily_summary
            from datetime import date

            db    = get_db()
            today = date.today().isoformat()

            users = db.execute(
                "SELECT * FROM users WHERE is_active=1 AND email IS NOT NULL"
            ).fetchall()

            for user in users:
                user = dict(user)
                try:
                    applied_today = db.execute(
                        "SELECT COUNT(*) FROM applications WHERE user_id=? AND applied_at LIKE ?",
                        (user["id"], f"{today}%")
                    ).fetchone()[0]

                    total_applied = db.execute(
                        "SELECT COUNT(*) FROM applications WHERE user_id=? AND status='applied'",
                        (user["id"],)
                    ).fetchone()[0]

                    new_jobs = db.execute(
                        "SELECT COUNT(*) FROM jobs WHERE scraped_at LIKE ?",
                        (f"{today}%",)
                    ).fetchone()[0]

                    notify_daily_summary(
                        user["name"], user["email"],
                        {
                            "applied_today": applied_today,
                            "total_applied": total_applied,
                            "new_jobs":      new_jobs
                        }
                    )
                except Exception as e:
                    print(f"  Summary error for {user.get('email')}: {e}")

        except Exception as e:
            print(f"[Scheduler] Daily summary error: {e}")
