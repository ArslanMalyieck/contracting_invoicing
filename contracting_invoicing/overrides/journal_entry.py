# Copyright (c) 2026, Arslan
"""Journal Entry guards: system-generated contracting JEs cancel only via
their source document's cancellation chain, never manually."""

import frappe
from frappe import _


def on_cancel(doc, method=None):
    if not doc.get("contracting_purpose"):
        return
    if frappe.flags.get("contracting_system_cancel"):
        return
    ref_dt = doc.get("contracting_reference_doctype")
    ref_name = doc.get("contracting_reference_name")
    if ref_dt and ref_name and frappe.db.get_value(ref_dt, ref_name, "docstatus") == 1:
        frappe.throw(
            _("This Journal Entry ({0}) is managed by Contracting Invoicing and is "
              "referenced by {1} {2}, which is still submitted. Cancel that document "
              "instead - this entry will cancel with it automatically.").format(
                _(doc.contracting_purpose), _(ref_dt), ref_name
            ),
            title=_("Managed Entry"),
        )


def on_trash(doc, method=None):
    if doc.get("contracting_purpose") and not frappe.flags.get("contracting_system_cancel"):
        frappe.throw(
            _("System-generated contracting entries cannot be deleted manually."),
            title=_("Managed Entry"),
        )
