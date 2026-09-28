"""
Job Applicant event hooks.
Fires Portal Notifications and email alerts without touching HRMS core.
"""
import frappe
from eliways_jobs.utils import (
    create_portal_notification, hiring_context, recruitment_recipients,
    send_portal_email, safe_log,
)


def after_insert(doc, method=None):
    """Candidate applied → notify candidate + employer."""
    try:
        # ── Candidate confirmation ─────────────────────────────────────────
        ctx = hiring_context(doc.job_title)
        company = ctx["hiring_company"]
        title = ctx["job_title"]
        candidate_email = doc.email_id or ""
        if candidate_email:
            create_portal_notification(
                user=candidate_email,
                subject=f"Application Received – {title}",
                message=(
                    f"Your application for <strong>{title}</strong> at "
                    f"<strong>{ctx['company_name']}</strong> has been received."
                ),
                ntype="success",
                link=f"/candidate/applications/{doc.name}",
                company=company,
                reference_doctype="Job Applicant",
                reference_name=doc.name,
            )
            send_portal_email(
                to=candidate_email,
                subject=f"Application Confirmed – {title}",
                template="application_confirmation",
                context={
                    **ctx,
                    "candidate_name": doc.applicant_name or candidate_email,
                    "application_date": frappe.utils.today(),
                    "portal_link": f"{frappe.conf.get('portal_url','')}/candidate/applications/{doc.name}",
                },
            )

        for emp_email in recruitment_recipients(company, "application"):
            create_portal_notification(
                user=emp_email,
                subject=f"New Applicant – {title}",
                message=(
                    f"<strong>{doc.applicant_name}</strong> applied for "
                    f"<strong>{title}</strong> at <strong>{ctx['company_name']}</strong>."
                ),
                ntype="info",
                link=f"/employer/jobs/{doc.job_title}/applicants",
                company=company,
                reference_doctype="Job Applicant",
                reference_name=doc.name,
            )
            send_portal_email(
                to=emp_email,
                subject=f"New Application – {title}",
                template="new_applicant",
                context={
                    **ctx,
                    "candidate_name": doc.applicant_name,
                    "application_date": frappe.utils.today(),
                    "portal_link": f"{frappe.conf.get('portal_url','')}/employer/jobs/{doc.job_title}/applicants",
                },
            )
    except Exception as e:
        safe_log("applicant.after_insert", e)


def on_update(doc, method=None):
    """Status changed → notify candidate if status is a candidate-facing milestone."""
    NOTIFY_STATUSES = {"Accepted", "Rejected", "Hold"}
    if doc.status not in NOTIFY_STATUSES:
        return
    if not doc.has_value_changed("status"):
        return

    status_messages = {
        "Accepted": ("Congratulations! Your application has been shortlisted.", "success"),
        "Rejected": ("We're sorry — your application was not progressed at this time.", "info"),
        "Hold":     ("Your application is currently on hold. We will be in touch.", "info"),
    }
    msg, ntype = status_messages.get(doc.status, ("Your application status has been updated.", "info"))

    candidate_email = doc.email_id or ""
    if candidate_email:
        try:
            ctx = hiring_context(doc.job_title)
            company = ctx["hiring_company"]
            title = ctx["job_title"] or doc.job_title
            create_portal_notification(
                user=candidate_email,
                subject=f"Application Update – {title}",
                message=msg,
                ntype=ntype,
                link=f"/candidate/applications/{doc.name}",
                company=company,
                reference_doctype="Job Applicant",
                reference_name=doc.name,
            )
            send_portal_email(
                to=candidate_email,
                subject=f"Application Update – {title}",
                template="application_status_change",
                context={
                    **ctx,
                    "candidate_name": doc.applicant_name or candidate_email,
                    "job_title":      title,
                    "status":         doc.status,
                    "message":        msg,
                    "portal_link":    f"/candidate/applications/{doc.name}",
                },
            )
        except Exception as e:
            safe_log("applicant.on_update", e)


# ── Helpers ───────────────────────────────────────────────────────────────────

