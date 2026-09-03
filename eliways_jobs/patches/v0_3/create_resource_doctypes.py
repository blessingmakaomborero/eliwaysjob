"""
Create three DocTypes for the Career Resources CMS + monetisation:

  1. Career Resource       — CMS article (title, slug, body HTML, meta, status, sponsor)
  2. Resource Download     — premium downloadable file attached to an article
  3. Resource Payment      — payment record when a user buys a premium download

Run with:
  bench --site hrms.localhost execute \
    eliways_jobs.patches.v0_3.create_resource_doctypes.execute
"""
import frappe


def _doctype_exists(name: str) -> bool:
    return frappe.db.exists("DocType", name)


def execute():
    _create_career_resource()
    _create_resource_download()
    _create_resource_payment()
    _seed_sponsor_slot()
    frappe.db.commit()
    print("[create_resource_doctypes] All DocTypes created / verified.")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Career Resource
# ─────────────────────────────────────────────────────────────────────────────
def _create_career_resource():
    if _doctype_exists("Career Resource"):
        print("  Career Resource — already exists, skipping.")
        return

    doc = frappe.get_doc({
        "doctype": "DocType",
        "name":    "Career Resource",
        "module":  "HR",
        "custom":  1,
        "naming_rule": "By fieldname",
        "autoname":    "field:slug",
        "fields": [
            # ── Identity ──────────────────────────────────────────────────
            {"fieldname": "title",        "label": "Title",        "fieldtype": "Data",      "reqd": 1, "in_list_view": 1},
            {"fieldname": "slug",         "label": "Slug",         "fieldtype": "Data",      "reqd": 1, "description": "URL path e.g. cv-writing (lowercase, hyphens only)"},
            {"fieldname": "category",     "label": "Category",     "fieldtype": "Select",    "options": "Job Applications\nInterviews\nGrowth & Planning\nJob Search\nCompensation\nWork & Productivity\nSponsored", "default": "Job Applications"},
            {"fieldname": "status",       "label": "Status",       "fieldtype": "Select",    "options": "Draft\nPublished\nArchived", "default": "Draft", "in_list_view": 1},
            {"fieldname": "column_break_1", "fieldtype": "Column Break"},
            {"fieldname": "read_time",    "label": "Read Time",    "fieldtype": "Data",      "default": "5 min read"},
            {"fieldname": "icon",         "label": "Icon (emoji)", "fieldtype": "Data",      "default": "📄"},
            {"fieldname": "color",        "label": "Card Colour",  "fieldtype": "Select",    "options": "indigo\npurple\nemerald\nblue\namber\nrose", "default": "indigo"},
            {"fieldname": "section_break_meta", "label": "Content", "fieldtype": "Section Break"},
            # ── Content ───────────────────────────────────────────────────
            {"fieldname": "description",  "label": "Short Description", "fieldtype": "Small Text", "reqd": 1, "description": "Shown on the index card"},
            {"fieldname": "intro",        "label": "Intro Paragraph",   "fieldtype": "Text",       "reqd": 1, "description": "Bold intro shown at the top of the article"},
            {"fieldname": "body",         "label": "Article Body (HTML)","fieldtype": "Text Editor","reqd": 1, "description": "Full article content — supports HTML"},
            {"fieldname": "tags",         "label": "Tags",              "fieldtype": "Data",       "description": "Comma-separated e.g. CV,Templates,First job"},
            {"fieldname": "section_break_seo", "label": "SEO", "fieldtype": "Section Break"},
            {"fieldname": "meta_title",   "label": "Meta Title",   "fieldtype": "Data",      "description": "Defaults to title if blank"},
            {"fieldname": "meta_desc",    "label": "Meta Description","fieldtype": "Small Text","description": "160 chars max"},
            {"fieldname": "section_break_monetise", "label": "Monetisation", "fieldtype": "Section Break"},
            # ── Monetisation ─────────────────────────────────────────────
            {"fieldname": "is_sponsored", "label": "Sponsored Article", "fieldtype": "Check",  "default": 0, "description": "Show 'Sponsored' badge and highlighted border"},
            {"fieldname": "sponsor_name", "label": "Sponsor Name",   "fieldtype": "Data",      "depends_on": "eval:doc.is_sponsored"},
            {"fieldname": "sponsor_logo", "label": "Sponsor Logo URL","fieldtype": "Data",     "depends_on": "eval:doc.is_sponsored"},
            {"fieldname": "sponsor_url",  "label": "Sponsor URL",    "fieldtype": "Data",      "depends_on": "eval:doc.is_sponsored"},
            {"fieldname": "sponsor_cta",  "label": "Sponsor CTA Text","fieldtype": "Data",     "depends_on": "eval:doc.is_sponsored", "default": "View Sponsor"},
            {"fieldname": "column_break_2", "fieldtype": "Column Break"},
            {"fieldname": "has_sidebar_ad","label": "Show Sidebar Ad","fieldtype": "Check",    "default": 0},
            {"fieldname": "ad_company",   "label": "Ad Company Name","fieldtype": "Data",      "depends_on": "eval:doc.has_sidebar_ad"},
            {"fieldname": "ad_tagline",   "label": "Ad Tagline",     "fieldtype": "Small Text","depends_on": "eval:doc.has_sidebar_ad"},
            {"fieldname": "ad_logo",      "label": "Ad Logo URL",    "fieldtype": "Data",      "depends_on": "eval:doc.has_sidebar_ad"},
            {"fieldname": "ad_url",       "label": "Ad URL",         "fieldtype": "Data",      "depends_on": "eval:doc.has_sidebar_ad"},
            {"fieldname": "ad_cta",       "label": "Ad CTA Text",    "fieldtype": "Data",      "depends_on": "eval:doc.has_sidebar_ad", "default": "View Jobs"},
            # ── Navigation ────────────────────────────────────────────────
            {"fieldname": "section_break_nav", "label": "Navigation", "fieldtype": "Section Break"},
            {"fieldname": "prev_slug",    "label": "Previous Article Slug","fieldtype": "Data"},
            {"fieldname": "prev_title",   "label": "Previous Article Title","fieldtype": "Data"},
            {"fieldname": "next_slug",    "label": "Next Article Slug","fieldtype": "Data"},
            {"fieldname": "next_title",   "label": "Next Article Title","fieldtype": "Data"},
            # ── Timestamps ───────────────────────────────────────────────
            {"fieldname": "published_at", "label": "Published At",  "fieldtype": "Date",      "read_only": 0},
            {"fieldname": "modified_at",  "label": "Last Modified", "fieldtype": "Datetime",  "read_only": 1},
        ],
        "permissions": [
            {"role": "System Manager",     "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Portal Administrator","read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All",               "read": 1},   # public read for published articles
        ],
    })
    doc.insert(ignore_permissions=True)
    print("  Career Resource — created.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Resource Download
# ─────────────────────────────────────────────────────────────────────────────
def _create_resource_download():
    if _doctype_exists("Resource Download"):
        print("  Resource Download — already exists, skipping.")
        return

    doc = frappe.get_doc({
        "doctype": "DocType",
        "name":    "Resource Download",
        "module":  "HR",
        "custom":  1,
        "fields": [
            {"fieldname": "title",         "label": "Download Title",  "fieldtype": "Data",   "reqd": 1, "in_list_view": 1},
            {"fieldname": "resource",      "label": "Career Resource", "fieldtype": "Link",   "options": "Career Resource", "reqd": 1, "in_list_view": 1},
            {"fieldname": "description",   "label": "Description",     "fieldtype": "Small Text"},
            {"fieldname": "file_url",      "label": "File URL",        "fieldtype": "Data",   "reqd": 1, "description": "Frappe file attachment URL or external link"},
            {"fieldname": "file_type",     "label": "File Type",       "fieldtype": "Select", "options": "PDF\nDOCX\nXLSX\nZIP", "default": "PDF"},
            {"fieldname": "is_free",       "label": "Free Download",   "fieldtype": "Check",  "default": 0, "in_list_view": 1},
            {"fieldname": "price_usd",     "label": "Price (USD)",     "fieldtype": "Currency","default": 2, "depends_on": "eval:!doc.is_free"},
            {"fieldname": "price_zwg",     "label": "Price (ZWG)",     "fieldtype": "Currency","default": 0, "depends_on": "eval:!doc.is_free", "description": "Optional ZWG equivalent"},
            {"fieldname": "thumbnail_url", "label": "Preview Image URL","fieldtype": "Data"},
            {"fieldname": "is_active",     "label": "Active",          "fieldtype": "Check",  "default": 1},
        ],
        "permissions": [
            {"role": "System Manager",      "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Portal Administrator","read": 1, "write": 1, "create": 1},
            {"role": "All",                "read": 1},
        ],
    })
    doc.insert(ignore_permissions=True)
    print("  Resource Download — created.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Resource Payment
# ─────────────────────────────────────────────────────────────────────────────
def _create_resource_payment():
    if _doctype_exists("Resource Payment"):
        print("  Resource Payment — already exists, skipping.")
        return

    doc = frappe.get_doc({
        "doctype": "DocType",
        "name":    "Resource Payment",
        "module":  "HR",
        "custom":  1,
        "fields": [
            {"fieldname": "user_email",    "label": "Buyer Email",      "fieldtype": "Data",   "reqd": 1, "in_list_view": 1},
            {"fieldname": "download",      "label": "Resource Download","fieldtype": "Link",   "options": "Resource Download", "reqd": 1, "in_list_view": 1},
            {"fieldname": "amount_usd",    "label": "Amount (USD)",     "fieldtype": "Currency","reqd": 1},
            {"fieldname": "currency",      "label": "Currency",         "fieldtype": "Select", "options": "USD\nZWG", "default": "USD"},
            {"fieldname": "status",        "label": "Status",           "fieldtype": "Select", "options": "Pending\nPaid\nFailed\nRefunded", "default": "Pending", "in_list_view": 1},
            {"fieldname": "payment_method","label": "Payment Method",   "fieldtype": "Select", "options": "Paynow\nEcoCash\nManual\nFree"},
            {"fieldname": "paynow_ref",    "label": "Paynow Reference", "fieldtype": "Data",   "description": "Paynow poll URL or reference"},
            {"fieldname": "paynow_status", "label": "Paynow Raw Status","fieldtype": "Small Text"},
            {"fieldname": "paid_at",       "label": "Paid At",          "fieldtype": "Datetime"},
            {"fieldname": "download_token","label": "Download Token",   "fieldtype": "Data",   "description": "Short-lived token for secure file download"},
            {"fieldname": "token_expires", "label": "Token Expires",    "fieldtype": "Datetime"},
            {"fieldname": "ip_address",    "label": "Buyer IP",         "fieldtype": "Data",   "read_only": 1},
        ],
        "permissions": [
            {"role": "System Manager",      "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Portal Administrator","read": 1, "write": 1},
        ],
    })
    doc.insert(ignore_permissions=True)
    print("  Resource Payment — created.")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Seed a Sponsor Slot DocType (simple lookup for sidebar ad inventory)
# ─────────────────────────────────────────────────────────────────────────────
def _seed_sponsor_slot():
    if _doctype_exists("Sponsor Slot"):
        print("  Sponsor Slot — already exists, skipping.")
        return

    doc = frappe.get_doc({
        "doctype": "DocType",
        "name":    "Sponsor Slot",
        "module":  "HR",
        "custom":  1,
        "fields": [
            {"fieldname": "company_name",  "label": "Company Name",    "fieldtype": "Data",   "reqd": 1, "in_list_view": 1},
            {"fieldname": "slot_type",     "label": "Slot Type",       "fieldtype": "Select", "options": "Sidebar Ad\nFeatured Article\nHomepage Banner", "in_list_view": 1},
            {"fieldname": "logo_url",      "label": "Logo URL",        "fieldtype": "Data"},
            {"fieldname": "tagline",       "label": "Tagline",         "fieldtype": "Small Text"},
            {"fieldname": "target_url",    "label": "Target URL",      "fieldtype": "Data"},
            {"fieldname": "cta_text",      "label": "CTA Text",        "fieldtype": "Data",   "default": "Learn More"},
            {"fieldname": "is_active",     "label": "Active",          "fieldtype": "Check",  "default": 1, "in_list_view": 1},
            {"fieldname": "starts_on",     "label": "Starts On",       "fieldtype": "Date"},
            {"fieldname": "ends_on",       "label": "Ends On",         "fieldtype": "Date"},
            {"fieldname": "monthly_fee_usd","label": "Monthly Fee (USD)","fieldtype": "Currency"},
            {"fieldname": "notes",         "label": "Notes",           "fieldtype": "Small Text"},
        ],
        "permissions": [
            {"role": "System Manager",      "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Portal Administrator","read": 1, "write": 1, "create": 1},
        ],
    })
    doc.insert(ignore_permissions=True)
    print("  Sponsor Slot — created.")
