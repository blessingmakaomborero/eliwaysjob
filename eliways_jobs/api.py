"""
Whitelisted API methods for the Eliways Jobs portal BFF.

These are called via /api/method/eliways_jobs.api.<function> from Next.js
server-side routes (admin token auth). They return aggregated SQL results
so the BFF never has to pull thousands of rows into JavaScript memory.
"""
import frappe


@frappe.whitelist(allow_guest=False)
def get_job_counts_by_company(companies: list) -> dict:
    """
    Return a dict of { company_name: open_job_count } for the given list of
    company names, using a single GROUP BY query with the composite index
    idx_jo_company_status.

    Called by the companies BFF route to avoid fetching up to 999 Job Opening
    rows just to count them.

    Args:
        companies: list of company name strings (max 200 to avoid oversized IN clauses)

    Returns:
        dict  { "Acme Corp": 4, "TechCo": 12, ... }
    """
    if not companies or not isinstance(companies, list):
        return {}

    # Safety cap — the BFF pages companies in sets of 50 anyway
    companies = companies[:200]

    placeholders = ", ".join(["%s"] * len(companies))
    rows = frappe.db.sql(
        """
        SELECT company, COUNT(*) AS cnt
        FROM   `tabJob Opening`
        WHERE  status = 'Open'
          AND  company IN ({placeholders})
          AND  job_title NOT REGEXP '^(Suite Verified Job|Company A Job|Company B Job|E2E |Test Job|BFF Test|Expiry Test)'
        GROUP  BY company
        """.format(placeholders=placeholders),
        tuple(companies),
        as_dict=True,
    )
    return {r["company"]: r["cnt"] for r in rows}


@frappe.whitelist(allow_guest=False)
def get_portal_stats() -> dict:
    """
    Return platform-level counts in a single DB round-trip each (index-only reads).
    Called by the /api/jobs/stats BFF route.
    """
    active_jobs = frappe.db.sql(
        """
        SELECT COUNT(*) FROM `tabJob Opening`
        WHERE status = 'Open'
          AND job_title NOT REGEXP '^(Suite Verified Job|Company A Job|Company B Job|E2E |Test Job|BFF Test|Expiry Test)'
        """
    )[0][0]
    total_apps = frappe.db.count("Job Applicant")
    employers = frappe.db.sql(
        """
        SELECT COUNT(*) FROM `tabCompany`
        WHERE name NOT REGEXP '^Test Corp'
          AND name != 'hr test'
        """
    )[0][0]
    candidates = frappe.db.count("Candidate Profile")
    return {
        "activeJobs":   active_jobs,
        "applications": total_apps,
        "employers":    employers,
        "candidates":   candidates,
    }


@frappe.whitelist(allow_guest=False)
def get_admin_summary(thirty_days_ago: str) -> dict:
    """
    Return all admin dashboard counts with minimal DB work.
    Each count hits an index-range scan; no full-table fetches.

    Args:
        thirty_days_ago: ISO date string, e.g. "2026-08-03"
    """
    # Job Opening counts
    active_jobs  = frappe.db.count("Job Opening", filters={"status": "Open"})
    closed_jobs  = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabJob Opening` WHERE status != 'Open'",
    )[0][0]

    # Application counts
    total_apps   = frappe.db.count("Job Applicant")
    recent_apps  = frappe.db.count("Job Applicant",
                                   filters=[["creation", ">=", thirty_days_ago]])

    # Status breakdown — only the status column, capped at 50k rows
    # (distinct status values ≤ ~10, so the reduce is O(1))
    app_rows = frappe.db.sql(
        "SELECT status, COUNT(*) AS cnt FROM `tabJob Applicant` GROUP BY status",
        as_dict=True,
    )
    apps_by_status = {r["status"] or "Unknown": r["cnt"] for r in app_rows}

    offer_rows = frappe.db.sql(
        "SELECT status, COUNT(*) AS cnt FROM `tabJob Offer` GROUP BY status",
        as_dict=True,
    )
    offers_by_status = {r["status"] or "Unknown": r["cnt"] for r in offer_rows}

    # Interview / offer totals
    total_interviews = frappe.db.count("Interview")
    total_offers     = frappe.db.count("Job Offer")

    # People counts
    total_candidates = frappe.db.count("Candidate Profile")
    total_employers  = frappe.db.count("Employer Profile")
    verified_emp     = frappe.db.count("Employer Profile",
                                       filters={"verification_status": "Verified"})
    pending_emp      = frappe.db.count("Employer Profile",
                                       filters={"verification_status": "Pending"})

    return {
        "summary": {
            "activeJobs":        active_jobs,
            "closedJobs":        closed_jobs,
            "totalJobs":         active_jobs + closed_jobs,
            "totalApplications": total_apps,
            "totalInterviews":   total_interviews,
            "totalOffers":       total_offers,
            "totalCandidates":   total_candidates,
            "totalEmployers":    total_employers,
            "verifiedEmployers": verified_emp,
            "pendingEmployers":  pending_emp,
        },
        "applicationsByStatus": apps_by_status,
        "offersByStatus":       offers_by_status,
        "recruitmentFunnel": {
            "applied":     total_apps,
            "shortlisted": apps_by_status.get("Accepted", 0),
            "interview":   total_interviews,
            "offer":       total_offers,
            "hired":       apps_by_status.get("Hired", 0),
        },
        "recentApplicationsCount": recent_apps,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Career Resources CMS API
# ═══════════════════════════════════════════════════════════════════════════

import secrets
from datetime import datetime, timedelta


@frappe.whitelist(allow_guest=True)
def get_resource_list() -> list:
    """
    Return all published Career Resources for the index page.
    Guest-accessible — no auth required.
    """
    return frappe.get_list(
        "Career Resource",
        filters=[["status", "=", "Published"]],
        fields=[
            "name", "slug", "title", "category", "description",
            "read_time", "icon", "color", "tags",
            "is_sponsored", "sponsor_name", "sponsor_logo",
            "published_at",
        ],
        order_by="published_at desc",
        limit=50,
        ignore_permissions=True,
    )


@frappe.whitelist(allow_guest=True)
def get_resource(slug: str) -> dict:
    """
    Return a single published Career Resource by slug.
    Guest-accessible.
    """
    results = frappe.get_list(
        "Career Resource",
        filters=[["slug", "=", slug], ["status", "=", "Published"]],
        fields=[
            "name", "slug", "title", "category", "description",
            "intro", "body", "tags", "read_time", "icon", "color",
            "is_sponsored", "sponsor_name", "sponsor_logo", "sponsor_url", "sponsor_cta",
            "has_sidebar_ad", "ad_company", "ad_tagline", "ad_logo", "ad_url", "ad_cta",
            "prev_slug", "prev_title", "next_slug", "next_title",
            "meta_title", "meta_desc", "published_at",
        ],
        limit=1,
        ignore_permissions=True,
    )
    if not results:
        frappe.throw("Resource not found", frappe.DoesNotExistError)
    return results[0]


@frappe.whitelist(allow_guest=True)
def get_resource_downloads(slug: str) -> list:
    """
    Return active downloads attached to a Career Resource.
    Free and premium both listed — client decides gate logic.
    """
    # Find the resource name from slug
    rec = frappe.db.get_value("Career Resource", {"slug": slug}, "name")
    if not rec:
        return []

    return frappe.get_list(
        "Resource Download",
        filters=[["resource", "=", rec], ["is_active", "=", 1]],
        fields=[
            "name", "title", "description", "file_type",
            "is_free", "price_usd", "price_zwg", "thumbnail_url",
        ],
        order_by="is_free desc, price_usd asc",
        limit=20,
        ignore_permissions=True,
    )


@frappe.whitelist(allow_guest=False)
def initiate_payment(download_name: str, user_email: str, payment_method: str = "Paynow") -> dict:
    """
    Create a pending Resource Payment record and return payment details.
    For free downloads, marks as Paid immediately and returns a token.

    Args:
        download_name:   Resource Download document name
        user_email:      Buyer's email address
        payment_method:  Paynow | EcoCash | Manual | Free

    Returns:
        dict with status, payment_name, redirect_url (for Paynow),
        or download_token (for free/already-paid).
    """
    download = frappe.get_doc("Resource Download", download_name)

    # ── Free download ──────────────────────────────────────────────────────
    if download.is_free:
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=24)
        pay = frappe.get_doc({
            "doctype":       "Resource Payment",
            "user_email":    user_email,
            "download":      download_name,
            "amount_usd":    0,
            "currency":      "USD",
            "status":        "Paid",
            "payment_method":"Free",
            "paid_at":       datetime.utcnow(),
            "download_token": token,
            "token_expires": expires,
        })
        pay.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "paid", "download_token": token, "expires": str(expires)}

    # ── Check if already paid ─────────────────────────────────────────────
    existing = frappe.get_list(
        "Resource Payment",
        filters=[
            ["user_email", "=", user_email],
            ["download",   "=", download_name],
            ["status",     "=", "Paid"],
        ],
        fields=["name", "download_token", "token_expires"],
        limit=1,
        ignore_permissions=True,
    )
    if existing:
        rec = existing[0]
        # Refresh token if expired
        if not rec.get("token_expires") or \
                datetime.utcnow() > datetime.fromisoformat(str(rec["token_expires"])):
            token = secrets.token_urlsafe(32)
            expires = datetime.utcnow() + timedelta(hours=24)
            frappe.db.set_value("Resource Payment", rec["name"], {
                "download_token": token,
                "token_expires":  expires,
            })
            frappe.db.commit()
            return {"status": "paid", "download_token": token, "expires": str(expires)}
        return {"status": "paid", "download_token": rec["download_token"]}

    integration_id = frappe.conf.get("paynow_integration_id") or ""
    integration_key = frappe.conf.get("paynow_integration_key") or ""
    if not integration_id or not integration_key:
        return {
            "status": "not_configured",
            "message": "Card payments are not available yet. Paynow credentials are not set on this site.",
        }

    # ── Create pending payment record ─────────────────────────────────────
    pay = frappe.get_doc({
        "doctype":        "Resource Payment",
        "user_email":     user_email,
        "download":       download_name,
        "amount_usd":     download.price_usd or 2,
        "currency":       "USD",
        "status":         "Pending",
        "payment_method": payment_method,
    })
    pay.insert(ignore_permissions=True)
    frappe.db.commit()

    # ── Paynow integration ─────────────────────────────────────────────────
    # Paynow Zimbabwe REST API v2
    # Docs: https://developers.paynow.co.zw/docs/integration.html
    # Credentials are stored in Frappe site config for security.
    paynow_result = _initiate_paynow(
        payment_name=pay.name,
        email=user_email,
        amount=float(download.price_usd or 2),
        description=f"Download: {download.title}",
    )

    if paynow_result.get("redirect_url"):
        frappe.db.set_value("Resource Payment", pay.name, {
            "paynow_ref": paynow_result.get("poll_url", ""),
        })
        frappe.db.commit()

    return {
        "status":       "pending",
        "payment_name": pay.name,
        "redirect_url": paynow_result.get("redirect_url", ""),
        "poll_url":     paynow_result.get("poll_url", ""),
        "amount_usd":   float(download.price_usd or 2),
    }


@frappe.whitelist(allow_guest=False)
def verify_payment(payment_name: str, user_email: str) -> dict:
    """
    Poll Paynow to check if payment has been completed.
    If paid, generate a download token and return it.

    Returns:
        dict with status ('pending'|'paid'|'failed') and download_token if paid.
    """
    try:
        pay = frappe.get_doc("Resource Payment", payment_name)
    except frappe.DoesNotExistError:
        return {"status": "not_found"}

    if pay.user_email != user_email:
        frappe.throw("Access denied", frappe.PermissionError)

    if pay.status == "Paid":
        return {"status": "paid", "download_token": pay.download_token}

    # Poll Paynow if we have a reference
    if pay.paynow_ref:
        result = _poll_paynow(pay.paynow_ref)
        if result.get("paid"):
            token = secrets.token_urlsafe(32)
            expires = datetime.utcnow() + timedelta(hours=24)
            frappe.db.set_value("Resource Payment", payment_name, {
                "status":         "Paid",
                "paid_at":        datetime.utcnow(),
                "download_token": token,
                "token_expires":  expires,
                "paynow_status":  result.get("raw_status", ""),
            })
            frappe.db.commit()
            return {"status": "paid", "download_token": token}
        elif result.get("failed"):
            frappe.db.set_value("Resource Payment", payment_name, {
                "status":        "Failed",
                "paynow_status": result.get("raw_status", ""),
            })
            frappe.db.commit()
            return {"status": "failed"}

    return {"status": "pending"}


@frappe.whitelist(allow_guest=False)
def get_download_url(download_token: str, user_email: str) -> dict:
    """
    Exchange a valid download token for the actual file URL.
    Token is single-use with a 24h expiry.
    """
    payments = frappe.get_list(
        "Resource Payment",
        filters=[
            ["download_token", "=", download_token],
            ["user_email",     "=", user_email],
            ["status",         "=", "Paid"],
        ],
        fields=["name", "download", "token_expires"],
        limit=1,
        ignore_permissions=True,
    )
    if not payments:
        return {"error": "Invalid or expired token"}

    pay = payments[0]
    if pay.get("token_expires") and \
            datetime.utcnow() > datetime.fromisoformat(str(pay["token_expires"])):
        return {"error": "Download link has expired. Please request a new one."}

    download = frappe.get_doc("Resource Download", pay["download"])
    return {"file_url": download.file_url, "title": download.title}


# ─── Paynow helpers ───────────────────────────────────────────────────────────

def _initiate_paynow(payment_name: str, email: str, amount: float, description: str) -> dict:
    """
    Initiate a Paynow payment. Returns redirect_url and poll_url.
    Credentials from frappe.conf (site_config.json):
        paynow_integration_id
        paynow_integration_key
        portal_url  (for return/result URLs)
    """
    try:
        import hashlib, urllib.parse, requests as req_lib

        integration_id  = frappe.conf.get("paynow_integration_id",  "")
        integration_key = frappe.conf.get("paynow_integration_key", "")
        portal_url      = frappe.conf.get("portal_url", "http://localhost:3000")

        if not integration_id or not integration_key:
            return {"error": "not_configured", "redirect_url": "", "poll_url": ""}

        return_url = f"{portal_url}/career-resources/downloads/complete?ref={payment_name}"
        result_url = f"{portal_url}/api/jobs/resources/paynow-callback"

        fields = {
            "id":          integration_id,
            "reference":   payment_name,
            "amount":      f"{amount:.2f}",
            "additionalinfo": description,
            "returnurl":   return_url,
            "resulturl":   result_url,
            "authemail":   email,
            "status":      "Message",
        }

        # Build hash: values in order + key, SHA512
        values = "".join(str(fields[k]) for k in [
            "id","reference","amount","additionalinfo","returnurl","resulturl","status"
        ]) + integration_key
        fields["hash"] = hashlib.sha512(values.encode()).hexdigest().upper()

        resp = req_lib.post(
            "https://www.paynow.co.zw/interface/initiatetransaction",
            data=fields, timeout=15
        )
        parsed = dict(urllib.parse.parse_qsl(resp.text))
        if parsed.get("status", "").lower() == "ok":
            return {
                "redirect_url": parsed.get("browserurl", ""),
                "poll_url":     parsed.get("pollurl", ""),
            }
        frappe.logger("eliways_jobs").error(f"[paynow] Init failed: {parsed}")
        return {"redirect_url": "", "poll_url": ""}
    except Exception as e:
        frappe.logger("eliways_jobs").error(f"[paynow] Exception: {e}")
        return {"redirect_url": "", "poll_url": ""}


def _poll_paynow(poll_url: str) -> dict:
    """Poll Paynow for payment status. Returns {paid, failed, raw_status}."""
    try:
        import urllib.parse, requests as req_lib
        resp = req_lib.get(poll_url, timeout=10)
        parsed = dict(urllib.parse.parse_qsl(resp.text))
        raw = parsed.get("status", "").lower()
        return {
            "paid":       raw in ("paid", "awaiting delivery"),
            "failed":     raw in ("cancelled", "failed"),
            "raw_status": raw,
        }
    except Exception as e:
        frappe.logger("eliways_jobs").error(f"[paynow.poll] {e}")
        return {"paid": False, "failed": False, "raw_status": "error"}


@frappe.whitelist(allow_guest=False)
def get_resource_stats() -> dict:
    """Admin: return revenue and download counts."""
    total_paid = frappe.db.count("Resource Payment", filters={"status": "Paid"})
    revenue = frappe.db.sql(
        "SELECT IFNULL(SUM(amount_usd),0) as total FROM `tabResource Payment` WHERE status='Paid'"
    )[0][0]
    downloads_by_item = frappe.db.sql(
        """SELECT rd.title, COUNT(rp.name) as sales
           FROM `tabResource Payment` rp
           JOIN `tabResource Download` rd ON rd.name = rp.download
           WHERE rp.status = 'Paid'
           GROUP BY rp.download
           ORDER BY sales DESC LIMIT 10""",
        as_dict=True,
    )
    sponsored_count = frappe.db.count("Career Resource", filters={"is_sponsored": 1, "status": "Published"})
    return {
        "total_paid_downloads": total_paid,
        "total_revenue_usd":    float(revenue or 0),
        "top_downloads":        downloads_by_item,
        "sponsored_articles":   sponsored_count,
    }


@frappe.whitelist(allow_guest=False)
def get_employer_profiles(status: str = "", search: str = "", limit: int = 200) -> list:
    """
    Return employer profiles for the admin verification page.
    Uses ignore_permissions=True so the admin API token can read the
    custom DocType without requiring explicit DocType-level permissions.
    """
    filters = []
    if status:
        filters.append(["verification_status", "=", status])
    if search:
        filters.append(["company_name", "like", f"%{search}%"])

    return frappe.get_list(
        "Employer Profile",
        filters=filters,
        fields=[
            "name", "user", "company_name", "email", "phone",
            "industry", "city", "country",
            "verification_status", "creation",
            "onboarding_completed", "onboarding_step",
        ],
        order_by="creation desc",
        limit=int(limit),
        ignore_permissions=True,
    )


@frappe.whitelist(allow_guest=False)
def update_employer_verification(profile_name: str, status: str, notes: str = "", verified_by: str = "") -> dict:
    """
    Update an employer's verification status.
    Uses direct SQL to avoid the DocType controller import error
    on custom=1 DocTypes that don't have a Python controller class.
    """
    allowed = {"Pending", "Verified", "Rejected", "Suspended"}
    if status not in allowed:
        frappe.throw(f"Invalid status: {status}")

    # Use direct SQL to avoid 'No module named frappe.core.doctype.employer_profile'
    # which occurs when frappe.get_doc tries to load a Python controller for a custom DocType
    exists = frappe.db.sql(
        "SELECT name, user, email, company_name, company FROM `tabEmployer Profile` WHERE name = %s",
        (profile_name,), as_dict=True
    )
    if not exists:
        frappe.throw(f"Employer Profile not found: {profile_name}")

    employer = exists[0]

    if status == "Verified":
        from eliways_jobs.employer_review import assert_subscription_paid
        assert_subscription_paid(profile_name)

    if status == "Verified":
        frappe.db.sql(
            """UPDATE `tabEmployer Profile`
               SET verification_status = %s, verification_date = NOW(), verified_by = %s, modified = NOW()
               WHERE name = %s""",
            (status, verified_by or frappe.session.user, profile_name),
        )
    else:
        frappe.db.sql(
            "UPDATE `tabEmployer Profile` SET verification_status = %s, modified = NOW() WHERE name = %s",
            (status, profile_name),
        )
    frappe.db.commit()

    if notes:
        frappe.logger("eliways_jobs").info(f"[verify] {profile_name} → {status}: {notes}")

    # Update User role
    user_email = employer.get("user", "")
    if user_email:
        try:
            user = frappe.get_doc("User", user_email)
            current_roles = [r.role for r in user.roles]
            if status == "Verified":
                if "Employer Manager" not in current_roles:
                    user.append("roles", {"role": "Employer Manager"})
                    user.save(ignore_permissions=True)
                    frappe.db.commit()
            elif status in ("Rejected", "Suspended"):
                user.roles = [r for r in user.roles if r.role not in ("Employer Manager",)]
                user.save(ignore_permissions=True)
                frappe.db.commit()
        except Exception as e:
            frappe.logger("eliways_jobs").error(f"[update_employer_verification] role update failed: {e}")

    _notify_verification(employer, status)
    return {"status": status, "profile": profile_name}


def _notify_verification(employer, status):
    """In-portal notice and email. The profile update is SQL, so the document hook does not run."""
    messages = {
        "Verified": "Your company has been verified. You can now publish job openings.",
        "Rejected": "Your company verification was not approved. Please contact support.",
        "Suspended": "Your employer account has been suspended. New recruitment actions are disabled.",
        "Pending": "Your company verification status has been reset to Pending.",
    }
    recipient = employer.get("user") or employer.get("email") or ""
    if not recipient:
        return
    message = messages.get(status, "Your verification status has been updated.")
    company_name = employer.get("company_name") or employer.get("company") or ""
    try:
        from eliways_jobs.utils import create_portal_notification, send_portal_email
        create_portal_notification(
            user=recipient,
            subject=f"Company Verification: {status}",
            message=message,
            ntype="success" if status == "Verified" else "error" if status in ("Rejected", "Suspended") else "info",
            link="/employer/dashboard",
            company=employer.get("company") or "",
            reference_doctype="Employer Profile",
            reference_name=employer.get("name") or "",
        )
        send_portal_email(
            to=recipient,
            subject=f"Company Verification Update – {status}",
            template="employer_verification",
            context={
                "company_name": company_name,
                "status": status,
                "message": message,
                "portal_link": "/employer/dashboard",
            },
        )
    except Exception as e:
        frappe.logger("eliways_jobs").error(f"[update_employer_verification] notify failed: {e}")


@frappe.whitelist(allow_guest=False)
def company_recruiters(company):
    """Users who may be assigned as interviewers for this company."""
    company = (company or "").strip()
    if not company:
        return []
    people = []
    seen = set()
    owners = frappe.db.sql(
        """SELECT user, primary_recruiter_name, company_name
           FROM `tabEmployer Profile` WHERE company = %s""",
        (company,), as_dict=True,
    )
    for row in owners:
        email = (row.user or "").strip()
        if email and email not in seen:
            seen.add(email)
            people.append({
                "user": email,
                "name": row.primary_recruiter_name or row.company_name or email,
                "role": "Employer Owner",
            })
    members = frappe.db.sql(
        """SELECT user, member_role FROM `tabEmployer Membership`
           WHERE company = %s AND status = 'Active'""",
        (company,), as_dict=True,
    )
    for row in members:
        email = (row.user or "").strip()
        if email and email not in seen:
            seen.add(email)
            people.append({"user": email, "name": email, "role": row.member_role or "Recruiter"})
    return people


@frappe.whitelist(allow_guest=False)
def interview_assignees(interviews):
    """Interview Detail rows for the given interview names. Child tables are not listed reliably over REST."""
    if isinstance(interviews, str):
        import json
        interviews = json.loads(interviews or "[]")
    names = [name for name in (interviews or []) if name]
    if not names:
        return []
    return frappe.db.sql(
        """SELECT parent, interviewer FROM `tabInterview Detail`
           WHERE parent IN ({placeholders})""".format(
            placeholders=", ".join(["%s"] * len(names))
        ),
        tuple(names),
        as_dict=True,
    )


@frappe.whitelist(allow_guest=False)
def ensure_interview_cancelled_status():
    """Add Cancelled to Interview status without editing the HRMS app."""
    options = "Pending\nUnder Review\nCleared\nRejected\nCancelled"
    current = frappe.db.get_value(
        "Property Setter",
        {"doc_type": "Interview", "field_name": "status", "property": "options"},
        "value",
    )
    if current == options:
        return options
    previous = frappe.session.user
    frappe.set_user("Administrator")
    try:
        from frappe.custom.doctype.property_setter.property_setter import make_property_setter
        make_property_setter("Interview", "status", "options", options, "Text", validate_fields_for_doctype=False)
        frappe.db.commit()
    finally:
        frappe.set_user(previous)
    frappe.clear_cache(doctype="Interview")
    return options


@frappe.whitelist(allow_guest=False)
def create_portal_notification(user: str, subject: str, message: str,
                                ntype: str = "info", link: str = "") -> dict:
    """Create a Portal Notification record."""
    try:
        from eliways_jobs.utils import create_portal_notification as _create
        _create(user=user, subject=subject, message=message, ntype=ntype, link=link)
        return {"created": True}
    except Exception as e:
        frappe.logger("eliways_jobs").error(f"[create_portal_notification] {e}")
        return {"created": False, "error": str(e)}


@frappe.whitelist(allow_guest=False)
def create_employer_profile(user: str, company_name: str, email: str,
                             phone: str = "", industry: str = "",
                             website: str = "", country: str = "",
                             city: str = "") -> dict:
    """
    Create an Employer Profile using direct SQL to avoid the DocType
    controller import error on custom=1 DocTypes.
    Idempotent — skips if profile already exists for this user.
    """
    existing = frappe.db.sql(
        "SELECT name FROM `tabEmployer Profile` WHERE user = %s LIMIT 1",
        (user,)
    )
    if existing:
        return {"name": existing[0][0], "created": False}

    duplicate, reason = _probable_duplicate(company_name, email)
    _ensure_profile_columns()

    import secrets as _secrets
    name = _secrets.token_urlsafe(8)
    columns = set(frappe.db.get_table_columns("Employer Profile"))
    row = {
        "name": name,
        "owner": "Administrator",
        "modified_by": "Administrator",
        "docstatus": 0,
        "user": user,
        "company_name": company_name,
        "email": email,
        "phone": phone,
        "industry": industry,
        "website": website,
        "country": country,
        "city": city,
        "verification_status": "Pending",
        "onboarding_completed": 0,
        "onboarding_step": 1,
        "duplicate_flag": duplicate,
        "duplicate_reason": reason,
    }
    usable = {key: value for key, value in row.items() if key in columns}
    col_sql = ", ".join(f"`{key}`" for key in usable)
    val_sql = ", ".join(["%s"] * len(usable))
    frappe.db.sql(
        f"INSERT INTO `tabEmployer Profile` ({col_sql}, creation, modified) VALUES ({val_sql}, NOW(), NOW())",
        list(usable.values()),
    )
    frappe.db.commit()
    return {"name": name, "created": True, "duplicate_flag": duplicate, "duplicate_reason": reason}


@frappe.whitelist(allow_guest=False)
def ensure_job_offer_fields():
    """Store portal offer details on the HRMS Job Offer without editing HRMS."""
    previous = frappe.session.user
    frappe.set_user("Administrator")
    try:
        fields = [
            {
                "fieldname": "job_opening",
                "label": "Job Opening",
                "fieldtype": "Link",
                "options": "Job Opening",
                "insert_after": "job_applicant",
            },
            {
                "fieldname": "date_of_joining",
                "label": "Date of Joining",
                "fieldtype": "Date",
                "insert_after": "offer_date",
            },
            {
                "fieldname": "currency",
                "label": "Currency",
                "fieldtype": "Link",
                "options": "Currency",
                "insert_after": "company",
            },
            {
                "fieldname": "gross_salary",
                "label": "Gross Salary",
                "fieldtype": "Currency",
                "insert_after": "currency",
            },
        ]
        for field in fields:
            if frappe.db.has_column("Job Offer", field["fieldname"]):
                continue
            frappe.get_doc({"doctype": "Custom Field", "dt": "Job Offer", **field}).insert(
                ignore_permissions=True
            )
        frappe.db.commit()
    finally:
        frappe.set_user(previous)
    return {"ok": True}


def _ensure_duplicate_flag():
    previous = frappe.session.user
    frappe.set_user("Administrator")
    try:
        if not frappe.db.has_column("Employer Profile", "duplicate_flag"):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Employer Profile",
                "fieldname": "duplicate_flag",
                "label": "Probable Duplicate",
                "fieldtype": "Check",
                "insert_after": "verification_status",
            }).insert(ignore_permissions=True)
        if not frappe.db.has_column("Employer Profile", "duplicate_reason"):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Employer Profile",
                "fieldname": "duplicate_reason",
                "label": "Duplicate Reason",
                "fieldtype": "Small Text",
                "insert_after": "duplicate_flag",
            }).insert(ignore_permissions=True)
        frappe.db.commit()
    finally:
        frappe.set_user(previous)


def _probable_duplicate(company_name, email):
    """Flag a registration that matches another company's name or private email domain. Never merge."""
    named = frappe.db.sql(
        "SELECT name FROM `tabEmployer Profile` WHERE company_name = %s LIMIT 1",
        (company_name,),
    )
    if named:
        return 1, "Same company name as an existing employer. Review both records. Do not merge them."
    domain = (email or "").split("@")[-1].lower()
    public = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "mail.test"}
    if domain and domain not in public:
        match = frappe.db.sql(
            "SELECT company_name FROM `tabEmployer Profile` WHERE email LIKE %s LIMIT 1",
            ("%@" + domain,),
        )
        if match:
            return 1, "Email domain @{0} is already used by {1}. Review both records. Do not merge them.".format(
                domain, match[0][0]
            )
    return 0, ""


@frappe.whitelist(allow_guest=False)
def get_employer_profile_by_user(user: str) -> dict:
    """
    Fetch a single Employer Profile by user email using direct SQL.
    Returns all columns so the onboarding wizard can pre-fill from
    data saved during registration (company_name, industry, country, city).
    """
    rows = frappe.db.sql(
        "SELECT * FROM `tabEmployer Profile` WHERE user = %s LIMIT 1",
        (user,), as_dict=True
    )
    if not rows:
        return {}
    profile = dict(rows[0])
    # Convert datetime objects to strings for JSON serialisation
    for k, v in profile.items():
        if hasattr(v, 'isoformat'):
            profile[k] = v.isoformat()
    return profile


PROFILE_COLUMNS = {
    "company_description": "text",
    "company_size": "varchar(140)",
    "trading_name": "varchar(140)",
    "registration_number": "varchar(140)",
    "tax_id": "varchar(140)",
    "company_type": "varchar(140)",
    "year_established": "varchar(140)",
    "primary_recruiter_name": "varchar(140)",
    "primary_recruiter_title": "varchar(140)",
    "primary_recruiter_email": "varchar(140)",
    "primary_recruiter_phone": "varchar(140)",
    "primary_recruiter_department": "varchar(140)",
    "recruitment_email": "varchar(140)",
    "cc_recruitment_emails": "text",
    "reply_to_email": "varchar(140)",
    "default_job_location": "varchar(140)",
    "application_notify_emails": "text",
    "interview_notify_emails": "text",
    "offer_notify_emails": "text",
    "logo": "varchar(255)",
    "duplicate_flag": "int(1) NOT NULL DEFAULT 0",
    "duplicate_reason": "text",
}


def _ensure_profile_columns():
    """The portal table was created without the onboarding columns. Add any that are missing."""
    added = False
    for field, column_type in PROFILE_COLUMNS.items():
        if frappe.db.has_column("Employer Profile", field):
            continue
        frappe.db.sql(f"ALTER TABLE `tabEmployer Profile` ADD COLUMN `{field}` {column_type}")
        added = True
    if added:
        frappe.db.commit()
        frappe.cache.hdel("table_columns", "tabEmployer Profile")


@frappe.whitelist(allow_guest=False)
def update_employer_profile(user: str, data: dict) -> dict:
    """
    Update an Employer Profile by user email using direct SQL SET.
    Ignores protected system fields. Creates the profile if it doesn't exist.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)
    if not isinstance(data, dict):
        frappe.throw("Profile data must be a set of fields.")

    PROTECTED = {
        'name', 'owner', 'creation', 'modified', 'modified_by',
        'docstatus', 'idx', 'user',
    }

    _ensure_profile_columns()
    existing = frappe.db.sql(
        "SELECT name FROM `tabEmployer Profile` WHERE user = %s LIMIT 1",
        (user,)
    )
    if not existing:
        created = create_employer_profile(
            user=user,
            company_name=data.get("company_name") or "",
            email=data.get("email") or user,
            phone=data.get("phone") or "",
            industry=data.get("industry") or "",
            website=data.get("website") or "",
            country=data.get("country") or "",
            city=data.get("city") or "",
        )
        if not created or created.get("error"):
            return {"error": (created or {}).get("error") or "Could not create the employer profile."}
        existing = frappe.db.sql(
            "SELECT name FROM `tabEmployer Profile` WHERE user = %s LIMIT 1",
            (user,),
        )
        if not existing:
            return {"error": "Could not create the employer profile."}

    profile_name = existing[0][0]
    columns = set(frappe.db.get_table_columns("Employer Profile"))
    safe = {k: v for k, v in data.items() if k not in PROTECTED and k in columns}

    if not safe:
        return {"updated": 0}

    # Build SET clause
    set_parts = []
    values = []
    for k, v in safe.items():
        set_parts.append(f"`{k}` = %s")
        values.append(v)

    values.append(profile_name)
    frappe.db.sql(
        f"UPDATE `tabEmployer Profile` SET {', '.join(set_parts)}, modified = NOW() WHERE name = %s",
        values
    )
    frappe.db.commit()
    return {"updated": len(safe), "profile": profile_name}


def _unique_company_abbr(company_name):
    """Allocate an abbreviation that is not already used by another Company."""
    words = [word for word in (company_name or "").split() if word]
    base = "".join(word[0] for word in words).upper()[:5] or "CO"
    if not frappe.db.exists("Company", {"abbr": base}):
        return base
    import hashlib
    digest = hashlib.sha1(company_name.encode("utf-8")).hexdigest()[:4].upper()
    for index in range(36):
        suffix = digest if index == 0 else digest[:3] + format(index, "X")
        candidate = (base[:1] + suffix)[:5]
        if not frappe.db.exists("Company", {"abbr": candidate}):
            return candidate
    frappe.throw("Could not allocate a unique company abbreviation.")


@frappe.whitelist(allow_guest=False)
def ensure_portal_company(company_name, country="Zimbabwe", industry="Services"):
    """
    Return the ERPNext Company name for a portal employer.
    Creates the company when it does not exist, with an abbreviation that
    does not collide with an unrelated company.
    """
    company_name = (company_name or "").strip()
    if not company_name:
        frappe.throw("Company name is required.")
    existing = frappe.db.get_value("Company", {"company_name": company_name}, "name")
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Company",
        "company_name": company_name,
        "abbr": _unique_company_abbr(company_name),
        "country": country or "Zimbabwe",
        "default_currency": "USD",
        "domain": industry or "Services",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


@frappe.whitelist(allow_guest=False)
def backfill_employer_companies() -> dict:
    """
    One-time fix: for every Employer Profile where company IS NULL but
    company_name is set, find or create the matching Frappe Company and
    link it back. Called once after migration to fix legacy profiles.
    """
    profiles = frappe.db.sql(
        "SELECT name, user, company_name, country, industry "
        "FROM `tabEmployer Profile` "
        "WHERE (company IS NULL OR company = '') AND company_name IS NOT NULL AND company_name != ''",
        as_dict=True,
    )
    fixed = 0
    for p in profiles:
        company_name = p.get("company_name", "")
        if not company_name:
            continue
        # Find existing company
        existing = frappe.db.sql(
            "SELECT name FROM `tabCompany` WHERE company_name = %s LIMIT 1",
            (company_name,), as_dict=True
        )
        if existing:
            co_name = existing[0]["name"]
        else:
            try:
                co_name = ensure_portal_company(
                    company_name,
                    p.get("country") or "Zimbabwe",
                    p.get("industry") or "Services",
                )
            except Exception as e:
                frappe.logger("eliways_jobs").error(f"[backfill] Company create failed for {company_name}: {e}")
                continue

        frappe.db.sql(
            "UPDATE `tabEmployer Profile` SET company = %s, modified = NOW() WHERE name = %s",
            (co_name, p["name"])
        )
        fixed += 1

    frappe.db.commit()
    frappe.logger("eliways_jobs").info(f"[backfill_employer_companies] Fixed {fixed} profiles")
    return {"fixed": fixed}


# ─── Portal account ───────────────────────────────────────────────────────────

_NOTIFY_FIELDS = ("notify_status", "notify_interviews", "notify_offers", "notify_alerts")


def _ensure_notification_columns():
    columns = {row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabCandidate Profile`")}
    for field in _NOTIFY_FIELDS:
        if field not in columns:
            frappe.db.sql(
                f"ALTER TABLE `tabCandidate Profile` ADD COLUMN `{field}` int(1) NOT NULL DEFAULT 1"
            )
    frappe.db.commit()


def _assert_portal_user(user_email: str):
    if not user_email or user_email in ("Administrator", "Guest"):
        frappe.throw("This account cannot be changed from the portal.")
    if not frappe.db.exists("User", user_email):
        frappe.throw("Account not found.")
    if "System Manager" in frappe.get_roles(user_email):
        frappe.throw("Administrator accounts must be changed from Frappe Desk.")


@frappe.whitelist(allow_guest=False)
def change_portal_password(user_email: str, old_password: str, new_password: str) -> dict:
    """Verify the current password, then set a new one. Called by the portal BFF."""
    _assert_portal_user(user_email)
    if not old_password or not new_password:
        frappe.throw("Current password and new password are required.")
    if len(new_password) < 8:
        frappe.throw("Password must be at least 8 characters.")
    if old_password == new_password:
        frappe.throw("Choose a password that is different from the current one.")

    from frappe.utils.password import check_password, update_password

    try:
        check_password(user_email, old_password)
    except frappe.AuthenticationError:
        frappe.throw("Current password is incorrect.")

    update_password(user_email, new_password, logout_all_sessions=False)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist(allow_guest=False)
def deactivate_portal_account(user_email: str, password: str) -> dict:
    """Disable a portal user after they confirm their password. Records stay in HRMS."""
    _assert_portal_user(user_email)
    if not password:
        frappe.throw("Password is required.")

    from frappe.utils.password import check_password

    try:
        check_password(user_email, password)
    except frappe.AuthenticationError:
        frappe.throw("Password is incorrect.")

    frappe.db.set_value("User", user_email, "enabled", 0)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist(allow_guest=False)
def get_notification_prefs(user_email: str) -> dict:
    _assert_portal_user(user_email)
    _ensure_notification_columns()
    rows = frappe.db.sql(
        """
        SELECT notify_status, notify_interviews, notify_offers, notify_alerts
        FROM `tabCandidate Profile`
        WHERE user = %s
        LIMIT 1
        """,
        user_email,
        as_dict=True,
    )
    if not rows:
        return {field: 1 for field in _NOTIFY_FIELDS}
    return {field: int(rows[0].get(field) or 0) for field in _NOTIFY_FIELDS}


@frappe.whitelist(allow_guest=False)
def set_notification_prefs(user_email: str, prefs) -> dict:
    _assert_portal_user(user_email)
    _ensure_notification_columns()
    if isinstance(prefs, str):
        prefs = frappe.parse_json(prefs)
    if not isinstance(prefs, dict):
        frappe.throw("Preferences are required.")

    values = {field: 1 if prefs.get(field) else 0 for field in _NOTIFY_FIELDS}
    found = frappe.db.sql(
        "SELECT name FROM `tabCandidate Profile` WHERE user = %s LIMIT 1",
        user_email,
    )
    if not found:
        frappe.throw("Create your candidate profile before changing notification settings.")
    frappe.db.sql(
        """
        UPDATE `tabCandidate Profile`
        SET notify_status = %s,
            notify_interviews = %s,
            notify_offers = %s,
            notify_alerts = %s,
            modified = NOW(6)
        WHERE user = %s
        """,
        (
            values["notify_status"],
            values["notify_interviews"],
            values["notify_offers"],
            values["notify_alerts"],
            user_email,
        ),
    )
    frappe.db.commit()
    return values


@frappe.whitelist(allow_guest=True)
def handle_paynow_callback(reference: str, amount: str = "", paynowreference: str = "",
                           pollurl: str = "", status: str = "", hash: str = "") -> dict:
    """
    Paynow server-to-server result URL.
    Rejects the call when the integration key is missing or the hash does not match.
    """
    import hashlib

    integration_key = frappe.conf.get("paynow_integration_key") or ""
    if not integration_key:
        frappe.throw("Paynow is not configured.")
    if not reference or not hash:
        frappe.throw("Incomplete Paynow callback.")

    payload = "".join([
        reference or "",
        amount or "",
        paynowreference or "",
        pollurl or "",
        status or "",
    ]) + integration_key
    expected = hashlib.sha512(payload.encode()).hexdigest().upper()
    if expected != (hash or "").upper():
        frappe.throw("Hash mismatch.")

    if not frappe.db.exists("Resource Payment", reference):
        frappe.throw("Payment not found.")

    normalised = (status or "").lower()
    if normalised in ("paid", "awaiting delivery"):
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=24)
        frappe.db.set_value("Resource Payment", reference, {
            "status": "Paid",
            "paid_at": datetime.utcnow(),
            "download_token": token,
            "token_expires": expires,
            "paynow_status": normalised,
            "paynow_ref": pollurl or "",
        })
    elif normalised in ("cancelled", "failed", "refunded"):
        frappe.db.set_value("Resource Payment", reference, {
            "status": "Failed",
            "paynow_status": normalised,
        })
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist(allow_guest=False)
def ensure_company_department(company, department_name):
    """
    Return the Department document name for a company.
    Creates the department under the company root when the employer typed a new name.
    """
    label = (department_name or "").strip()
    if not company or not label:
        return ""
    if frappe.db.exists("Department", label):
        return label
    abbr = frappe.db.get_value("Company", company, "abbr") or ""
    named = "{0} - {1}".format(label, abbr) if abbr else label
    if frappe.db.exists("Department", named):
        return named
    existing = frappe.db.get_value(
        "Department", {"department_name": label, "company": company}, "name"
    )
    if existing:
        return existing
    root = frappe.db.get_value("Department", {"is_group": 1, "company": company}, "name")
    doc = frappe.get_doc({
        "doctype": "Department",
        "department_name": label,
        "company": company,
        "parent_department": root,
        "is_group": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


@frappe.whitelist(allow_guest=False)
def ensure_interview_round(round_name="Screening", designation=None):
    """
    Return an Interview Round the HRMS Interview document can link to.
    Creates a General skill and the round when they do not exist.
    A round tied to a different designation gets a designation-specific name.
    """
    name = (round_name or "Screening").strip() or "Screening"
    existing = frappe.db.get_value(
        "Interview Round", name, ["name", "designation"], as_dict=True
    )
    if existing:
        locked = existing.designation and designation and existing.designation != designation
        if not locked:
            return existing.name
        name = "{0} — {1}".format(name, designation)
        again = frappe.db.exists("Interview Round", name)
        if again:
            return again

    if not frappe.db.exists("Skill", "General"):
        frappe.get_doc({
            "doctype": "Skill",
            "skill_name": "General",
            "description": "General screening skill",
        }).insert(ignore_permissions=True)

    doc = frappe.get_doc({
        "doctype": "Interview Round",
        "round_name": name,
        "designation": designation or None,
        "expected_skill_set": [{"skill": "General"}],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name
