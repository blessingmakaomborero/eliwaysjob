"""
Employer verification review, supporting documents, information requests,
and subscription payments. Reads and writes use SQL because these custom
DocTypes do not have Python controllers.
"""
import frappe
from frappe.utils import add_days, getdate, nowdate, now_datetime

PLANS = {
    "Starter": {"amount": 25, "currency": "USD", "days": 30, "open_jobs": 3},
    "Growth": {"amount": 60, "currency": "USD", "days": 30, "open_jobs": 15},
}
DOCUMENT_TYPES = (
    "Certificate of Incorporation",
    "Tax Clearance",
    "Director ID",
    "Proof of Address",
    "Proof of Payment",
    "Other",
)
PAYMENT_METHODS = ("EcoCash", "Bank Transfer", "Paynow", "Cash")


def _ensure_unicode_collation():
    """Portal tables created without a collation pick up utf8mb4_general_ci.
    Frappe tables use utf8mb4_unicode_ci, and MariaDB rejects comparing the two.
    """
    tables = (
        "tabEmployer Profile",
        "tabCandidate Profile",
        "tabEmployer Membership",
        "tabEmployer Document",
        "tabEmployer Information Request",
        "tabEmployer Subscription",
        "tabJob Alert",
        "tabSaved Job",
        "tabPortal Notification",
        "tabCareer Resource",
        "tabResource Download",
        "tabResource Payment",
        "tabSponsor Slot",
    )
    for table in tables:
        mismatched = frappe.db.sql(
            """SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                 AND COLLATION_NAME IS NOT NULL
                 AND COLLATION_NAME <> 'utf8mb4_unicode_ci'""",
            (table,),
        )[0][0]
        if not mismatched:
            continue
        frappe.db.sql(
            "ALTER TABLE `{0}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci".format(table)
        )
    frappe.db.commit()


def ensure_review_doctypes():
    """Create the review DocTypes once. Safe to call on every request."""
    _ensure_unicode_collation()
    if frappe.db.exists("DocType", "Employer Subscription"):
        return
    # Only Administrator may grant the Portal Administrator role on a custom DocType.
    previous = frappe.session.user
    frappe.set_user("Administrator")
    try:
        _create_review_doctypes()
    finally:
        frappe.set_user(previous)


def _create_review_doctypes():
    _create("Employer Document", [
        {"fieldname": "profile", "label": "Employer Profile", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
        {"fieldname": "document_type", "label": "Document Type", "fieldtype": "Select",
         "options": "\n".join(DOCUMENT_TYPES), "reqd": 1, "in_list_view": 1},
        {"fieldname": "file_url", "label": "File URL", "fieldtype": "Data", "reqd": 1},
        {"fieldname": "file_name", "label": "File Name", "fieldtype": "Data", "in_list_view": 1},
        {"fieldname": "status", "label": "Status", "fieldtype": "Select",
         "options": "Submitted\nAccepted\nRejected", "default": "Submitted", "in_list_view": 1},
        {"fieldname": "reviewer_note", "label": "Reviewer Note", "fieldtype": "Small Text"},
    ])
    _create("Employer Information Request", [
        {"fieldname": "profile", "label": "Employer Profile", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
        {"fieldname": "user", "label": "Employer User", "fieldtype": "Data", "in_list_view": 1},
        {"fieldname": "subject", "label": "Subject", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
        {"fieldname": "message", "label": "Message", "fieldtype": "Text", "reqd": 1},
        {"fieldname": "status", "label": "Status", "fieldtype": "Select",
         "options": "Open\nResponded\nClosed", "default": "Open", "in_list_view": 1},
        {"fieldname": "response", "label": "Employer Response", "fieldtype": "Text"},
        {"fieldname": "requested_by", "label": "Requested By", "fieldtype": "Data"},
    ])
    _create("Employer Subscription", [
        {"fieldname": "profile", "label": "Employer Profile", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
        {"fieldname": "user", "label": "Employer User", "fieldtype": "Data", "in_list_view": 1},
        {"fieldname": "plan", "label": "Plan", "fieldtype": "Select", "options": "Starter\nGrowth", "reqd": 1, "in_list_view": 1},
        {"fieldname": "amount", "label": "Amount", "fieldtype": "Float", "reqd": 1},
        {"fieldname": "currency", "label": "Currency", "fieldtype": "Data", "default": "USD"},
        {"fieldname": "status", "label": "Status", "fieldtype": "Select",
         "options": "Pending\nPaid\nFailed", "default": "Pending", "in_list_view": 1},
        {"fieldname": "payment_method", "label": "Payment Method", "fieldtype": "Select",
         "options": "EcoCash\nBank Transfer\nPaynow", "reqd": 1},
        {"fieldname": "payment_reference", "label": "Payment Reference", "fieldtype": "Data", "in_list_view": 1},
        {"fieldname": "payer_phone", "label": "Payer Phone", "fieldtype": "Data"},
        {"fieldname": "paid_at", "label": "Paid At", "fieldtype": "Datetime"},
        {"fieldname": "verified_by", "label": "Verified By", "fieldtype": "Data"},
        {"fieldname": "period_start", "label": "Period Start", "fieldtype": "Date"},
        {"fieldname": "period_end", "label": "Period End", "fieldtype": "Date"},
        {"fieldname": "notes", "label": "Notes", "fieldtype": "Small Text"},
    ])
    frappe.db.commit()


def _create(name, fields):
    if frappe.db.exists("DocType", name):
        return
    doc = frappe.get_doc({
        "doctype": "DocType",
        "name": name,
        "module": "HR",
        "custom": 1,
        "fields": fields,
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Portal Administrator", "read": 1, "write": 1, "create": 1},
        ],
    })
    doc.insert(ignore_permissions=True)


def _row(doctype, values):
    name = frappe.generate_hash(length=10)
    columns = ["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"]
    params = [name, "Administrator", now_datetime(), now_datetime(), "Administrator", 0, 0]
    for key, value in values.items():
        columns.append(key)
        params.append(value)
    placeholders = ", ".join(["%s"] * len(columns))
    col_sql = ", ".join("`{0}`".format(c) for c in columns)
    frappe.db.sql(
        "INSERT INTO `tab{0}` ({1}) VALUES ({2})".format(doctype, col_sql, placeholders),
        params,
    )
    frappe.db.commit()
    return name


def _profile(profile_name):
    rows = frappe.db.sql(
        "SELECT * FROM `tabEmployer Profile` WHERE name = %s",
        (profile_name,), as_dict=True,
    )
    if not rows:
        frappe.throw("Employer Profile not found: {0}".format(profile_name))
    return rows[0]


def _profile_for_user(user):
    rows = frappe.db.sql(
        "SELECT * FROM `tabEmployer Profile` WHERE user = %s LIMIT 1",
        (user,), as_dict=True,
    )
    return rows[0] if rows else None


def _documents(profile_name):
    return frappe.db.sql(
        """SELECT name, document_type, file_url, file_name, status, reviewer_note, creation
           FROM `tabEmployer Document` WHERE profile = %s ORDER BY creation DESC""",
        (profile_name,), as_dict=True,
    )


def _requests(profile_name):
    return frappe.db.sql(
        """SELECT name, subject, message, status, response, requested_by, creation, modified
           FROM `tabEmployer Information Request` WHERE profile = %s ORDER BY creation DESC""",
        (profile_name,), as_dict=True,
    )


def _ensure_subscription_proof_columns():
    """Cash payments store the receipt on the subscription row.

    has_column uses a cached column list, so it can miss a column that is
    already in the table and the following ALTER then fails with 1060.
    """
    columns = {
        "proof_file_url": "varchar(500)",
        "proof_file_name": "varchar(140)",
    }
    added = False
    for field, column_type in columns.items():
        exists = frappe.db.sql(
            """SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE()
                 AND TABLE_NAME = 'tabEmployer Subscription'
                 AND COLUMN_NAME = %s""",
            (field,),
        )[0][0]
        if exists:
            continue
        frappe.db.sql(
            "ALTER TABLE `tabEmployer Subscription` ADD COLUMN `{0}` {1}".format(field, column_type)
        )
        added = True
    if added:
        frappe.db.commit()
    frappe.cache.hdel("table_columns", "tabEmployer Subscription")


def _latest_subscription(profile_name):
    _ensure_subscription_proof_columns()
    rows = frappe.db.sql(
        """SELECT name, plan, amount, currency, status, payment_method, payment_reference,
                  payer_phone, paid_at, verified_by, period_start, period_end, notes, creation,
                  proof_file_url, proof_file_name
           FROM `tabEmployer Subscription` WHERE profile = %s ORDER BY creation DESC LIMIT 1""",
        (profile_name,), as_dict=True,
    )
    return rows[0] if rows else None


def _checks(profile, documents, subscription):
    def filled(*keys):
        return all(profile.get(key) for key in keys)

    paid = bool(subscription and subscription.get("status") == "Paid")
    items = [
        ("onboarding", "Onboarding submitted", bool(profile.get("onboarding_completed"))),
        ("identity", "Company name, industry and size", filled("company_name", "industry", "company_size")),
        ("contact", "Official email, phone, city and country", filled("email", "phone", "city", "country")),
        ("description", "Company description", filled("company_description")),
        ("recruiter", "Primary recruiter name, email and phone",
         filled("primary_recruiter_name", "primary_recruiter_email", "primary_recruiter_phone")),
        ("recruitment_email", "Recruitment notification email", filled("recruitment_email")),
        ("registration", "Company registration number", filled("registration_number")),
        ("company_link", "Linked Frappe company", filled("company")),
        ("documents", "At least one supporting document", len(documents) > 0),
        ("subscription", "Subscription payment verified", paid),
    ]
    return [{"key": key, "label": label, "ok": bool(ok)} for key, label, ok in items]


def _pack(profile):
    documents = _documents(profile.name)
    requests = _requests(profile.name)
    subscription = _latest_subscription(profile.name)
    checks = _checks(profile, documents, subscription)
    return {
        "profile": profile,
        "documents": documents,
        "requests": requests,
        "subscription": subscription,
        "checks": checks,
        "ready": all(item["ok"] for item in checks),
        "plans": [
            {"name": name, **meta} for name, meta in PLANS.items()
        ],
    }


def _employer_filters(status="", search=""):
    filters = []
    params = []
    if status in ("Pending", "Verified", "Rejected", "Suspended"):
        filters.append("p.verification_status COLLATE utf8mb4_unicode_ci = %s")
        params.append(status)
    elif status == "Awaiting payment":
        filters.append(
            """IFNULL((SELECT s.status COLLATE utf8mb4_unicode_ci FROM `tabEmployer Subscription` s
               WHERE s.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci
               ORDER BY s.creation DESC LIMIT 1), 'None') != 'Paid'"""
        )
    elif status == "Information requested":
        filters.append(
            """(SELECT COUNT(*) FROM `tabEmployer Information Request` r
               WHERE r.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci
                 AND r.status COLLATE utf8mb4_unicode_ci = 'Open') > 0"""
        )
    if search:
        safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = "%{0}%".format(safe)
        filters.append(
            "(p.company_name COLLATE utf8mb4_unicode_ci LIKE %s "
            "OR p.email COLLATE utf8mb4_unicode_ci LIKE %s "
            "OR p.user COLLATE utf8mb4_unicode_ci LIKE %s "
            "OR p.industry COLLATE utf8mb4_unicode_ci LIKE %s)"
        )
        params.extend([like, like, like, like])
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    return where, params


@frappe.whitelist(allow_guest=False)
def list_employers_for_review(status="", search="", limit=20, page=1):
    ensure_review_doctypes()
    from eliways_jobs.api import _ensure_duplicate_flag
    _ensure_duplicate_flag()
    try:
        page_no = max(1, int(page or 1))
    except (TypeError, ValueError):
        page_no = 1
    try:
        page_size = min(50, max(1, int(limit or 20)))
    except (TypeError, ValueError):
        page_size = 20
    where, params = _employer_filters(status, search)
    total = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabEmployer Profile` p {where}".format(where=where),
        params,
    )[0][0]
    rows = frappe.db.sql(
        """
        SELECT p.name, p.user, p.company_name, p.email, p.phone, p.industry,
               p.city, p.country, p.verification_status, p.creation,
               p.onboarding_completed, p.company, p.duplicate_flag, p.duplicate_reason,
               (SELECT COUNT(*) FROM `tabEmployer Document` d
                 WHERE d.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci) AS document_count,
               (SELECT COUNT(*) FROM `tabEmployer Information Request` r
                 WHERE r.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci
                   AND r.status COLLATE utf8mb4_unicode_ci = 'Open') AS open_requests,
               (SELECT s.status COLLATE utf8mb4_unicode_ci FROM `tabEmployer Subscription` s
                 WHERE s.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci
                 ORDER BY s.creation DESC LIMIT 1) AS subscription_status,
               (SELECT s.plan COLLATE utf8mb4_unicode_ci FROM `tabEmployer Subscription` s
                 WHERE s.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci
                 ORDER BY s.creation DESC LIMIT 1) AS subscription_plan
        FROM `tabEmployer Profile` p
        {where}
        ORDER BY p.creation DESC
        LIMIT %s OFFSET %s
        """.format(where=where),
        params + [page_size, (page_no - 1) * page_size], as_dict=True,
    )
    count_where, count_params = _employer_filters("", search)
    counts = frappe.db.sql(
        """
        SELECT COUNT(*) AS all_count,
               SUM(p.verification_status COLLATE utf8mb4_unicode_ci = 'Pending') AS pending,
               SUM(p.verification_status COLLATE utf8mb4_unicode_ci = 'Verified') AS verified,
               SUM(p.verification_status COLLATE utf8mb4_unicode_ci = 'Rejected') AS rejected,
               SUM(p.verification_status COLLATE utf8mb4_unicode_ci = 'Suspended') AS suspended,
               SUM(IFNULL((SELECT s.status COLLATE utf8mb4_unicode_ci FROM `tabEmployer Subscription` s
                    WHERE s.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci
                    ORDER BY s.creation DESC LIMIT 1), 'None') != 'Paid') AS awaiting_payment,
               SUM((SELECT COUNT(*) FROM `tabEmployer Information Request` r
                    WHERE r.profile COLLATE utf8mb4_unicode_ci = p.name COLLATE utf8mb4_unicode_ci
                      AND r.status COLLATE utf8mb4_unicode_ci = 'Open') > 0) AS information_requested
        FROM `tabEmployer Profile` p
        {where}
        """.format(where=count_where),
        count_params, as_dict=True,
    )[0]
    def num(value):
        return int(value or 0)
    return {
        "data": rows,
        "total": num(total),
        "page": page_no,
        "page_size": page_size,
        "counts": {
            "All": num(counts.all_count),
            "Pending": num(counts.pending),
            "Awaiting payment": num(counts.awaiting_payment),
            "Information requested": num(counts.information_requested),
            "Verified": num(counts.verified),
            "Rejected": num(counts.rejected),
            "Suspended": num(counts.suspended),
        },
    }


@frappe.whitelist(allow_guest=False)
def get_employer_review(profile_name):
    ensure_review_doctypes()
    return _pack(_profile(profile_name))


@frappe.whitelist(allow_guest=False)
def get_my_employer_review(user):
    ensure_review_doctypes()
    profile = _profile_for_user(user)
    if not profile:
        frappe.throw("Employer profile not found.")
    return _pack(profile)


@frappe.whitelist(allow_guest=False)
def add_employer_document(user, document_type, file_url, file_name=""):
    ensure_review_doctypes()
    if document_type not in DOCUMENT_TYPES:
        frappe.throw("Choose a valid document type.")
    if not file_url:
        frappe.throw("A file is required.")
    profile = _profile_for_user(user)
    if not profile:
        frappe.throw("Employer profile not found.")
    name = _row("Employer Document", {
        "profile": profile.name,
        "document_type": document_type,
        "file_url": file_url,
        "file_name": file_name or file_url,
        "status": "Submitted",
    })
    return {"name": name}


@frappe.whitelist(allow_guest=False)
def review_employer_document(document_name, decision, reviewer_note=""):
    ensure_review_doctypes()
    if decision not in ("Accepted", "Rejected"):
        frappe.throw("Decision must be Accepted or Rejected.")
    rows = frappe.db.sql(
        "SELECT name FROM `tabEmployer Document` WHERE name = %s",
        (document_name,), as_dict=True,
    )
    if not rows:
        frappe.throw("Document not found.")
    frappe.db.sql(
        """UPDATE `tabEmployer Document`
           SET status = %s, reviewer_note = %s, modified = NOW()
           WHERE name = %s""",
        (decision, reviewer_note or "", document_name),
    )
    frappe.db.commit()
    return {"name": document_name, "status": decision}


@frappe.whitelist(allow_guest=False)
def create_information_request(profile_name, subject, message, requested_by=""):
    ensure_review_doctypes()
    subject = (subject or "").strip()
    message = (message or "").strip()
    if not subject or not message:
        frappe.throw("Subject and message are required.")
    profile = _profile(profile_name)
    name = _row("Employer Information Request", {
        "profile": profile.name,
        "user": profile.user,
        "subject": subject,
        "message": message,
        "status": "Open",
        "requested_by": requested_by or frappe.session.user,
    })
    try:
        from eliways_jobs.utils import create_portal_notification
        create_portal_notification(
            user=profile.user,
            subject="More information requested",
            message=message,
            ntype="info",
            link="/employer/verification",
        )
    except Exception:
        frappe.logger("eliways_jobs").error("Could not notify employer about information request")
    return {"name": name}


@frappe.whitelist(allow_guest=False)
def respond_information_request(user, request_name, response):
    ensure_review_doctypes()
    response = (response or "").strip()
    if not response:
        frappe.throw("A response is required.")
    profile = _profile_for_user(user)
    if not profile:
        frappe.throw("Employer profile not found.")
    rows = frappe.db.sql(
        """SELECT name, status FROM `tabEmployer Information Request`
           WHERE name = %s AND profile = %s""",
        (request_name, profile.name), as_dict=True,
    )
    if not rows:
        frappe.throw("Request not found.")
    frappe.db.sql(
        """UPDATE `tabEmployer Information Request`
           SET response = %s, status = 'Responded', modified = NOW()
           WHERE name = %s""",
        (response, request_name),
    )
    frappe.db.commit()
    return {"name": request_name, "status": "Responded"}


@frappe.whitelist(allow_guest=False)
def create_employer_subscription(user, plan, payment_method, payment_reference="", payer_phone="",
                                 proof_file_url="", proof_file_name=""):
    ensure_review_doctypes()
    _ensure_subscription_proof_columns()
    if plan not in PLANS:
        frappe.throw("Choose Starter or Growth.")
    if payment_method not in PAYMENT_METHODS:
        frappe.throw("Choose a payment method.")
    reference = (payment_reference or "").strip()
    proof_url = (proof_file_url or "").strip()
    if payment_method == "Cash":
        if not proof_url.startswith("/"):
            frappe.throw("Upload a photo or scan of the cash receipt before submitting.")
        if len(reference) < 2:
            frappe.throw("Enter the cash receipt number.")
    elif payment_method != "Paynow" and len(reference) < 4:
        frappe.throw("Enter the EcoCash or bank payment reference so an administrator can verify it.")
    profile = _profile_for_user(user)
    if not profile:
        frappe.throw("Employer profile not found.")
    latest = _latest_subscription(profile.name)
    if latest and latest.status == "Paid":
        return {"name": latest.name, "status": "Paid", "already_paid": True}
    if latest and latest.status == "Pending":
        frappe.db.sql(
            """UPDATE `tabEmployer Subscription`
               SET status = 'Failed', notes = 'Replaced by a new payment', modified = NOW()
               WHERE name = %s""",
            (latest.name,),
        )
    meta = PLANS[plan]
    name = _row("Employer Subscription", {
        "profile": profile.name,
        "user": profile.user,
        "plan": plan,
        "amount": meta["amount"],
        "currency": meta["currency"],
        "status": "Pending",
        "payment_method": payment_method,
        "payment_reference": reference,
        "payer_phone": (payer_phone or "").strip(),
        "proof_file_url": proof_url,
        "proof_file_name": (proof_file_name or "").strip(),
    })
    return {
        "name": name,
        "status": "Pending",
        "amount": meta["amount"],
        "currency": meta["currency"],
        "plan": plan,
    }


@frappe.whitelist(allow_guest=False)
def verify_employer_subscription(subscription_name, decision, verified_by="", notes=""):
    ensure_review_doctypes()
    if decision not in ("Paid", "Failed"):
        frappe.throw("Decision must be Paid or Failed.")
    rows = frappe.db.sql(
        "SELECT name, plan, status FROM `tabEmployer Subscription` WHERE name = %s",
        (subscription_name,), as_dict=True,
    )
    if not rows:
        frappe.throw("Subscription not found.")
    if decision == "Paid":
        meta = PLANS.get(rows[0].plan) or PLANS["Starter"]
        start = nowdate()
        end = add_days(start, meta["days"])
        frappe.db.sql(
            """UPDATE `tabEmployer Subscription`
               SET status = 'Paid', paid_at = NOW(), verified_by = %s,
                   period_start = %s, period_end = %s, notes = %s, modified = NOW()
               WHERE name = %s""",
            (verified_by or frappe.session.user, start, end, notes or "", subscription_name),
        )
    else:
        frappe.db.sql(
            """UPDATE `tabEmployer Subscription`
               SET status = 'Failed', notes = %s, verified_by = %s, modified = NOW()
               WHERE name = %s""",
            (notes or "Payment could not be matched.", verified_by or frappe.session.user, subscription_name),
        )
    frappe.db.commit()
    return {"name": subscription_name, "status": decision}


def _subscription_active(sub):
    if not sub or sub.status != "Paid" or not sub.period_end:
        return False
    return getdate(sub.period_end) >= getdate(nowdate())


def _open_job_count(company):
    if not company:
        return 0
    rows = frappe.db.sql(
        "SELECT COUNT(*) AS total FROM `tabJob Opening` WHERE company = %s AND status = 'Open'",
        (company,), as_dict=True,
    )
    return int(rows[0].total or 0)


@frappe.whitelist(allow_guest=False)
def subscription_is_paid(user):
    ensure_review_doctypes()
    profile = _profile_for_user(user)
    if not profile:
        return {"paid": False, "can_publish": False}
    sub = _latest_subscription(profile.name)
    meta = PLANS.get(sub.plan) if sub else None
    limit = meta["open_jobs"] if meta else 0
    count = _open_job_count(profile.company)
    paid = _subscription_active(sub)
    return {
        "paid": paid,
        "can_publish": bool(paid and count < limit),
        "status": sub.status if sub else "None",
        "plan": sub.plan if sub else "",
        "name": sub.name if sub else "",
        "period_end": sub.period_end if sub else None,
        "open_jobs": limit,
        "open_job_count": count,
    }


def assert_subscription_paid(profile_name):
    ensure_review_doctypes()
    sub = _latest_subscription(profile_name)
    if not _subscription_active(sub):
        frappe.throw("Verify the subscription payment before approving this employer.")
