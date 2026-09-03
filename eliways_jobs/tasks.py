"""
Scheduled tasks for eliways_jobs.
Registered in hooks.py under scheduler_events.

Performance notes
─────────────────
close_expired_jobs:
  Uses idx_jo_status_closes_on (status, closes_on) — index range scan, no
  table scan even with millions of jobs. Processes up to 500 per run with
  a single db.commit() at the end instead of one per job to reduce lock
  contention on busy databases.

send_job_alerts (Daily / Weekly):
  Old approach was N+1: one frappe.get_list("Job Opening") per alert (up to
  500 queries per scheduler run). New approach:

    1. Load all active alerts for the frequency in one query.
    2. Find the oldest `last_sent` date across all alerts to determine the
       global "since" window.
    3. Fetch ALL new jobs in that window in a SINGLE query (+ optional
       employment_type refinement).
    4. Filter each alert's matches in Python (O(alerts × jobs) but jobs is
       bounded to the new-jobs window, typically small).
    5. Bulk-update last_sent for all successfully emailed alerts in one
       db.sql UPDATE … WHERE name IN (…) call.

  This reduces DB round-trips from O(N alerts) to O(1) for the job fetch
  plus O(1) for the bulk update, regardless of how many alerts are active.
"""
import frappe
from frappe.utils import today, add_days
from eliways_jobs.utils import safe_log, send_portal_email


# ─── Task 1: Auto-close expired Job Openings ──────────────────────────────────

def close_expired_jobs():
    """
    Daily: Find Job Openings whose closes_on < today and status = Open.
    Uses idx_jo_status_closes_on composite index.
    """
    try:
        today_date = today()
        expired = frappe.get_list(
            "Job Opening",
            filters=[
                ["status",    "=",   "Open"],
                ["closes_on", "<",   today_date],
                ["closes_on", "!=",  ""],
                ["closes_on", "is",  "set"],
            ],
            fields=["name", "job_title", "company", "closes_on"],
            limit=500,  # raised from 200; index scan keeps this fast
        )

        if not expired:
            frappe.logger("eliways_jobs").info("[close_expired_jobs] Nothing to close.")
            return

        closed_names = []
        for job in expired:
            try:
                doc = frappe.get_doc("Job Opening", job["name"])
                doc.status = "Closed"
                doc.save(ignore_permissions=True)
                closed_names.append(job["name"])
                frappe.logger("eliways_jobs").info(
                    f"[close_expired_jobs] Closed: {job['name']} ({job['job_title']})"
                )
            except Exception as e:
                safe_log("close_expired_jobs.single", e)

        # Single commit after all saves to reduce lock round-trips
        frappe.db.commit()
        frappe.logger("eliways_jobs").info(
            f"[close_expired_jobs] Done. Closed {len(closed_names)} job(s)."
        )
    except Exception as e:
        safe_log("close_expired_jobs", e)


# ─── Task 2: Daily / Weekly job alert digests ─────────────────────────────────

def send_daily_job_alerts():
    """Daily: send job alert digests to candidates with frequency = Daily."""
    _send_job_alerts(frequency="Daily")


def send_weekly_job_alerts():
    """Weekly: send job alert digests to candidates with frequency = Weekly."""
    _send_job_alerts(frequency="Weekly")


def _send_job_alerts(frequency: str):
    """
    Batch-optimised job alert dispatcher.

    Single DB round-trip for jobs instead of one per alert (old N+1 pattern).
    """
    try:
        # ── 1. Load all active alerts for this frequency ───────────────────────
        alerts = frappe.get_list(
            "Job Alert",
            filters=[["frequency", "=", frequency], ["active", "=", 1]],
            fields=["name", "user", "keywords", "location", "employment_type", "last_sent"],
            limit=1000,   # raised; idx_jal_freq_active makes this an index scan
        )

        if not alerts:
            frappe.logger("eliways_jobs").info(
                f"[send_job_alerts] {frequency}: no active alerts."
            )
            return

        # ── 2. Find the oldest since-date across all alerts ────────────────────
        #  This is the widest window we need to query. Each alert will filter
        #  further by its own last_sent in Python — cheap O(n) on a small list.
        oldest_since = None
        for alert in alerts:
            last = alert.get("last_sent")
            since = str(last) if last else str(add_days(today(), -7))
            if oldest_since is None or since < oldest_since:
                oldest_since = since

        # ── 3. Single bulk query for all new jobs in the window ────────────────
        #  Uses idx_jo_status_creation (status, creation) — index range scan.
        #  We fetch all employment_type values and filter per-alert in Python
        #  to avoid one query per employment_type combination.
        all_new_jobs = frappe.get_list(
            "Job Opening",
            filters=[
                ["status",   "=", "Open"],
                ["creation", ">", oldest_since],
            ],
            fields=["name", "job_title", "company", "job_location",
                    "employment_type", "closes_on", "creation"],
            order_by="creation desc",
            limit=500,  # cap per run; enough for a day/week of new jobs
        )

        portal_url = frappe.conf.get("portal_url", "http://localhost:3000")
        today_str  = today()
        sent_names: list[str] = []

        # ── 4. Match each alert against the pre-fetched job list ──────────────
        for alert in alerts:
            try:
                last  = alert.get("last_sent")
                since = str(last) if last else str(add_days(today(), -7))
                keywords  = (alert.get("keywords")       or "").lower().split()
                location  = (alert.get("location")       or "").lower()
                emp_type  = (alert.get("employment_type") or "").lower()

                matched = []
                for job in all_new_jobs:
                    # Respect per-alert since date
                    if str(job.get("creation", "")) <= since:
                        continue
                    # employment_type filter
                    if emp_type and (job.get("employment_type") or "").lower() != emp_type:
                        continue
                    # Keyword match (any keyword in job text)
                    text = " ".join([
                        job.get("job_title",    "") or "",
                        job.get("company",      "") or "",
                        job.get("job_location", "") or "",
                    ]).lower()
                    if keywords and not any(kw in text for kw in keywords):
                        continue
                    # Location filter
                    if location and location not in (job.get("job_location") or "").lower():
                        continue
                    matched.append(job)

                if not matched:
                    continue

                user_email = alert.get("user") or ""
                if not user_email:
                    continue

                jobs_ctx = [
                    {
                        "id":       j["name"],
                        "title":    j["job_title"],
                        "company":  j["company"],
                        "location": j.get("job_location") or "",
                        "type":     j.get("employment_type") or "",
                        "closes":   str(j.get("closes_on") or ""),
                    }
                    for j in matched
                ]

                sent = send_portal_email(
                    to=user_email,
                    subject=f"New Jobs Matching '{alert.get('keywords','')}' – {len(matched)} Available",
                    template="job_alert_digest",
                    context={
                        "keywords":    alert.get("keywords", ""),
                        "jobs":        jobs_ctx,
                        "portal_link": f"{portal_url}/jobs",
                    },
                )

                if sent:
                    sent_names.append(alert["name"])

            except Exception as e:
                safe_log(f"send_job_alerts.alert.{alert.get('name','?')}", e)

        # ── 5. Bulk-update last_sent in a single query ─────────────────────────
        if sent_names:
            placeholders = ", ".join(["%s"] * len(sent_names))
            frappe.db.sql(
                f"UPDATE `tabJob Alert` SET last_sent = %s WHERE name IN ({placeholders})",
                [today_str] + sent_names,
            )
            frappe.db.commit()

        frappe.logger("eliways_jobs").info(
            f"[send_job_alerts] {frequency}: processed {len(alerts)} alerts, "
            f"sent {len(sent_names)} digest(s)."
        )
    except Exception as e:
        safe_log(f"send_job_alerts.{frequency}", e)


# ─── Manual trigger helpers (for testing) ─────────────────────────────────────

def run_all_tasks():
    """Run all tasks manually. Useful for testing from bench console."""
    print("Running close_expired_jobs...")
    close_expired_jobs()
    print("Running send_daily_job_alerts...")
    send_daily_job_alerts()
    print("Done.")
