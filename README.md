# eliways_jobs — Custom Frappe App

Custom Frappe/HRMS integration app for the [Eliways Jobs Portal](https://github.com/blessingmakaomborero/job-portal).

## What this app does

- **DocTypes**: Candidate Profile, Employer Profile, Employer Membership, Job Alert, Saved Job, Portal Notification, Career Resource, Resource Download, Resource Payment, Sponsor Slot
- **Scheduled tasks**: Auto-close expired jobs daily, send job alert digests (daily/weekly)
- **Document hooks**: Notify candidates on application status changes, notify employers on new applications, send interview and offer notifications
- **API methods**: Whitelisted BFF endpoints called by the Next.js portal (job counts, admin analytics, CMS resources, Paynow payment integration)
- **DB indexes**: 20 composite indexes for million-scale performance (v0_2 patch)

## Installation

```bash
# On your Frappe bench
cd /path/to/frappe-bench

# Get the app
bench get-app eliways_jobs https://github.com/blessingmakaomborero/eliways-jobs-frappe-app.git

# Install on your site
bench --site your-site.com install-app eliways_jobs

# Run migrations (creates DocTypes + indexes)
bench --site your-site.com migrate
```

## Patches

| Patch | What it does |
|---|---|
| `v0_1/add_last_sent_to_job_alert` | Adds `last_sent` column to Job Alert |
| `v0_2/add_portal_indexes` | Creates 20 composite DB indexes for performance |
| `v0_3/create_resource_doctypes` | Creates Career Resource, Resource Download, Resource Payment, Sponsor Slot DocTypes |

## Site config keys

Set these with `bench set-config`:

```bash
bench --site your-site.com set-config portal_url https://jobs.eliwayssolutions.co.zw
bench --site your-site.com set-config paynow_integration_id YOUR_ID
bench --site your-site.com set-config paynow_integration_key YOUR_KEY
```

## Companion app

The Next.js portal that consumes this app:  
→ https://github.com/blessingmakaomborero/job-portal
