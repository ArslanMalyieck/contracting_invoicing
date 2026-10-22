# Copyright (c) 2026, Arslan
"""Retention Ledger: per-contract retention held, released and balance, with
the expected release date of the NEXT tranche that becomes claimable.

Design note: expected_release_date is derived from the EARLIEST invoice that
still has unreleased retention, not the contract's last invoice - each
invoice's retention has its own defect-liability clock starting at that
invoice's own posting date. Using the last invoice would understate how soon
earlier retention could already be claimed.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, nowdate

from contracting_invoicing.contracting_invoicing.doctype.retention_release.retention_release import (
    released_for_invoice,
)


def execute(filters=None):
    filters = filters or {}
    return _columns(), _data(filters)


def _columns():
    return [
        {"label": _("Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "Contracting Contract", "width": 140},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
        {"label": _("Contract Value"), "fieldname": "contract_value", "fieldtype": "Currency", "width": 120},
        {"label": _("Retention %"), "fieldname": "retention_percent", "fieldtype": "Percent", "width": 90},
        {"label": _("Cap %"), "fieldname": "retention_cap_percent", "fieldtype": "Percent", "width": 80},
        {"label": _("Retention Held"), "fieldname": "retention_held", "fieldtype": "Currency", "width": 130},
        {"label": _("Retention Released"), "fieldname": "retention_released", "fieldtype": "Currency", "width": 130},
        {"label": _("Retention Balance"), "fieldname": "retention_balance", "fieldtype": "Currency", "width": 130},
        {"label": _("Defect Liability (Months)"), "fieldname": "defect_liability_months", "fieldtype": "Int", "width": 90},
        {"label": _("Next Claimable Date"), "fieldname": "expected_release_date", "fieldtype": "Date", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]


def _data(filters):
    conditions = ["cc.status != 'Draft'"]
    params = []
    if filters.get("company"):
        conditions.append("cc.company = %s")
        params.append(filters["company"])
    if filters.get("contract"):
        conditions.append("cc.name = %s")
        params.append(filters["contract"])
    if filters.get("status"):
        conditions[0] = "cc.status = %s"
        params.insert(0, filters["status"])

    contracts = frappe.db.sql(
        f"""
        select cc.name as contract, cc.customer, cc.company, cc.contract_value,
               cc.retention_percent, cc.retention_cap_percent,
               cc.retention_held, cc.retention_released, cc.retention_balance,
               cc.defect_liability_months, cc.status
        from `tabContracting Contract` cc
        where {" and ".join(conditions)}
        order by cc.name
        """,
        params,
        as_dict=True,
    )

    today = getdate(nowdate())
    rows = []
    for c in contracts:
        c["expected_release_date"] = _next_claimable_date(c.contract, c.defect_liability_months)
        if flt(c.retention_balance) <= 0:
            c["status"] = _("Fully Released") if flt(c.retention_held) else _("None")
        elif c["expected_release_date"] and getdate(c["expected_release_date"]) <= today:
            c["status"] = _("Claimable")
        else:
            c["status"] = _("Not Due")
        rows.append(c)
    return rows


def _next_claimable_date(contract, defect_liability_months):
    """Earliest posting_date among invoices with retention still outstanding,
    plus the DLP. None if there's no open retention or no DLP configured."""
    if not defect_liability_months:
        return None
    invoices = frappe.db.sql(
        """
        select si.name, si.posting_date, si.contracting_retention_amount
        from `tabSales Invoice` si
        join `tabProgress Claim` pc on pc.name = si.contracting_claim
        where pc.contract = %s and si.docstatus = 1
          and si.contracting_retention_amount > 0
        order by si.posting_date asc
        """,
        contract,
        as_dict=True,
    )
    for inv in invoices:
        balance = flt(inv.contracting_retention_amount) - released_for_invoice(inv.name)
        if balance > 0:
            return add_months(getdate(inv.posting_date), int(defect_liability_months))
    return None
