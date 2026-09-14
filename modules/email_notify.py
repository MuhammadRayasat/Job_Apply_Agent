"""
Email Notification Module — Gmail SMTP
Sends email to user when:
- A job has been applied to
- Daily summary of applications
- New matching jobs found
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------

def send_email(to_email: str, subject: str, html_body: str) -> dict:
    """
    Send an email via Gmail SMTP.
    Requires GMAIL_USER and GMAIL_APP_PASSWORD in environment / .env
    Returns: {"success": bool, "message": str}
    """
    gmail_user     = os.environ.get("GMAIL_USER", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_user or not gmail_password:
        return {
            "success": False,
            "message": "Gmail credentials .env mein set nahi hain (GMAIL_USER, GMAIL_APP_PASSWORD)."
        }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"JobAgent <{gmail_user}>"
        msg["To"]      = to_email

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_password)
            smtp.sendmail(gmail_user, to_email, msg.as_string())

        print(f"[Email] Sent to {to_email}: {subject}")
        return {"success": True, "message": f"Email sent to {to_email}"}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "Gmail auth failed. App Password check karo."}
    except Exception as e:
        return {"success": False, "message": f"Email error: {str(e)}"}


# ---------------------------------------------------------------------------
# Notification templates
# ---------------------------------------------------------------------------

def notify_job_applied(user_name: str, user_email: str, job: dict) -> dict:
    """Notify user that a job was applied to."""
    subject = f"JobAgent: Applied — {job.get('title')} @ {job.get('company')}"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;
                background: #0f172a; color: #e2e8f0; padding: 30px; border-radius: 12px;">

      <div style="text-align: center; margin-bottom: 24px;">
        <h1 style="color: #6366f1; font-size: 24px;">🤖 JobAgent</h1>
        <p style="color: #94a3b8;">Automatic Application Update</p>
      </div>

      <div style="background: #1e293b; border: 1px solid #334155;
                  border-radius: 10px; padding: 20px; margin-bottom: 20px;">
        <p style="color: #22c55e; font-size: 16px; margin-bottom: 12px;">
          ✅ <strong>Apply ho gaya!</strong>
        </p>
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="padding: 8px 0; color: #94a3b8; width: 120px;">Job Title</td>
            <td style="padding: 8px 0; color: #e2e8f0;"><strong>{job.get('title', 'N/A')}</strong></td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94a3b8;">Company</td>
            <td style="padding: 8px 0; color: #e2e8f0;">{job.get('company', 'N/A')}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94a3b8;">Location</td>
            <td style="padding: 8px 0; color: #e2e8f0;">{job.get('location', 'N/A')}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94a3b8;">Source</td>
            <td style="padding: 8px 0; color: #a5b4fc;">{job.get('source', 'N/A')}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94a3b8;">Match Score</td>
            <td style="padding: 8px 0; color: #22c55e;"><strong>{job.get('match_score', 0)}%</strong></td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #94a3b8;">Applied At</td>
            <td style="padding: 8px 0; color: #e2e8f0;">{datetime.now().strftime('%d %b %Y, %I:%M %p')}</td>
          </tr>
        </table>
        {"<br><a href='" + job.get('url','') + "' style='color: #6366f1;'>Job Link dekho</a>" if job.get('url') else ""}
      </div>

      <p style="color: #94a3b8; font-size: 13px; text-align: center;">
        Hi {user_name}, yeh JobAgent ka automatic notification hai.<br>
        Dashboard pe saari applications dekho.
      </p>
    </div>
    """
    return send_email(user_email, subject, html)


def notify_daily_summary(user_name: str, user_email: str, stats: dict) -> dict:
    """Send daily summary of job applications."""
    subject = f"JobAgent Daily Summary — {stats.get('applied_today', 0)} jobs applied today"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;
                background: #0f172a; color: #e2e8f0; padding: 30px; border-radius: 12px;">

      <div style="text-align: center; margin-bottom: 24px;">
        <h1 style="color: #6366f1; font-size: 24px;">🤖 JobAgent</h1>
        <p style="color: #94a3b8;">Daily Summary — {datetime.now().strftime('%d %B %Y')}</p>
      </div>

      <div style="display: flex; gap: 12px; margin-bottom: 20px;">
        <div style="flex:1; background: #1e293b; border-radius: 10px; padding: 16px; text-align: center;">
          <div style="font-size: 32px; color: #6366f1; font-weight: bold;">{stats.get('applied_today', 0)}</div>
          <div style="color: #94a3b8; font-size: 13px;">Applied Today</div>
        </div>
        <div style="flex:1; background: #1e293b; border-radius: 10px; padding: 16px; text-align: center;">
          <div style="font-size: 32px; color: #22c55e; font-weight: bold;">{stats.get('total_applied', 0)}</div>
          <div style="color: #94a3b8; font-size: 13px;">Total Applied</div>
        </div>
        <div style="flex:1; background: #1e293b; border-radius: 10px; padding: 16px; text-align: center;">
          <div style="font-size: 32px; color: #f59e0b; font-weight: bold;">{stats.get('new_jobs', 0)}</div>
          <div style="color: #94a3b8; font-size: 13px;">New Jobs Found</div>
        </div>
      </div>

      <p style="color: #94a3b8; font-size: 13px; text-align: center;">
        Hi {user_name}, JobAgent din bhar kaam karta raha.<br>
        Kal bhi automatically apply karta rahega!
      </p>
    </div>
    """
    return send_email(user_email, subject, html)


def notify_new_matches(user_name: str, user_email: str, jobs: list) -> dict:
    """Notify user about new job matches found."""
    subject = f"JobAgent: {len(jobs)} naye jobs mili hain!"

    jobs_html = ""
    for job in jobs[:5]:
        jobs_html += f"""
        <tr>
          <td style="padding: 10px; border-bottom: 1px solid #334155;">
            <strong style="color: #e2e8f0;">{job.get('title','N/A')}</strong><br>
            <span style="color: #94a3b8; font-size: 12px;">{job.get('company','N/A')} · {job.get('location','N/A')}</span>
          </td>
          <td style="padding: 10px; border-bottom: 1px solid #334155; text-align: center;">
            <span style="color: #22c55e; font-weight: bold;">{job.get('match_score',0)}%</span>
          </td>
          <td style="padding: 10px; border-bottom: 1px solid #334155; text-align: center;">
            <span style="color: #a5b4fc; font-size: 12px;">{job.get('source','N/A')}</span>
          </td>
        </tr>
        """

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;
                background: #0f172a; color: #e2e8f0; padding: 30px; border-radius: 12px;">

      <div style="text-align: center; margin-bottom: 24px;">
        <h1 style="color: #6366f1; font-size: 24px;">🤖 JobAgent</h1>
        <p style="color: #22c55e; font-size: 16px;">{len(jobs)} naye matching jobs mili hain!</p>
      </div>

      <table style="width: 100%; border-collapse: collapse; background: #1e293b;
                    border-radius: 10px; overflow: hidden;">
        <thead>
          <tr style="background: #334155;">
            <th style="padding: 12px; text-align: left; color: #94a3b8; font-size: 12px;">JOB</th>
            <th style="padding: 12px; text-align: center; color: #94a3b8; font-size: 12px;">MATCH</th>
            <th style="padding: 12px; text-align: center; color: #94a3b8; font-size: 12px;">SOURCE</th>
          </tr>
        </thead>
        <tbody>
          {jobs_html}
        </tbody>
      </table>

      <p style="color: #94a3b8; font-size: 13px; text-align: center; margin-top: 20px;">
        Hi {user_name}, JobAgent ne automatically apply kar diya hai inhe.<br>
        Dashboard pe details dekho.
      </p>
    </div>
    """
    return send_email(user_email, subject, html)
