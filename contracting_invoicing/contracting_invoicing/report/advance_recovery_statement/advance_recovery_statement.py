# Copyright (c) 2026, Arslan
"""Advance Recovery Statement: one row per advance (gross, recovered,
balance, ZATCA 386 status) with indented rows underneath showing exactly
which claims recovered how much against it. The indented detail is the
ZATCA audit-defense trail for prepayment adjustments - do not remove it.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return _columns(), _data(filters)


def _columns():
    return [
        {"label": _("Contract / Claim"), "fieldname": "contract", "fieldtype": "Link", "options": "Contracting Contract", "width": 140},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 130},
        {"label": _("Advance PE / Invoice"), "fieldname": "reference", "fieldtype": "Dynamic Link", "options": "reference_type", "width": 150},
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Gross Amount"), "fieldname": "gross_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Recovered (Gross)"), "fieldname": "recovered_gross", "fieldtype": "Currency", "width": 130},
        {"label": _("Balance (Gross)"), "fieldname": "balance_gross", "fieldtype": "Currency", "width": 130},
        {"label": _("Recovery %"), "fieldname": "recovery_percent", "fieldtype": "Percent", "width": 90},
        {"label": _("ZATCA"), "fieldname": "zatca_status", "fieldtype": "Data", "width": 140},
    ]


def _data(filters):
    # Contracting Contract is NOT submittable - use status, not docstatus.
    conditions = ["cc.status != 'Draft'"]
    params = []
    if filters.get("company"):
        conditions.append("cc.company = %s")
        params.append(filters["company"])
    if filters.get("contract"):
        conditions.append("cc.name = %s")
        params.append(filters["contract"])

    advances = frappe.db.sql(
        f"""
        select ca.payment_entry, ca.posting_date, ca.gross_amount,
               ca.recovered_gross, ca.balance_gross,
               cc.name as contract, cc.customer, cc.recovery_percent
        from `tabContract Advance` ca
        join `tabContracting Contract` cc on cc.name = ca.parent
        where {" and ".join(conditions)}
        order by cc.name, ca.posting_date
        """,
        params,
        as_dict=True,
    )

    rows = []
    for a in advances:
        rows.append(
            {
                "contract": a.contract,
                "customer": a.customer,
                "reference": a.payment_entry,
                "reference_type": "Payment Entry",
                "posting_date": a.posting_date,
                "gross_amount": flt(a.gross_amount, 2),
                "recovered_gross": flt(a.recovered_gross, 2),
                "balance_gross": flt(a.balance_gross, 2),
                "recovery_percent": a.recovery_percent,
                "zatca_status": _zatca_status(a.payment_entry),
                "indent": 0,
            }
        )
        for rec in _recoveries(a.payment_entry):
            rows.append(
                {
                    "contract": a.contract,
                    "reference": rec.sales_invoice,
                    "reference_type": "Sales Invoice",
                    "posting_date": rec.posting_date,
                    "recovered_gross": flt(rec.allocated_amount, 2),
                    "zatca_status": _zatca_status(rec.sales_invoice),
                    "indent": 1,
                }
            )
    return rows


def _recoveries(payment_entry):
    return frappe.db.sql(
        """
        select si.name as sales_invoice, si.posting_date, adv.allocated_amount
        from `tabSales Invoice Advance` adv
        join `tabSales Invoice` si on si.name = adv.parent
        where adv.reference_name = %s and si.docstatus = 1
        order by si.posting_date
        """,
        payment_entry,
        as_dict=True,
    )


def _zatca_status(voucher):
    siaf = frappe.db.get_value(
        "Sales Invoice Additional Fields",
        {"sales_invoice": voucher, "docstatus": ["<", 2]},
        "integration_status",
    )
    return siaf or _("Not submitted")
