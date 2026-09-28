"""Shared utilities for the eliways_jobs custom app."""
import frappe
from frappe.utils import now_datetime


def ensure_notification_columns():
    """Add company ownership fields once. Safe to call from hooks."""
    if getattr(frappe.flags, "portal_notification_scoped", None):
        return
    previous = frappe.session.user
    frappe.set_user("Administrator")
    try:
        _add_notification_columns()
    finally:
        frappe.set_user(previous)
    frappe.flags.portal_notification_scoped = True


def _add_notification_columns():
    for fieldname, label in (
        ("company", "Company"),
        ("reference_doctype", "Reference DocType"),
        ("reference_name", "Reference Name"),
    ):
        if frappe.db.has_column("Portal Notification", fieldname):
            continue
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Portal Notification",
            "fieldname": fieldname,
            "label": label,
            "fieldtype": "Data",
            "insert_after": "user",
        }).insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache(doctype="Portal Notification")


def create_portal_notification(
    user: str,
    subject: str,
    message: str,
    ntype: str = "info",
    link: str = "",
    company: str = "",
    reference_doctype: str = "",
    reference_name: str = "",
) -> None:
    """Create a Portal Notification for one user. Company is the hiring company when known."""
    if not user:
        return
    ensure_notification_columns()
    today = frappe.utils.today()
    existing = frappe.db.exists(
        "Portal Notification",
        {"user": user, "subject": subject, "creation": [">=", today]},
    )
    if existing:
        return

    doc = frappe.get_doc({
        "doctype": "Portal Notification",
        "user": user,
        "subject": subject,
        "message": message,
        "type": ntype,
        "link": link or "",
        "read": 0,
        "company": company or "",
        "reference_doctype": reference_doctype or "",
        "reference_name": reference_name or "",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()


def hiring_context(job_opening):
    """Company branding for one vacancy. Job Applicant.job_title stores the Job Opening name."""
    empty = {
        "hiring_company": "", "company": "", "company_name": "", "company_logo": "",
        "company_website": "", "recruiter_name": "", "reply_to_email": "",
        "job_title": job_opening or "", "job_opening": job_opening or "",
    }
    if not job_opening:
        return empty
    opening = frappe.db.get_value(
        "Job Opening", job_opening, ["company", "job_title"], as_dict=True
    ) or {}
    company = opening.get("company") or ""
    profile = {}
    if company:
        rows = frappe.db.sql(
            """SELECT company_name, website, logo, recruitment_email, primary_recruiter_name
               FROM `tabEmployer Profile` WHERE company = %s LIMIT 1""",
            (company,), as_dict=True,
        )
        profile = rows[0] if rows else {}
    display = profile.get("company_name") or company
    return {
        "hiring_company": company,
        "company": display,
        "company_name": display,
        "company_logo": profile.get("logo") or "",
        "company_website": profile.get("website") or "",
        "recruiter_name": profile.get("primary_recruiter_name") or "",
        "reply_to_email": profile.get("recruitment_email") or "",
        "job_title": opening.get("job_title") or job_opening or "",
        "job_opening": job_opening or "",
    }


def recruitment_recipients(company, purpose):
    """Emails that should hear about this company's recruitment events. No other company is included."""
    field = {
        "application": "application_notify_emails",
        "interview": "interview_notify_emails",
        "offer": "offer_notify_emails",
    }.get(purpose, "application_notify_emails")
    if not company:
        return []
    rows = frappe.db.sql(
        """SELECT user, recruitment_email, primary_recruiter_email, `{field}` AS extra
           FROM `tabEmployer Profile` WHERE company = %s""".format(field=field),
        (company,), as_dict=True,
    )
    found = []
    for row in rows:
        for value in (row.user, row.recruitment_email, row.primary_recruiter_email, row.extra):
            for part in str(value or "").replace(";", ",").split(","):
                email = part.strip()
                if "@" in email and email not in found:
                    found.append(email)
    return found


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

        kwargs = {
            "recipients": [to],
            "subject": subject,
            "message": html,
            "delayed": False,
        }
        # Keep the platform mailbox as the address. The hiring company is the display name only.
        outgoing = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "email_id")
        brand = (context.get("company_name") or "").strip()
        if outgoing and "@" in outgoing and brand:
            kwargs["sender"] = f"{brand} via {context.get('portal_name', 'Eliways Jobs')} <{outgoing}>"
        reply_to = (context.get("reply_to_email") or "").strip()
        if "@" in reply_to:
            kwargs["reply_to"] = reply_to
        frappe.sendmail(**kwargs)
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
    brand = ctx.get("company_name") or portal_name
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
            f"<p><strong>{ctx.get('company_name','Your company')}</strong> received a new application.</p>"
            f"<p><strong>{ctx.get('candidate_name','A candidate')}</strong> applied for "
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
    elif template == "job_expiring":
        body_lines.append(
            f"<p><strong>{ctx.get('company_name','')}</strong>: the vacancy "
            f"<strong>{ctx.get('job_title','')}</strong> closes on {ctx.get('closes_on','')}.</p>"
        )
        if ctx.get("message"):
            body_lines.append(f"<p>{ctx.get('message')}</p>")
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
    <h1 style="margin:0;color:white;font-size:20px;">{brand}</h1>
  </div>
  <div style="background:white;padding:24px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px;">
    <h2 style="color:#111827;font-size:18px;margin-top:0;">{subject}</h2>
    {body_html}
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
    <p style="color:#9ca3af;font-size:12px;margin:0;">
      Powered by {portal_name}. The recruitment action above belongs to {brand}.
      <a href="{portal_url}" style="color:#4f46e5;">Visit Portal</a>
    </p>
  </div>
</body>
</html>
"""
