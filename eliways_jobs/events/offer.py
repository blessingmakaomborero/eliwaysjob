"""Job Offer event hooks."""
import frappe
from eliways_jobs.utils import create_portal_notification, send_portal_email, safe_log


def after_insert(doc, method=None):
    try:
        candidate_email = getattr(doc, "applicant_email", "") or ""
        if not candidate_email:
            # Try to get from Job Applicant
            applicant = frappe.db.get_value("Job Applicant", doc.job_applicant, "email_id")
            candidate_email = applicant or ""
        if not candidate_email:
            return

        create_portal_notification(
            user=candidate_email,
            subject=f"Job Offer – {doc.designation}",
            message=f"You have received a job offer for <strong>{doc.designation}</strong> at <strong>{doc.company}</strong>.",
            ntype="success",
            link="/candidate/offers",
        )
        send_portal_email(
            to=candidate_email,
            subject=f"Job Offer – {doc.designation} at {doc.company}",
            template="job_offer",
            context={
                "candidate_name": doc.applicant_name or candidate_email,
                "designation":    doc.designation,
                "company":        doc.company,
                "offer_date":     str(doc.offer_date or frappe.utils.today()),
                "portal_link":    f"{frappe.conf.get('portal_url','')}/candidate/offers",
            },
        )
    except Exception as e:
        safe_log("offer.after_insert", e)
