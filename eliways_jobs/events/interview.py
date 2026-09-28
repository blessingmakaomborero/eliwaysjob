"""Interview event hooks."""
import frappe
from eliways_jobs.utils import (
    create_portal_notification, hiring_context, recruitment_recipients,
    send_portal_email, safe_log,
)


def after_insert(doc, method=None):
    _notify_candidate(doc, is_reschedule=False)


def on_update(doc, method=None):
    if doc.has_value_changed("status") and doc.status == "Cancelled":
        _notify_cancelled(doc)
        return
    if doc.has_value_changed("scheduled_on") or doc.has_value_changed("from_time"):
        _notify_candidate(doc, is_reschedule=True)


def _notify_candidate(doc, is_reschedule: bool):
    try:
        applicant = frappe.get_doc("Job Applicant", doc.job_applicant)
        ctx = hiring_context(applicant.job_title)
        company = ctx["hiring_company"]
        title = ctx["job_title"]
        candidate_email = applicant.email_id or ""
        action = "Rescheduled" if is_reschedule else "Scheduled"
        subject = f"Interview {action} – {title}"
        place = getattr(doc, "location", None) or (doc.interview_summary or "").split("\n")[0]

        if candidate_email:
            create_portal_notification(
                user=candidate_email,
                subject=subject,
                message=(
                    f"Your interview with <strong>{ctx['company_name']}</strong> for "
                    f"<strong>{title}</strong> has been {action.lower()} for "
                    f"<strong>{doc.scheduled_on}</strong> at {doc.from_time}."
                ),
                ntype="info",
                link="/candidate/interviews",
                company=company,
                reference_doctype="Interview",
                reference_name=doc.name,
            )
            send_portal_email(
                to=candidate_email,
                subject=subject,
                template="interview_scheduled",
                context={
                    **ctx,
                    "candidate_name": applicant.applicant_name or candidate_email,
                    "interview_round": doc.interview_round or "Interview",
                    "scheduled_on": str(doc.scheduled_on),
                    "from_time": str(doc.from_time),
                    "to_time": str(doc.to_time or ""),
                    "location": place,
                    "meeting_link": getattr(doc, "virtual_meeting_link", "") or "",
                    "is_reschedule": is_reschedule,
                    "portal_link": f"{frappe.conf.get('portal_url','')}/candidate/interviews",
                },
            )

        recipients = recruitment_recipients(company, "interview")
        for person in _assigned_interviewers(doc):
            if person not in recipients and person != candidate_email:
                recipients.append(person)
        for emp_email in recipients:
            if emp_email == candidate_email:
                continue
            create_portal_notification(
                user=emp_email,
                subject=subject,
                message=(
                    f"Interview {action.lower()} for <strong>{title}</strong> "
                    f"with {applicant.applicant_name or candidate_email}."
                ),
                ntype="info",
                link="/employer/interviews",
                company=company,
                reference_doctype="Interview",
                reference_name=doc.name,
            )
    except Exception as e:
        safe_log("interview.notify_candidate", e)


def _notify_cancelled(doc):
    try:
        applicant = frappe.get_doc("Job Applicant", doc.job_applicant)
        ctx = hiring_context(applicant.job_title)
        company = ctx["hiring_company"]
        title = ctx["job_title"]
        candidate_email = applicant.email_id or ""
        subject = f"Interview Cancelled – {title}"
        message = (
            f"The interview with <strong>{ctx['company_name']}</strong> for "
            f"<strong>{title}</strong> on <strong>{doc.scheduled_on}</strong> has been cancelled."
        )
        if candidate_email:
            create_portal_notification(
                user=candidate_email,
                subject=subject,
                message=message,
                ntype="info",
                link="/candidate/interviews",
                company=company,
                reference_doctype="Interview",
                reference_name=doc.name,
            )
            send_portal_email(
                to=candidate_email,
                subject=subject,
                template="interview_scheduled",
                context={
                    **ctx,
                    "candidate_name": applicant.applicant_name or candidate_email,
                    "interview_round": doc.interview_round or "Interview",
                    "scheduled_on": str(doc.scheduled_on),
                    "from_time": str(doc.from_time),
                    "to_time": str(doc.to_time or ""),
                    "message": "This interview has been cancelled.",
                    "portal_link": "/candidate/interviews",
                },
            )
        for emp_email in recruitment_recipients(company, "interview") + _assigned_interviewers(doc):
            if emp_email == candidate_email:
                continue
            create_portal_notification(
                user=emp_email,
                subject=subject,
                message=message,
                ntype="info",
                link="/employer/interviews",
                company=company,
                reference_doctype="Interview",
                reference_name=doc.name,
            )
    except Exception as e:
        safe_log("interview.notify_cancelled", e)


def _assigned_interviewers(doc):
    found = []
    for row in doc.get("interview_details") or []:
        email = (row.interviewer or "").strip()
        if "@" in email and email not in found:
            found.append(email)
    return found
