"""Employer Profile event hooks."""
import frappe
from eliways_jobs.utils import create_portal_notification, send_portal_email, safe_log


def on_update(doc, method=None):
    """Notify employer when verification status changes."""
    if not doc.has_value_changed("verification_status"):
        return

    employer_email = doc.user or doc.email or ""
    if not employer_email:
        return

    status = doc.verification_status
    messages = {
        "Verified":  ("Your company has been verified. You can now publish job openings.", "success"),
        "Rejected":  ("Your company verification was not approved. Please contact support for assistance.", "error"),
        "Suspended": ("Your employer account has been suspended. Please contact support.", "error"),
        "Pending":   ("Your company verification status has been reset to Pending.", "info"),
    }
    msg, ntype = messages.get(status, ("Your verification status has been updated.", "info"))

    try:
        create_portal_notification(
            user=employer_email,
            subject=f"Company Verification: {status}",
            message=msg,
            ntype=ntype,
            link="/employer/company",
        )
        send_portal_email(
            to=employer_email,
            subject=f"Company Verification Update – {status}",
            template="employer_verification",
            context={
                "company_name": doc.company_name or doc.company or "",
                "status":       status,
                "message":      msg,
                "portal_link":  f"{frappe.conf.get('portal_url','')}/employer/company",
            },
        )
    except Exception as e:
        safe_log("employer.on_update", e)
