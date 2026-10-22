# Copyright (c) 2026, Arslan
"""Contract Progress Statement: per contract, the certified-to-date vs contract
value (progress %), advance position, and retention position. Claim-level
detail rows show each Progress Claim's contribution."""

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
        {"label": _("Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "Contracting Contract", "width": 140},
        {"label": _("Claim"), "fieldname": "claim", "fieldtype": "Link", "options": "Progress Claim", "width": 130},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 130},
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Contract Value"), "fieldname": "contract_value", "fieldtype": "Currency", "width": 120},
        {"label": _("This Period (Net)"), "fieldname": "current_certified_value", "fieldtype": "Currency", "width": 130},
        {"label": _("Cumulative (Net)"), "fieldname": "cumulative_certified_value", "fieldtype": "Currency", "width": 130},
        {"label": _("% Complete"), "fieldname": "pct_complete", "fieldtype": "Percent", "width": 90},
        {"label": _("Advance Recovery"), "fieldname": "advance_recovery", "fieldtype": "Currency", "width": 120},
        {"label": _("Retention"), "fieldname": "retention_amount", "fieldtype": "Currency", "width": 110},
        {"label": _("Net Amount Due"), "fieldname": "net_amount_due", "fieldtype": "Currency", "width": 120},
        {"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 130},
        {"label": _("Status"), "fieldname": "docstatus_label", "fieldtype": "Data", "width": 80},
    ]


def _data(filters):
    # Contracting Contract is NOT submittable (status-driven: Draft/Active/
    # Defect Liability/Closed) - docstatus is always 0. Filter by status
    # instead; default excludes Draft (nothing has happened on it yet).
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
               cc.certified_to_date, cc.advance_balance_gross,
               cc.advance_received_net, cc.advance_recovered_gross,
               cc.retention_held, cc.retention_released, cc.retention_balance
        from `tabContracting Contract` cc
        where {" and ".join(conditions)}
        order by cc.name
        """,
        params,
        as_dict=True,
    )

    rows = []
    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
    for c in contracts:
        claims = frappe.get_all(
            "Progress Claim",
            filters={"contract": c.contract, "docstatus": ["in", [1, 2]]},
            fields=[
                "name as claim", "posting_date", "cumulative_certified_value",
                "current_certified_value", "advance_recovery_gross",
                "retention_amount", "net_amount_due", "sales_invoice", "docstatus",
            ],
            order_by="posting_date, creation",
        )
        if not claims:
            rows.append(_summary_row(c))
            continue
        for cl in claims:
            cl["contract"] = c.contract
            cl["customer"] = c.customer
            cl["contract_value"] = c.contract_value
            cl["advance_recovery"] = cl.pop("advance_recovery_gross", 0)
            cl["pct_complete"] = _pct(cl.get("cumulative_certified_value"), c.contract_value)
            cl["docstatus_label"] = status_map.get(cl.docstatus, "?")
            rows.append(cl)
    return rows


def _summary_row(c):
    return {
        "contract": c.contract,
        "customer": c.customer,
        "contract_value": c.contract_value,
        "current_certified_value": c.certified_to_date,
        "cumulative_certified_value": c.certified_to_date,
        "pct_complete": _pct(c.certified_to_date, c.contract_value),
        "advance_recovery": c.advance_recovered_gross,
        "retention_amount": c.retention_held,
        "net_amount_due": None,
        "docstatus_label": "— no claims —",
    }


def _pct(certified, contract_value):
    if not flt(contract_value):
        return 0
    return flt(flt(certified) / flt(contract_value) * 100, 2)
