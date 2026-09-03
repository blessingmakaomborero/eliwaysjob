"""Interview event hooks."""
import frappe
from eliways_jobs.utils import create_portal_notification, send_portal_email, safe_log


def after_insert(doc, method=None):
    _notify_candidate(doc, is_reschedule=False)


def on_update(doc, method=None):
    if doc.has_value_changed("scheduled_on") or doc.has_value_changed("from_time"):
        _notify_candidate(doc, is_reschedule=True)


def _notify_candidate(doc, is_reschedule: bool):
    try:
        applicant = frappe.get_doc("Job Applicant", doc.job_applicant)
        candidate_email = applicant.email_id or ""
        if not candidate_email:
            return

        action = "Rescheduled" if is_reschedule else "Scheduled"
        subject = f"Interview {action} – {applicant.job_title}"

        create_portal_notification(
            user=candidate_email,
            subject=subject,
            message=(
                f"Your interview for <strong>{applicant.job_title}</strong> has been "
                f"{action.lower()} for <strong>{doc.scheduled_on}</strong> at {doc.from_time}."
            ),
            ntype="info",
            link="/candidate/interviews",
        )
        send_portal_email(
            to=candidate_email,
            subject=subject,
            template="interview_scheduled",
            context={
                "candidate_name":  applicant.applicant_name or candidate_email,
                "job_title":       applicant.job_title,
                "interview_round": doc.interview_round or "Interview",
                "scheduled_on":    str(doc.scheduled_on),
                "from_time":       str(doc.from_time),
                "to_time":         str(doc.to_time or ""),
                "location":        doc.location or "",
                "meeting_link":    doc.virtual_meeting_link or "",
                "is_reschedule":   is_reschedule,
                "portal_link":     f"{frappe.conf.get('portal_url','')}/candidate/interviews",
            },
        )
    except Exception as e:
        safe_log("interview.notify_candidate", e)
