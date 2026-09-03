"""
Eliways Jobs Portal — Frappe hooks
"""

app_name          = "eliways_jobs"
app_title         = "Eliways Jobs"
app_publisher     = "Eliways Solutions"
app_description   = "Custom portal integration for Eliways Jobs"
app_email         = "dev@eliwayssolutions.co.zw"
app_license       = "MIT"

# ─── Document Event Hooks ────────────────────────────────────────────────────
# These fire on HRMS DocType events to create Portal Notifications and
# trigger email alerts WITHOUT modifying HRMS core.

doc_events = {
    "Job Applicant": {
        "after_insert": "eliways_jobs.events.applicant.after_insert",
        "on_update":    "eliways_jobs.events.applicant.on_update",
    },
    "Interview": {
        "after_insert": "eliways_jobs.events.interview.after_insert",
        "on_update":    "eliways_jobs.events.interview.on_update",
    },
    "Job Offer": {
        "after_insert": "eliways_jobs.events.offer.after_insert",
    },
    "Employer Profile": {
        "on_update": "eliways_jobs.events.employer.on_update",
    },
}

# ─── Scheduled Tasks ─────────────────────────────────────────────────────────

scheduler_events = {
    "daily": [
        "eliways_jobs.tasks.close_expired_jobs",
        "eliways_jobs.tasks.send_daily_job_alerts",
    ],
    "weekly": [
        "eliways_jobs.tasks.send_weekly_job_alerts",
    ],
}
