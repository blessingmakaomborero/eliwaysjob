"""
Job Applicant event hooks.
Fires Portal Notifications and email alerts without touching HRMS core.
"""
import frappe
from eliways_jobs.utils import create_portal_notification, send_portal_email, safe_log


def after_insert(doc, method=None):
    """Candidate applied → notify candidate + employer."""
    try:
        # ── Candidate confirmation ─────────────────────────────────────────
        candidate_email = doc.email_id or ""
        if candidate_email:
            create_portal_notification(
                user=candidate_email,
                subject="Application Received",
                message=(
                    f"Your application for <strong>{doc.job_title}</strong> has been received. "
                    "We will review it and be in touch."
                ),
                ntype="success",
                link=f"/candidate/applications/{doc.name}",
            )
            send_portal_email(
                to=candidate_email,
                subject=f"Application Confirmed – {doc.job_title}",
                template="application_confirmation",
                context={
                    "candidate_name": doc.applicant_name or candidate_email,
                    "job_title":      doc.job_title,
                    "company":        _get_job_company(doc.job_title),
                    "application_date": frappe.utils.today(),
                    "portal_link":    f"{frappe.conf.get('portal_url','')}/candidate/applications/{doc.name}",
                },
            )

        # ── Employer new applicant notification ────────────────────────────
        employer_emails = _get_employer_emails(doc.job_title)
        for emp_email in employer_emails:
            create_portal_notification(
                user=emp_email,
                subject="New Applicant",
                message=(
                    f"<strong>{doc.applicant_name}</strong> applied for "
                    f"<strong>{doc.job_title}</strong>."
                ),
                ntype="info",
                link=f"/employer/jobs/{doc.job_title}/applicants",
            )
            send_portal_email(
                to=emp_email,
                subject=f"New Application – {doc.job_title}",
                template="new_applicant",
                context={
                    "candidate_name": doc.applicant_name,
                    "job_title":      doc.job_title,
                    "application_date": frappe.utils.today(),
                    "portal_link":    f"{frappe.conf.get('portal_url','')}/employer/jobs/{frappe.utils.scrub(doc.job_title)}/applicants",
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
            create_portal_notification(
                user=candidate_email,
                subject=f"Application Update – {doc.job_title}",
                message=msg,
                ntype=ntype,
                link=f"/candidate/applications/{doc.name}",
            )
            send_portal_email(
                to=candidate_email,
                subject=f"Application Update – {doc.job_title}",
                template="application_status_change",
                context={
                    "candidate_name": doc.applicant_name or candidate_email,
                    "job_title":      doc.job_title,
                    "status":         doc.status,
                    "message":        msg,
                    "portal_link":    f"{frappe.conf.get('portal_url','')}/candidate/applications/{doc.name}",
                },
            )
        except Exception as e:
            safe_log("applicant.on_update", e)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_job_company(job_title: str) -> str:
    try:
        return frappe.db.get_value("Job Opening", job_title, "company") or ""
    except Exception:
        return ""


def _get_employer_emails(job_title: str) -> list:
    """Return email addresses of Employer Recruiter users for this job's company."""
    try:
        company = _get_job_company(job_title)
        if not company:
            return []
        profiles = frappe.get_list(
            "Employer Profile",
            filters={"company": company},
            fields=["user"],
            limit=10,
        )
        return [p.user for p in profiles if p.user]
    except Exception:
        return []
