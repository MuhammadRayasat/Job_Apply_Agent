from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

# Must be set BEFORE google/protobuf imports — fixes Python 3.14 compatibility
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import threading
import json
from datetime import datetime
from modules.database import init_db, get_db
from modules.cv_parser import parse_cv
from modules.job_scraper import scrape_all_jobs
from modules.ai_matcher import match_jobs_with_cv
from modules.auto_apply import auto_apply_job

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "job-agent-secret-2024")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads", "cvs")
ALLOWED_EXTENSIONS = {"pdf", "docx", "doc"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB max

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Pehle login karein.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Sab fields zaroori hain.", "danger")
            return render_template("register.html")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("Yeh email pehle se registered hai.", "danger")
            return render_template("register.html")

        hashed = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (name, email, password, created_at) VALUES (?, ?, ?, ?)",
            (name, email, hashed, datetime.now().isoformat())
        )
        db.commit()
        flash("Account ban gaya! Ab login karein.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db   = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not user or not check_password_hash(user["password"], password):
            flash("Email ya password galat hai.", "danger")
            return render_template("login.html")

        session["user_id"]   = user["id"]
        session["user_name"] = user["name"]
        flash(f"Welcome, {user['name']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logout ho gaye.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    db      = get_db()
    user    = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    apps    = db.execute(
        """SELECT a.id, a.status, a.match_score, a.applied_at, a.apply_note,
                  j.title, j.company, j.location, j.url, j.source
           FROM applications a
           JOIN jobs j ON a.job_id = j.id
           WHERE a.user_id = ?
           ORDER BY a.applied_at DESC LIMIT 20""",
        (session["user_id"],)
    ).fetchall()
    jobs    = db.execute(
        "SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT 50"
    ).fetchall()

    stats = {
        "total_applied":  db.execute("SELECT COUNT(*) FROM applications WHERE user_id = ?", (session["user_id"],)).fetchone()[0],
        "pending":        db.execute("SELECT COUNT(*) FROM applications WHERE user_id = ? AND status = 'pending'", (session["user_id"],)).fetchone()[0],
        "success":        db.execute("SELECT COUNT(*) FROM applications WHERE user_id = ? AND status = 'applied'", (session["user_id"],)).fetchone()[0],
        "total_jobs":     db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
    }

    from modules.scheduler import get_scheduler_status
    scheduler_status = get_scheduler_status()

    return render_template("dashboard.html", user=user, applications=apps, jobs=jobs,
                           stats=stats, scheduler=scheduler_status)


# ---------------------------------------------------------------------------
# Setup — CV + API Key
# ---------------------------------------------------------------------------

@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        action = request.form.get("action")

        # Save API key
        if action == "save_api":
            api_key      = request.form.get("gemini_api_key", "").strip()
            job_titles   = request.form.get("job_titles", "").strip()
            location     = request.form.get("location", "").strip()
            notify_email = request.form.get("notify_email", "").strip().lower()
            auto_apply   = 1 if request.form.get("auto_apply") else 0

            db.execute(
                "UPDATE users SET gemini_api_key=?, job_titles=?, location=?, notify_email=?, auto_apply=? WHERE id=?",
                (api_key, job_titles, location, notify_email, auto_apply, session["user_id"])
            )
            db.commit()
            flash("Settings save ho gayi!", "success")

        # Save LinkedIn credentials
        elif action == "save_linkedin":
            li_email    = request.form.get("linkedin_email", "").strip().lower()
            li_password = request.form.get("linkedin_password", "")
            db.execute(
                "UPDATE users SET linkedin_email=?, linkedin_password=? WHERE id=?",
                (li_email, li_password, session["user_id"])
            )
            db.commit()
            flash("LinkedIn credentials save ho gaye!", "success")

        # Upload CV
        elif action == "upload_cv":
            if "cv_file" not in request.files:
                flash("Koi file select nahi ki.", "danger")
                return redirect(url_for("setup"))

            file = request.files["cv_file"]
            if file.filename == "":
                flash("File empty hai.", "danger")
                return redirect(url_for("setup"))

            if file and allowed_file(file.filename):
                filename  = secure_filename(f"user_{session['user_id']}_{file.filename}")
                filepath  = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)

                # Parse CV text
                cv_text = parse_cv(filepath)

                db.execute(
                    "UPDATE users SET cv_filename = ?, cv_text = ? WHERE id = ?",
                    (filename, cv_text, session["user_id"])
                )
                db.commit()
                flash("CV upload ho gaya aur parse ho gaya!", "success")
            else:
                flash("Sirf PDF, DOC, DOCX allowed hain.", "danger")

        return redirect(url_for("setup"))

    return render_template("setup.html", user=user)


# ---------------------------------------------------------------------------
# Job Scraping — Manual Trigger
# ---------------------------------------------------------------------------

@app.route("/scrape-jobs", methods=["POST"])
@login_required
def scrape_jobs():
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if not user["job_titles"]:
        return jsonify({"status": "error", "message": "Pehle job titles setup mein set karein."})

    def run_scraper():
        jobs = scrape_all_jobs(user["job_titles"], user["location"] or "")
        for job in jobs:
            existing = db.execute(
                "SELECT id FROM jobs WHERE url = ?", (job["url"],)
            ).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO jobs (title, company, location, description, url, source, scraped_at) VALUES (?,?,?,?,?,?,?)",
                    (job["title"], job["company"], job["location"],
                     job["description"], job["url"], job["source"],
                     datetime.now().isoformat())
                )
        db.commit()

    t = threading.Thread(target=run_scraper)
    t.daemon = True
    t.start()

    return jsonify({"status": "ok", "message": "Job scraping shuru ho gayi! Dashboard refresh karein."})


# ---------------------------------------------------------------------------
# AI Match + Auto Apply
# ---------------------------------------------------------------------------

@app.route("/match-and-apply", methods=["POST"])
@login_required
def match_and_apply():
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if not user["gemini_api_key"]:
        return jsonify({"status": "error", "message": "Gemini API key setup mein add karein."})
    if not user["cv_text"]:
        return jsonify({"status": "error", "message": "Pehle CV upload karein."})

    jobs = db.execute("SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT 100").fetchall()
    if not jobs:
        return jsonify({"status": "error", "message": "Pehle jobs scrape karein."})

    def run_matching():
        matched = match_jobs_with_cv(
            cv_text=user["cv_text"],
            jobs=[dict(j) for j in jobs],
            api_key=user["gemini_api_key"],
            job_titles=user["job_titles"]
        )
        for job in matched:
            already = db.execute(
                "SELECT id FROM applications WHERE user_id = ? AND job_id = ?",
                (session["user_id"], job["id"])
            ).fetchone()
            if not already:
                db.execute(
                    "INSERT INTO applications (user_id, job_id, status, match_score, cover_letter, applied_at) VALUES (?,?,?,?,?,?)",
                    (session["user_id"], job["id"], "pending",
                     job["match_score"], job["cover_letter"],
                     datetime.now().isoformat())
                )
        db.commit()

    t = threading.Thread(target=run_matching)
    t.daemon = True
    t.start()

    return jsonify({"status": "ok", "message": "AI matching shuru ho gayi! Thodi der mein dashboard mein results aayenge."})


@app.route("/apply/<int:app_id>", methods=["POST"])
@login_required
def apply_single(app_id):
    db          = get_db()
    application = db.execute(
        "SELECT a.*, j.url, j.title, j.company FROM applications a JOIN jobs j ON a.job_id = j.id WHERE a.id = ? AND a.user_id = ?",
        (app_id, session["user_id"])
    ).fetchone()

    if not application:
        return jsonify({"status": "error", "message": "Application nahi mili."})

    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    result = auto_apply_job(
        job_url=application["url"],
        cv_path=os.path.join(app.config["UPLOAD_FOLDER"], user["cv_filename"] or ""),
        cover_letter=application["cover_letter"],
        user_info=dict(user)
    )

    status = "applied" if result["success"] else "failed"
    db.execute(
        "UPDATE applications SET status = ?, apply_note = ? WHERE id = ?",
        (status, result["message"], app_id)
    )
    db.commit()

    return jsonify({"status": "ok", "message": result["message"]})


# ---------------------------------------------------------------------------
# Applications list (AJAX)
# ---------------------------------------------------------------------------

@app.route("/api/applications")
@login_required
def api_applications():
    db   = get_db()
    apps = db.execute(
        """SELECT a.id, a.status, a.match_score, a.applied_at, a.apply_note,
                  j.title, j.company, j.location, j.url, j.source
           FROM applications a
           JOIN jobs j ON a.job_id = j.id
           WHERE a.user_id = ?
           ORDER BY a.applied_at DESC""",
        (session["user_id"],)
    ).fetchall()

    return jsonify([dict(a) for a in apps])


# ---------------------------------------------------------------------------
# Scheduler API
# ---------------------------------------------------------------------------

@app.route("/api/scheduler-status")
@login_required
def api_scheduler_status():
    from modules.scheduler import get_scheduler_status
    return jsonify(get_scheduler_status())


@app.route("/api/run-now", methods=["POST"])
@login_required
def api_run_now():
    """Manually trigger one auto cycle right now."""
    from modules.scheduler import _run_auto_cycle
    t = threading.Thread(target=lambda: _run_auto_cycle(app))
    t.daemon = True
    t.start()
    return jsonify({"status": "ok", "message": "Auto cycle shuru ho gaya! Thodi der mein dashboard update hoga."})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5001)
