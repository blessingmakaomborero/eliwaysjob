"""Job Offer event hooks."""
import frappe
from eliways_jobs.utils import (
    create_portal_notification, hiring_context, recruitment_recipients,
    send_portal_email, safe_log,
)


def after_insert(doc, method=None):
    try:
        candidate_email = getattr(doc, "applicant_email", "") or ""
        if not candidate_email:
            # Try to get from Job Applicant
            applicant = frappe.db.get_value("Job Applicant", doc.job_applicant, "email_id")
            candidate_email = applicant or ""
        if not candidate_email:
            return

        ctx = hiring_context(getattr(doc, "job_opening", None))
        company = doc.company or ctx["hiring_company"]
        display = ctx["company_name"] or doc.company
        create_portal_notification(
            user=candidate_email,
            subject=f"Job Offer – {doc.designation}",
            message=(
                f"You have received a job offer for <strong>{doc.designation}</strong> "
                f"at <strong>{display}</strong>."
            ),
            ntype="success",
            link="/candidate/offers",
            company=company,
            reference_doctype="Job Offer",
            reference_name=doc.name,
        )
        send_portal_email(
            to=candidate_email,
            subject=f"Job Offer – {doc.designation} at {display}",
            template="job_offer",
            context={
                **ctx,
                "company_name": display,
                "company": display,
                "candidate_name": doc.applicant_name or candidate_email,
                "designation": doc.designation,
                "offer_date": str(doc.offer_date or frappe.utils.today()),
                "portal_link": f"{frappe.conf.get('portal_url','')}/candidate/offers",
            },
        )
        for emp_email in recruitment_recipients(company, "offer"):
            if emp_email == candidate_email:
                continue
            create_portal_notification(
                user=emp_email,
                subject=f"Offer created – {doc.designation}",
                message=f"An offer was created for {doc.applicant_name or candidate_email}.",
                ntype="info",
                link="/employer/offers",
                company=company,
                reference_doctype="Job Offer",
                reference_name=doc.name,
            )
    except Exception as e:
        safe_log("offer.after_insert", e)
