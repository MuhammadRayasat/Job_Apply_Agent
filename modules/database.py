import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jobagent.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            email           TEXT    NOT NULL UNIQUE,
            password        TEXT    NOT NULL,
            notify_email    TEXT,
            gemini_api_key  TEXT,
            job_titles      TEXT,
            location        TEXT,
            cv_filename     TEXT,
            cv_text         TEXT,
            is_active       INTEGER DEFAULT 1,
            auto_apply      INTEGER DEFAULT 1,
            last_run        TEXT,
            created_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            description TEXT,
            url         TEXT UNIQUE,
            source      TEXT,
            scraped_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS applications (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            job_id       INTEGER NOT NULL,
            status       TEXT    DEFAULT 'pending',
            match_score  REAL    DEFAULT 0,
            cover_letter TEXT,
            apply_note   TEXT,
            applied_at   TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (job_id)  REFERENCES jobs(id),
            UNIQUE(user_id, job_id)
        );
    """)
    db.commit()
    db.close()
    print("[DB] Database initialized.")
    _migrate_db()


def _migrate_db():
    """Add new columns to existing DB without breaking old data."""
    db = get_db()
    existing_cols = [row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()]

    migrations = {
        "notify_email":     "ALTER TABLE users ADD COLUMN notify_email TEXT",
        "auto_apply":       "ALTER TABLE users ADD COLUMN auto_apply INTEGER DEFAULT 1",
        "last_run":         "ALTER TABLE users ADD COLUMN last_run TEXT",
        "linkedin_email":   "ALTER TABLE users ADD COLUMN linkedin_email TEXT",
        "linkedin_password":"ALTER TABLE users ADD COLUMN linkedin_password TEXT",
    }

    for col, sql in migrations.items():
        if col not in existing_cols:
            db.execute(sql)
            print(f"[DB] Migrated: added column '{col}'")

    db.commit()
    db.close()
