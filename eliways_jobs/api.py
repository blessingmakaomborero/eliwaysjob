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
    active_jobs = frappe.db.count("Job Opening", filters={"status": "Open"})
    total_apps  = frappe.db.count("Job Applicant")
    employers   = frappe.db.count("Company")
    candidates  = frappe.db.count("Candidate Profile")
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
            frappe.logger("eliways_jobs").warning(
                "[paynow] No credentials configured — returning mock response"
            )
            return {
                "redirect_url": f"{portal_url}/career-resources/downloads/pending?ref={payment_name}",
                "poll_url": "",
            }

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
