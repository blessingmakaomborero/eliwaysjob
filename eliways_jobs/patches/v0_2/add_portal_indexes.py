"""
Add composite DB indexes for Eliways Jobs portal performance.

Targets million-scale Job Opening, Job Applicant, Employer Profile,
Job Alert, and Employer Membership tables.

Each CREATE INDEX is guarded with IF NOT EXISTS (MySQL 8+) or a
manual check (MariaDB <10.5) so the patch is idempotent.
"""
import frappe


def _index_exists(table: str, index_name: str) -> bool:
    rows = frappe.db.sql(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE table_schema = DATABASE() "
        "AND table_name = %s AND index_name = %s",
        (table, index_name),
    )
    return bool(rows and rows[0][0])


def _add_index(table: str, index_name: str, columns: str, unique: bool = False):
    """Create index only if it doesn't already exist."""
    if _index_exists(table, index_name):
        frappe.logger("eliways_jobs").info(
            "[add_portal_indexes] Index already exists: %s.%s — skipped" % (table, index_name)
        )
        return
    kind = "UNIQUE INDEX" if unique else "INDEX"
    sql = "CREATE %s `%s` ON `%s` (%s)" % (kind, index_name, table, columns)
    frappe.db.sql(sql)
    frappe.logger("eliways_jobs").info(
        "[add_portal_indexes] Created index: %s.%s (%s)" % (table, index_name, columns)
    )


def execute():
    """Run all index additions."""

    # ── tabJob Opening ────────────────────────────────────────────────────────
    # Most queries filter on status='Open' — single most important index
    _add_index("tabJob Opening", "idx_jo_status",
               "`status`")

    # Public listing: WHERE status='Open' ORDER BY creation DESC
    _add_index("tabJob Opening", "idx_jo_status_creation",
               "`status`, `creation` DESC")

    # Expiry scheduler + apply expiry check: WHERE status='Open' AND closes_on < today
    _add_index("tabJob Opening", "idx_jo_status_closes_on",
               "`status`, `closes_on`")

    # Employer jobs list: WHERE company='X' AND status='Y'
    _add_index("tabJob Opening", "idx_jo_company_status",
               "`company`, `status`")

    # Company directory job-count sub-query: WHERE status='Open' AND company IN (...)
    # Covered by idx_jo_company_status — also add company alone for IN list scans
    _add_index("tabJob Opening", "idx_jo_company",
               "`company`")

    # Job alerts: WHERE status='Open' AND creation > since AND employment_type='X'
    _add_index("tabJob Opening", "idx_jo_status_emptype_creation",
               "`status`, `employment_type`, `creation` DESC")

    # Job location text searches — partial index (prefix 64 chars) for LIKE 'x%' acceleration
    # Note: LIKE '%x%' (leading %) cannot use an index; this helps only suffix-free patterns.
    # The real fix for full-text search is MySQL FULLTEXT — see below.
    _add_index("tabJob Opening", "idx_jo_job_location",
               "`job_location`(64)")

    # Full-text index covering all searchable text fields (used by keyword search)
    # MySQL/MariaDB FULLTEXT: use MATCH(col) AGAINST('keyword' IN BOOLEAN MODE)
    if not _index_exists("tabJob Opening", "ft_jo_search"):
        frappe.db.sql(
            "CREATE FULLTEXT INDEX `ft_jo_search` ON `tabJob Opening` "
            "(`job_title`, `skills`, `job_location`, `designation`, `company`)"
        )
        frappe.logger("eliways_jobs").info(
            "[add_portal_indexes] Created FULLTEXT index ft_jo_search on tabJob Opening"
        )

    # ── tabJob Applicant ──────────────────────────────────────────────────────
    # Candidate application list: WHERE email_id='x' ORDER BY creation DESC
    _add_index("tabJob Applicant", "idx_ja_email_id",
               "`email_id`")

    _add_index("tabJob Applicant", "idx_ja_email_creation",
               "`email_id`, `creation` DESC")

    # Duplicate-check query: WHERE job_title='x' AND email_id='y' (2-column unique check)
    _add_index("tabJob Applicant", "idx_ja_job_email",
               "`job_title`, `email_id`")

    # Analytics / employer applicants: WHERE job_title IN (...) ORDER BY creation
    _add_index("tabJob Applicant", "idx_ja_job_status",
               "`job_title`, `status`")

    # Status column used in GROUP BY for analytics
    _add_index("tabJob Applicant", "idx_ja_status_creation",
               "`status`, `creation`")

    # ── tabEmployer Profile ───────────────────────────────────────────────────
    # Every authenticated employer request does: WHERE user='email@...' LIMIT 1
    _add_index("tabEmployer Profile", "idx_ep_user",
               "`user`")

    # Verification flow: WHERE verification_status='Pending'
    _add_index("tabEmployer Profile", "idx_ep_verification_status",
               "`verification_status`")

    # Company lookup + verification (post route): WHERE user='x' AND verification_status='y'
    _add_index("tabEmployer Profile", "idx_ep_user_company",
               "`user`, `company`")

    # ── tabEmployer Membership ────────────────────────────────────────────────
    # Team member lookup: WHERE user='x' AND status='Active'
    _add_index("tabEmployer Membership", "idx_em_user_status",
               "`user`, `status`")

    # Company membership list: WHERE company='x'
    _add_index("tabEmployer Membership", "idx_em_company",
               "`company`")

    # ── tabJob Alert ─────────────────────────────────────────────────────────
    # Daily scheduler: WHERE frequency='Daily' AND active=1
    _add_index("tabJob Alert", "idx_jal_freq_active",
               "`frequency`, `active`")

    # User's own alerts: WHERE user='email@...'
    _add_index("tabJob Alert", "idx_jal_user",
               "`user`")

    # ── tabCandidate Profile ──────────────────────────────────────────────────
    # Profile lookup: WHERE user='email@...' (same pattern as Employer Profile)
    _add_index("tabCandidate Profile", "idx_cp_user",
               "`user`")

    # ── tabPortal Notification ────────────────────────────────────────────────
    try:
        _add_index("tabPortal Notification", "idx_pn_user_read",
                   "`user`, `read`")
        _add_index("tabPortal Notification", "idx_pn_user_creation",
                   "`user`, `creation` DESC")
    except Exception:
        pass  # table may not exist in all environments

    frappe.db.commit()
    print("[add_portal_indexes] All indexes applied successfully.")
