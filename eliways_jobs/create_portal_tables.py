"""
Directly create the portal DocType tables that Frappe migrate misses
because they are custom=1 DocTypes created via patches.
"""
import frappe


def execute():
    tables = {
        "tabEmployer Profile": """
            CREATE TABLE IF NOT EXISTS `tabEmployer Profile` (
              `name`                varchar(140) NOT NULL,
              `creation`            datetime(6) DEFAULT NULL,
              `modified`            datetime(6) DEFAULT NULL,
              `modified_by`         varchar(140) DEFAULT NULL,
              `owner`               varchar(140) DEFAULT NULL,
              `docstatus`           int(1) NOT NULL DEFAULT 0,
              `idx`                 int(8) NOT NULL DEFAULT 0,
              `user`                varchar(140) DEFAULT NULL,
              `company_name`        varchar(140) DEFAULT NULL,
              `company`             varchar(140) DEFAULT NULL,
              `email`               varchar(140) DEFAULT NULL,
              `phone`               varchar(50) DEFAULT NULL,
              `industry`            varchar(140) DEFAULT NULL,
              `website`             varchar(255) DEFAULT NULL,
              `country`             varchar(140) DEFAULT NULL,
              `city`                varchar(140) DEFAULT NULL,
              `verification_status` varchar(50) DEFAULT 'Pending',
              `onboarding_completed` int(1) DEFAULT 0,
              `onboarding_step`     int(8) DEFAULT 1,
              `duplicate_flag`      int(1) DEFAULT 0,
              PRIMARY KEY (`name`),
              KEY `modified` (`modified`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "tabCandidate Profile": """
            CREATE TABLE IF NOT EXISTS `tabCandidate Profile` (
              `name`           varchar(140) NOT NULL,
              `creation`       datetime(6) DEFAULT NULL,
              `modified`       datetime(6) DEFAULT NULL,
              `modified_by`    varchar(140) DEFAULT NULL,
              `owner`          varchar(140) DEFAULT NULL,
              `docstatus`      int(1) NOT NULL DEFAULT 0,
              `idx`            int(8) NOT NULL DEFAULT 0,
              `user`           varchar(140) DEFAULT NULL,
              `full_name`      varchar(255) DEFAULT NULL,
              `phone`          varchar(50) DEFAULT NULL,
              `location`       varchar(255) DEFAULT NULL,
              `bio`            text DEFAULT NULL,
              `skills`         text DEFAULT NULL,
              `resume_file`    varchar(255) DEFAULT NULL,
              `linkedin_url`   varchar(255) DEFAULT NULL,
              `website`        varchar(255) DEFAULT NULL,
              `profile_complete` int(1) DEFAULT 0,
              PRIMARY KEY (`name`),
              KEY `modified` (`modified`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "tabEmployer Membership": """
            CREATE TABLE IF NOT EXISTS `tabEmployer Membership` (
              `name`             varchar(140) NOT NULL,
              `creation`         datetime(6) DEFAULT NULL,
              `modified`         datetime(6) DEFAULT NULL,
              `modified_by`      varchar(140) DEFAULT NULL,
              `owner`            varchar(140) DEFAULT NULL,
              `docstatus`        int(1) NOT NULL DEFAULT 0,
              `idx`              int(8) NOT NULL DEFAULT 0,
              `user`             varchar(140) DEFAULT NULL,
              `employer_profile` varchar(140) DEFAULT NULL,
              `company`          varchar(140) DEFAULT NULL,
              `member_role`      varchar(50) DEFAULT 'Recruiter',
              `status`           varchar(50) DEFAULT 'Active',
              `invited_by`       varchar(140) DEFAULT NULL,
              PRIMARY KEY (`name`),
              KEY `modified` (`modified`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "tabJob Alert": """
            CREATE TABLE IF NOT EXISTS `tabJob Alert` (
              `name`            varchar(140) NOT NULL,
              `creation`        datetime(6) DEFAULT NULL,
              `modified`        datetime(6) DEFAULT NULL,
              `modified_by`     varchar(140) DEFAULT NULL,
              `owner`           varchar(140) DEFAULT NULL,
              `docstatus`       int(1) NOT NULL DEFAULT 0,
              `idx`             int(8) NOT NULL DEFAULT 0,
              `user`            varchar(140) DEFAULT NULL,
              `keywords`        varchar(255) DEFAULT NULL,
              `location`        varchar(255) DEFAULT NULL,
              `employment_type` varchar(140) DEFAULT NULL,
              `frequency`       varchar(50) DEFAULT 'Daily',
              `active`          int(1) DEFAULT 1,
              `last_sent`       date DEFAULT NULL,
              PRIMARY KEY (`name`),
              KEY `modified` (`modified`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "tabSaved Job": """
            CREATE TABLE IF NOT EXISTS `tabSaved Job` (
              `name`        varchar(140) NOT NULL,
              `creation`    datetime(6) DEFAULT NULL,
              `modified`    datetime(6) DEFAULT NULL,
              `modified_by` varchar(140) DEFAULT NULL,
              `owner`       varchar(140) DEFAULT NULL,
              `docstatus`   int(1) NOT NULL DEFAULT 0,
              `idx`         int(8) NOT NULL DEFAULT 0,
              `user`        varchar(140) DEFAULT NULL,
              `job_opening` varchar(140) DEFAULT NULL,
              PRIMARY KEY (`name`),
              KEY `modified` (`modified`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        "tabPortal Notification": """
            CREATE TABLE IF NOT EXISTS `tabPortal Notification` (
              `name`        varchar(140) NOT NULL,
              `creation`    datetime(6) DEFAULT NULL,
              `modified`    datetime(6) DEFAULT NULL,
              `modified_by` varchar(140) DEFAULT NULL,
              `owner`       varchar(140) DEFAULT NULL,
              `docstatus`   int(1) NOT NULL DEFAULT 0,
              `idx`         int(8) NOT NULL DEFAULT 0,
              `user`        varchar(140) DEFAULT NULL,
              `subject`     varchar(255) DEFAULT NULL,
              `message`     text DEFAULT NULL,
              `type`        varchar(50) DEFAULT 'info',
              `read`        int(1) DEFAULT 0,
              `link`        varchar(255) DEFAULT NULL,
              PRIMARY KEY (`name`),
              KEY `modified` (`modified`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    }

    for table_name, sql in tables.items():
        try:
            frappe.db.sql(sql)
            print(f"Created table: {table_name}")
        except Exception as e:
            print(f"Error creating {table_name}: {e}")

    frappe.db.commit()
    print("All portal tables created.")
