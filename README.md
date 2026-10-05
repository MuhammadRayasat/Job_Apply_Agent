# Job Application Automation Agent

This repository contains an automated system designed to streamline the job application process. It includes features for scraping job listings, matching them against a CV using AI, and automating applications on platforms like Indeed.

## Core Features
- **Job Scraping:** Automatically fetches job listings based on preferred titles and locations.
- **AI Matching:** Uses AI to evaluate job descriptions against your uploaded CV.
- **Auto-Apply:** Attempts to automate the application process for matched jobs.
- **Dashboard:** Manages applications, tracks status (pending, applied, failed), and provides statistics.
- **Indeed Session Management:** Safely handles Indeed authentication sessions for automation.

## Technical Stack
- **Backend:** Flask (Python)
- **Database:** SQLite
- **Automation/Scraping:** Playwright
- **AI Matching:** (Gemini API integration)
- **Task Scheduling:** APScheduler

## Quick Setup
1.  **Environment:** Ensure you have Python installed and install dependencies from `requirements.txt`.
2.  **Configuration:** Configure environment variables and API keys as required.
3.  **Launch:** Run the application using `python app.py` (or the provided start scripts).
4.  **Dashboard:** Access the interface to upload your CV, set job preferences, and start the scraping/matching process.
