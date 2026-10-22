# Copyright (c) 2026, Arslan
"""Manual, synchronous ZATCA submission - a reliable alternative to
ksa_compliance's queue-based batch sync for demos and small sites where
background workers may not be running. Triggered by a Desk button on
Payment Entry / Sales Invoice; does exactly what the hourly batch job would
do, just immediately and in the foreground.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate

from contracting_invoicing.contracting_invoicing.doctype.contracting_contract.contracting_contract import (
    compute_advance_totals,
    populate_payment_entry_accounts,
)


@frappe.whitelist()
def make_advance_payment_entry(source_name: str):
    """Mapped-doc source for the Contracting Contract 'Record Advance' button
    (frappe.model.open_mapped_doc pattern - same mechanism as Sales Order ->
    Sales Invoice / Payment Entry). Prefills party, company, accounts and tax
    template so the user lands on a ready-to-submit form, not a blank one.
    """
    contract = frappe.get_doc("Contracting Contract", source_name)
    frappe.has_permission("Contracting Contract", "write", doc=contract, throw=True)

    if contract.status != "Active":
        frappe.throw(_("Contract {0} is {1}, not Active.").format(contract.name, _(contract.status)))

    _validate_advance_allowed(contract)

    company = frappe.get_cached_doc("Company", contract.company)
    settings_name = frappe.db.exists("Contracting Settings", {"company": contract.company})
    settings = frappe.get_cached_doc("Contracting Settings", settings_name) if settings_name else None
    tax_template = contract.advance_taxes_template or frappe.db.get_value(
        "Sales Taxes and Charges Template", {"company": contract.company, "is_default": 1}
    ) or frappe.db.get_value("Sales Taxes and Charges Template", {"company": contract.company})

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = contract.company
    pe.party_type = "Customer"
    pe.party = contract.customer
    pe.paid_from = company.default_receivable_account
    pe.paid_to = company.default_bank_account or company.default_cash_account
    pe.contracting_contract = contract.name
    pe.custom_prepayment_invoice = 1
    pe.custom_prepayment_invoice_description = _("Advance Payment - {0}").format(contract.contract_title)
    if tax_template and settings:
        pe.sales_taxes_and_charges_template = tax_template

        # Prefill the advance so the user lands on a ready-to-submit form.
        # Basis-aware: on Net basis an explicit Advance Amount is the net and
        # VAT is added on top; on Gross basis it is VAT-inclusive. Blank = auto
        # from the Advance % entitlement. The PE records paid_amount = gross
        # with a ZATCA Actual + Deduct tax row (taxable = net).
        totals = compute_advance_totals(contract)
        rate = totals["vat_rate"]
        pe.paid_amount = flt(totals["gross"], 2)
        pe.received_amount = flt(totals["gross"], 2)
        if rate:
            pe.append(
                "taxes",
                {
                    "charge_type": "Actual",
                    "add_deduct_tax": "Deduct",
                    "included_in_paid_amount": 0,
                    "account_head": settings.advance_vat_clearing_account,
                    "description": _("VAT {0}% on advance").format(rate),
                    "rate": rate,
                    "tax_amount": flt(totals["tax"], 2),
                },
            )
    populate_payment_entry_accounts(pe)
    return pe


def _validate_advance_allowed(contract):
    if flt(contract.advance_percent):
        limit = flt(contract.advance_percent) / 100 * flt(contract.contract_value)
        if flt(contract.advance_received_net) >= limit:
            frappe.throw(
                _(
                    "Advance already fully recorded for this contract: {0} received against "
                    "a {1}% ({2}) entitlement. A Contracting Manager can still create one "
                    "manually if this is a genuine additional advance."
                ).format(
                    frappe.format_value(contract.advance_received_net, {"fieldtype": "Currency"}),
                    contract.advance_percent,
                    frappe.format_value(limit, {"fieldtype": "Currency"}),
                )
            )
    elif contract.advances:
        frappe.throw(
            _(
                "An advance has already been recorded for this contract, and no Advance % "
                "is configured to allow staged advances. Set Advance % on the contract if "
                "more than one advance is expected."
            )
        )


@frappe.whitelist()
def make_progress_claim(source_name: str):
    """Mapped-doc source for the Contracting Contract 'New Progress Claim'
    button. Prefills contract, customer, company, taxes template, and the
    next period's start date from the previous claim's end date.
    """
    contract = frappe.get_doc("Contracting Contract", source_name)
    frappe.has_permission("Contracting Contract", "write", doc=contract, throw=True)

    if contract.status != "Active":
        frappe.throw(_("Contract {0} is {1}, not Active.").format(contract.name, _(contract.status)))

    tax_template = frappe.db.get_value(
        "Sales Taxes and Charges Template", {"company": contract.company, "is_default": 1}
    ) or frappe.db.get_value("Sales Taxes and Charges Template", {"company": contract.company})

    last_period_to = frappe.db.get_value(
        "Progress Claim",
        {"contract": contract.name, "docstatus": 1},
        "period_to",
        order_by="period_to desc",
    )

    claim = frappe.new_doc("Progress Claim")
    claim.contract = contract.name
    claim.customer = contract.customer
    claim.company = contract.company
    claim.posting_date = nowdate()
    claim.period_from = add_days(last_period_to, 1) if last_period_to else nowdate()
    claim.period_to = nowdate()
    if tax_template:
        claim.taxes_template = tax_template
    return claim


@frappe.whitelist()
def submit_now(sales_invoice: str) -> str:
    frappe.has_permission("Sales Invoice", "submit", throw=True)
    siaf_name = frappe.db.get_value(
        "Sales Invoice Additional Fields",
        {"sales_invoice": sales_invoice, "docstatus": ["<", 2]},
    )
    if not siaf_name:
        frappe.throw(_("No pending ZATCA submission found for {0}.").format(sales_invoice))
    siaf = frappe.get_doc("Sales Invoice Additional Fields", siaf_name)
    if siaf.integration_status not in ("Ready For Batch", "Resend", "Corrected"):
        frappe.throw(
            _("{0} is not pending submission (status: {1}).").format(
                sales_invoice, siaf.integration_status
            )
        )
    result = siaf.submit_to_zatca()
    siaf.reload()
    return f"{result} | Status: {siaf.integration_status}"
