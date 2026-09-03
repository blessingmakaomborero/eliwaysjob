"""Add last_sent field to Job Alert DocType."""
import frappe


def execute():
    if not frappe.db.has_column("Job Alert", "last_sent"):
        frappe.db.add_column("Job Alert", "last_sent", "DATE")
        frappe.db.commit()
        print("Added last_sent column to Job Alert.")
