"""
AI Matcher Module — Gemini API with Key Rotation
- Matches CV with job descriptions
- Generates match score (0-100)
- Generates personalized cover letter
- Auto-rotates API key on 429 / quota errors (up to 10 keys)
"""

import google.generativeai as genai
import json
import time
import re


MIN_MATCH_SCORE = 60  # Only apply if score >= 60

# Errors that indicate quota exhausted — trigger key rotation
QUOTA_ERRORS = (
    "429", "quota", "rate limit", "resource exhausted",
    "too many requests", "ResourceExhausted"
)


def _is_quota_error(error_str: str) -> bool:
    err = error_str.lower()
    return any(q.lower() in err for q in QUOTA_ERRORS)


def match_jobs_with_cv(cv_text: str, jobs: list, api_key: str,
                       job_titles: str = "", user_id: int = None) -> list:
    """
    Compare CV against each job and return matched jobs with score + cover letter.
    Auto-rotates Gemini API key on quota/429 errors.
    """
    if not cv_text:
        print("[AI Matcher] CV text missing.")
        return []

    # --- Build key pool ---
    # If user_id given, load rotation keys from DB; else use single key
    key_pool = []   # list of (api_key_str, key_id_or_None)

    if user_id:
        try:
            from modules.api_key_manager import get_all_keys, mark_quota_hit, mark_used
            db_keys = get_all_keys(user_id)
            for row in db_keys:
                if row["api_key"] and not row["quota_hit"] and row["is_active"]:
                    key_pool.append((row["api_key"], row["slot"]))
        except Exception as e:
            print(f"[AI Matcher] Could not load rotation keys: {e}")

    # Fallback — add the main api_key if not already in pool
    if api_key and api_key not in [k for k, _ in key_pool]:
        key_pool.append((api_key, None))

    if not key_pool:
        print("[AI Matcher] No API keys available.")
        return []

    current_key_idx = 0
    current_api_key, current_key_id = key_pool[current_key_idx]
    genai.configure(api_key=current_api_key)
    model = genai.GenerativeModel("gemini-flash-lite-latest")
    print(f"[AI Matcher] Using key slot {current_key_id or 'main'} | {len(key_pool)} keys available")

    matched = []
    print(f"[AI Matcher] {len(jobs)} jobs analyse ho rahi hain...")

    for i, job in enumerate(jobs):
        attempt = 0
        while attempt <= len(key_pool):
            try:
                print(f"[AI Matcher] Job {i+1}/{len(jobs)}: {job.get('title')} @ {job.get('company')}")

                result = _analyse_single_job(model, cv_text, job)

                # Track key usage
                if user_id and current_key_id:
                    try:
                        mark_used(current_key_id)
                    except Exception:
                        pass

                if result and result["match_score"] >= MIN_MATCH_SCORE:
                    job["match_score"]  = result["match_score"]
                    job["cover_letter"] = result["cover_letter"]
                    matched.append(job)
                    print(f"  ✓ Match score: {result['match_score']} — ADDED")
                else:
                    score = result["match_score"] if result else 0
                    print(f"  ✗ Match score: {score} — SKIP")

                time.sleep(2)
                break  # success — move to next job

            except Exception as e:
                err_str = str(e)
                if _is_quota_error(err_str):
                    print(f"[AI Matcher] Quota/429 on key slot {current_key_id or 'main'} — rotating...")

                    # Mark this key as quota-hit in DB
                    if user_id and current_key_id:
                        try:
                            mark_quota_hit(current_key_id)
                        except Exception:
                            pass

                    # Try next key
                    current_key_idx += 1
                    if current_key_idx >= len(key_pool):
                        print("[AI Matcher] All API keys exhausted! Stopping.")
                        return matched

                    current_api_key, current_key_id = key_pool[current_key_idx]
                    genai.configure(api_key=current_api_key)
                    model = genai.GenerativeModel("gemini-flash-lite-latest")
                    print(f"[AI Matcher] Switched to key slot {current_key_id or 'main'}")
                    attempt += 1
                    time.sleep(2)
                    # retry same job with new key
                else:
                    print(f"[AI Matcher] Error on job {job.get('title')}: {err_str}")
                    time.sleep(5)
                    break  # non-quota error — skip job

    print(f"[AI Matcher] Done. {len(matched)} jobs matched.")
    return matched


def _analyse_single_job(model, cv_text: str, job: dict) -> dict | None:
    """Send one job to Gemini and get match score + cover letter."""

    prompt = f"""
You are an expert HR analyst and career coach.

CANDIDATE CV:
{cv_text[:3000]}

JOB POSTING:
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Location: {job.get('location', 'N/A')}
Description: {job.get('description', 'N/A')[:1500]}

TASK:
1. Analyse how well this candidate matches the job.
2. Give a match score from 0 to 100 (100 = perfect match).
3. Write a short, professional cover letter (max 200 words) for this specific job.

IMPORTANT: Respond ONLY in this exact JSON format, no extra text:
{{
  "match_score": <number 0-100>,
  "match_reason": "<one sentence why>",
  "cover_letter": "<full cover letter text>"
}}
"""

    try:
        response = model.generate_content(prompt)
        text     = response.text.strip()

        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "match_score":  int(data.get("match_score", 0)),
                "match_reason": data.get("match_reason", ""),
                "cover_letter": data.get("cover_letter", "")
            }
    except json.JSONDecodeError:
        print(f"[AI Matcher] JSON parse error")
    except Exception as e:
        raise  # re-raise so caller can handle quota errors

    return None


def generate_cover_letter(cv_text: str, job: dict, api_key: str) -> str:
    """Generate a standalone cover letter for a specific job."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-flash-lite-latest")

    prompt = f"""
Write a professional cover letter for this job application.

CANDIDATE CV SUMMARY:
{cv_text[:2000]}

JOB:
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Description: {job.get('description', 'N/A')[:1000]}

Write a compelling, personalized cover letter in 150-200 words.
Start with "Dear Hiring Manager,"
End with "Sincerely, [Candidate Name]"
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Cover Letter] Error: {e}")
        return "Cover letter generation failed."
