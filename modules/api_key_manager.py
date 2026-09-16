"""
API Key Manager — Gemini Key Rotation
- Up to 10 API keys per user
- Auto-rotates on 429 / quota errors
- Tracks which keys hit their limit
- Resets quota_hit daily
"""

from datetime import datetime
from modules.database import get_db


def get_next_key(user_id: int) -> dict | None:
    """
    Return the next available (non-quota-hit) API key for this user.
    Returns dict with {id, slot, api_key} or None if all exhausted.
    """
    db = get_db()
    row = db.execute("""
        SELECT id, slot, api_key FROM api_keys
        WHERE user_id = ? AND is_active = 1 AND quota_hit = 0 AND api_key != ''
        ORDER BY slot ASC
        LIMIT 1
    """, (user_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def mark_quota_hit(key_id: int):
    """Mark a key as quota-exhausted so rotation skips it."""
    db = get_db()
    db.execute("""
        UPDATE api_keys
        SET quota_hit = 1, error_count = error_count + 1, last_used = ?
        WHERE id = ?
    """, (datetime.utcnow().isoformat(), key_id))
    db.commit()
    db.close()
    print(f"[KeyManager] Key id={key_id} marked quota_hit — rotating to next key.")


def mark_used(key_id: int):
    """Update last_used timestamp."""
    db = get_db()
    db.execute("UPDATE api_keys SET last_used = ? WHERE id = ?",
               (datetime.utcnow().isoformat(), key_id))
    db.commit()
    db.close()


def reset_quota_hits(user_id: int):
    """Reset all quota flags for a user (call daily or manually)."""
    db = get_db()
    db.execute("UPDATE api_keys SET quota_hit = 0 WHERE user_id = ?", (user_id,))
    db.commit()
    db.close()
    print(f"[KeyManager] Quota reset for user_id={user_id}")


def get_all_keys(user_id: int) -> list:
    """Return all 10 key slots for a user (for setup page display)."""
    db = get_db()
    rows = db.execute("""
        SELECT slot, api_key, is_active, quota_hit, error_count, last_used
        FROM api_keys
        WHERE user_id = ?
        ORDER BY slot ASC
    """, (user_id,)).fetchall()
    db.close()
    keys = {row["slot"]: dict(row) for row in rows}
    # Fill missing slots with empty
    result = []
    for slot in range(1, 11):
        result.append(keys.get(slot, {
            "slot": slot, "api_key": "", "is_active": 1,
            "quota_hit": 0, "error_count": 0, "last_used": None
        }))
    return result


def save_key(user_id: int, slot: int, api_key: str):
    """Insert or update an API key for a given slot."""
    db = get_db()
    db.execute("""
        INSERT INTO api_keys (user_id, slot, api_key, is_active, quota_hit, error_count)
        VALUES (?, ?, ?, 1, 0, 0)
        ON CONFLICT(user_id, slot) DO UPDATE SET
            api_key     = excluded.api_key,
            is_active   = 1,
            quota_hit   = 0,
            error_count = 0
    """, (user_id, slot, api_key.strip()))
    db.commit()
    db.close()


def get_active_key_for_user(user_id: int, fallback_key: str = "") -> tuple:
    """
    Get the first available key. Falls back to user's main gemini_api_key
    if no rotation keys set.
    Returns (api_key_string, key_id_or_None)
    """
    key_row = get_next_key(user_id)
    if key_row and key_row["api_key"]:
        return key_row["api_key"], key_row["id"]
    # fallback to main key stored in users table
    if fallback_key:
        return fallback_key, None
    return "", None
