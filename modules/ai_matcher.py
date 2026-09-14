"""
AI Matcher Module — Gemini API
- Matches CV with job descriptions
- Generates match score (0-100)
- Generates personalized cover letter
"""

import google.generativeai as genai
import json
import time
import re


MIN_MATCH_SCORE = 60  # Only apply if score >= 60


def match_jobs_with_cv(cv_text: str, jobs: list, api_key: str, job_titles: str = "") -> list:
    """
    Compare CV against each job and return matched jobs with score + cover letter.
    Only returns jobs with match_score >= MIN_MATCH_SCORE.
    """
    if not api_key or not cv_text:
        print("[AI Matcher] API key ya CV text missing hai.")
        return []

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-flash-lite-latest")

    matched = []
    print(f"[AI Matcher] {len(jobs)} jobs analyse ho rahi hain...")

    for i, job in enumerate(jobs):
        try:
            print(f"[AI Matcher] Job {i+1}/{len(jobs)}: {job.get('title')} @ {job.get('company')}")

            result = _analyse_single_job(model, cv_text, job)

            if result and result["match_score"] >= MIN_MATCH_SCORE:
                job["match_score"]  = result["match_score"]
                job["cover_letter"] = result["cover_letter"]
                matched.append(job)
                print(f"  ✓ Match score: {result['match_score']} — ADDED")
            else:
                score = result["match_score"] if result else 0
                print(f"  ✗ Match score: {score} — SKIP")

            # Rate limit — Gemini free tier allows 15 req/min
            time.sleep(2)

        except Exception as e:
            print(f"[AI Matcher] Error on job {job.get('title')}: {e}")
            time.sleep(5)
            continue

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

        # Extract JSON from response
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "match_score":  int(data.get("match_score", 0)),
                "match_reason": data.get("match_reason", ""),
                "cover_letter": data.get("cover_letter", "")
            }
    except json.JSONDecodeError:
        print(f"[AI Matcher] JSON parse error, response was: {text[:200]}")
    except Exception as e:
        print(f"[AI Matcher] Gemini error: {e}")

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
