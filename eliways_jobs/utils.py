"""Shared utilities for the eliways_jobs custom app."""
import frappe
from frappe.utils import now_datetime


def create_portal_notification(
    user: str,
    subject: str,
    message: str,
    ntype: str = "info",
    link: str = "",
) -> None:
    """Create a Portal Notification record for a user (deduped by subject+user+day)."""
    today = frappe.utils.today()
    existing = frappe.db.exists(
        "Portal Notification",
        {"user": user, "subject": subject, "creation": [">=", today]},
    )
    if existing:
        return  # avoid duplicate notifications same day

    doc = frappe.get_doc({
        "doctype": "Portal Notification",
        "user":    user,
        "subject": subject,
        "message": message,
        "type":    ntype,
        "link":    link or "",
        "read":    0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()


def send_portal_email(
    to: str,
    subject: str,
    template: str,
    context: dict,
) -> bool:
    """
    Send a transactional email using Frappe's email queue.
    Falls back to simple sendmail if template not found.
    Returns True on success, False on failure (logs error).
    """
    try:
        portal_url = frappe.conf.get("portal_url", "http://localhost:3000")
        context.setdefault("portal_name", frappe.conf.get("portal_name", "Eliways Jobs"))
        context.setdefault("portal_url", portal_url)

        # Build a simple HTML body since we may not have email templates configured
        html = _build_email_html(subject, template, context)

        frappe.sendmail(
            recipients=[to],
            subject=subject,
            message=html,
            delayed=False,
        )
        frappe.logger("eliways_jobs").info(
            f"[email] Sent '{subject}' to {to}"
        )
        return True
    except Exception as e:
        frappe.logger("eliways_jobs").error(
            f"[email] Failed to send '{subject}' to {to}: {e}"
        )
        return False


def safe_log(context_name: str, exc: Exception) -> None:
    """Log an exception without re-raising."""
    frappe.logger("eliways_jobs").error(
        f"[eliways_jobs.{context_name}] {type(exc).__name__}: {exc}"
    )


def _build_email_html(subject: str, template: str, ctx: dict) -> str:
    """Build a minimal branded HTML email body."""
    portal_name = ctx.get("portal_name", "Eliways Jobs")
    portal_url  = ctx.get("portal_url", "#")
    body_lines  = []

    greet = ctx.get("candidate_name") or ctx.get("company_name") or ""
    if greet:
        body_lines.append(f"<p>Dear {greet},</p>")

    # Template-specific paragraphs
    if template == "application_confirmation":
        body_lines.append(
            f"<p>Your application for <strong>{ctx.get('job_title','')}</strong> at "
            f"<strong>{ctx.get('company','')}</strong> has been received on "
            f"{ctx.get('application_date','')}.</p>"
            f"<p>We will review it and be in touch. You can track your application status in your portal.</p>"
        )
    elif template == "new_applicant":
        body_lines.append(
            f"<p><strong>{ctx.get('candidate_name','A candidate')}</strong> has applied for "
            f"<strong>{ctx.get('job_title','')}</strong> on {ctx.get('application_date','')}.</p>"
        )
    elif template == "application_status_change":
        body_lines.append(
            f"<p>Your application for <strong>{ctx.get('job_title','')}</strong> has been updated.</p>"
            f"<p><strong>Status:</strong> {ctx.get('status','')}</p>"
            f"<p>{ctx.get('message','')}</p>"
        )
    elif template == "interview_scheduled":
        action = "rescheduled" if ctx.get("is_reschedule") else "scheduled"
        body_lines.append(
            f"<p>Your interview for <strong>{ctx.get('job_title','')}</strong> has been {action}.</p>"
            f"<ul>"
            f"<li><strong>Round:</strong> {ctx.get('interview_round','')}</li>"
            f"<li><strong>Date:</strong> {ctx.get('scheduled_on','')}</li>"
            f"<li><strong>Time:</strong> {ctx.get('from_time','')} – {ctx.get('to_time','')}</li>"
        )
        if ctx.get("location"):
            body_lines.append(f"<li><strong>Location:</strong> {ctx['location']}</li>")
        if ctx.get("meeting_link"):
            meeting_link = ctx['meeting_link']
            body_lines.append(f"<li><strong>Meeting Link:</strong> <a href='{meeting_link}'>{meeting_link}</a></li>")
        body_lines.append("</ul>")
    elif template == "job_offer":
        body_lines.append(
            f"<p>Congratulations! You have received a job offer for "
            f"<strong>{ctx.get('designation','')}</strong> at <strong>{ctx.get('company','')}</strong>.</p>"
            f"<p>Offer Date: {ctx.get('offer_date','')}</p>"
        )
    elif template == "employer_verification":
        body_lines.append(f"<p>{ctx.get('message','Your verification status has been updated.')}</p>")
    elif template == "job_alert_digest":
        body_lines.append(f"<p>Here are the latest jobs matching your alert <strong>{ctx.get('keywords','')}</strong>:</p>")
        for job in ctx.get("jobs", []):
            job_id    = job.get("id", "")
            job_title = job.get("title", "")
            company   = job.get("company", "")
            location  = job.get("location", "")
            job_link  = f"{portal_url}/jobs/{job_id}"
            body_lines.append(
                f"<div style='margin:12px 0;padding:12px;border:1px solid #e5e7eb;border-radius:8px;'>"
                f"<p style='margin:0;font-weight:600;'>{job_title}</p>"
                f"<p style='margin:4px 0;color:#6b7280;font-size:14px;'>{company} · {location}</p>"
                f"<a href='{job_link}' style='color:#4f46e5;font-size:14px;'>View Job &#8594;</a>"
                f"</div>"
            )
    else:
        body_lines.append(f"<p>{subject}</p>")

    if ctx.get("portal_link"):
        link = ctx["portal_link"] if ctx["portal_link"].startswith("http") else f"{portal_url}{ctx['portal_link']}"
        body_lines.append(f"<p><a href='{link}' style='color:#4f46e5;'>View in Portal →</a></p>")

    body_html = "\n".join(body_lines)

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject}</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#111827;">
  <div style="background:#4f46e5;padding:16px 24px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;color:white;font-size:20px;">{portal_name}</h1>
  </div>
  <div style="background:white;padding:24px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px;">
    <h2 style="color:#111827;font-size:18px;margin-top:0;">{subject}</h2>
    {body_html}
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
    <p style="color:#9ca3af;font-size:12px;margin:0;">
      You received this email because you have an account on {portal_name}.
      <a href="{portal_url}" style="color:#4f46e5;">Visit Portal</a>
    </p>
  </div>
</body>
</html>
"""
