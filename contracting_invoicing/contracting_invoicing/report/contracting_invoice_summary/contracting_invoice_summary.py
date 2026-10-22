# Copyright (c) 2026, Arslan
"""Contracting Invoice Summary: every contracting Sales Invoice with its
retention, advance recovery, deductions and net amount due, plus the ZATCA
status of the generated e-invoice."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    columns = _columns()
    data = _data(filters)
    return columns, data


def _columns():
    return [
        {"label": _("Sales Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "Contracting Contract", "width": 130},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 130},
        {"label": _("Net Total"), "fieldname": "net_total", "fieldtype": "Currency", "width": 110},
        {"label": _("VAT"), "fieldname": "total_taxes_and_charges", "fieldtype": "Currency", "width": 100},
        {"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
        {"label": _("Advance Recovery"), "fieldname": "contracting_advance_recovery", "fieldtype": "Currency", "width": 120},
        {"label": _("Retention"), "fieldname": "contracting_retention_amount", "fieldtype": "Currency", "width": 110},
        {"label": _("Deductions"), "fieldname": "deductions_total", "fieldtype": "Currency", "width": 110},
        {"label": _("Net Amount Due"), "fieldname": "contracting_net_amount_due", "fieldtype": "Currency", "width": 120},
        {"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
        {"label": _("ZATCA Status"), "fieldname": "zatca_status", "fieldtype": "Data", "width": 110},
        {"label": _("Doc Status"), "fieldname": "docstatus_label", "fieldtype": "Data", "width": 80},
    ]


def _data(filters):
    conditions = ["si.contracting_claim is not null", "si.contracting_claim != ''"]
    params = []
    if filters.get("company"):
        conditions.append("si.company = %s")
        params.append(filters["company"])
    if filters.get("contract"):
        conditions.append("pc.contract = %s")
        params.append(filters["contract"])
    if filters.get("from_date"):
        conditions.append("si.posting_date >= %s")
        params.append(filters["from_date"])
    if filters.get("to_date"):
        conditions.append("si.posting_date <= %s")
        params.append(filters["to_date"])

    invoices = frappe.db.sql(
        f"""
        select si.name, si.posting_date, pc.contract, si.customer,
               si.net_total, si.total_taxes_and_charges, si.grand_total,
               si.contracting_advance_recovery, si.contracting_retention_amount,
               si.contracting_net_amount_due, si.outstanding_amount,
               si.contracting_claim, si.docstatus
        from `tabSales Invoice` si
        left join `tabProgress Claim` pc on pc.sales_invoice = si.name
        where {" and ".join(conditions)}
        order by si.posting_date, si.name
        """,
        params,
        as_dict=True,
    )

    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
    rows = []
    for inv in invoices:
        inv["deductions_total"] = _deductions_total(inv.contracting_claim) if inv.contracting_claim else 0
        inv["zatca_status"] = _zatca_status(inv.name)
        inv["docstatus_label"] = status_map.get(inv.docstatus, "?")
        rows.append(inv)
    return rows


def _deductions_total(claim_name):
    rows = frappe.get_all(
        "Progress Claim Deduction",
        filters={"parent": claim_name, "parenttype": "Progress Claim"},
        fields=["deduction_type", "amount"],
    )
    total = 0
    for r in rows:
        if frappe.db.get_value("Deduction Type", r.deduction_type, "treatment") == "Payment-side Deduction":
            total += flt(r.amount)
    return flt(total, 2)


def _zatca_status(si_name):
    siaf = frappe.db.get_value(
        "Sales Invoice Additional Fields",
        {"sales_invoice": si_name, "docstatus": ["<", 2]},
        "integration_status",
    )
    if not siaf:
        return "—"
    return siaf
