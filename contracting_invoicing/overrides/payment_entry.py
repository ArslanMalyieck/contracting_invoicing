# Copyright (c) 2026, Arslan
"""Payment Entry hooks: register contract-linked advances and post the
Advance VAT correction JE.

Accounting model (see SPIKE_FINDINGS.md): the ksa_compliance-enforced Deduct
tax row is pointed at the 'VAT on Advances' clearing account; this hook posts
Dr Bank / Cr Output VAT so the advance's VAT is declared correctly on receipt
per KSA rules. Recovery JEs (task 4) amortize the clearing account.
"""

import frappe
from frappe import _
from frappe.utils import flt

from contracting_invoicing.contracting_invoicing.doctype.contracting_settings.contracting_settings import (
    get_settings,
)


def _is_contract_advance(doc) -> bool:
    return bool(doc.get("contracting_contract") and doc.get("custom_prepayment_invoice"))


def validate(doc, method=None):
    if not doc.get("contracting_contract"):
        return
    contract = frappe.get_cached_doc("Contracting Contract", doc.contracting_contract)

    if doc.company != contract.company:
        frappe.throw(_("Contract {0} belongs to {1}.").format(contract.name, contract.company))
    if doc.party_type != "Customer" or doc.party != contract.customer:
        frappe.throw(
            _("Contract {0} belongs to customer {1}.").format(contract.name, contract.customer)
        )
    if not doc.get("custom_prepayment_invoice"):
        frappe.msgprint(
            _(
                "This Payment Entry is linked to contract {0} but is not marked as a "
                "Prepayment Invoice. It will NOT be registered as an advance and no "
                "ZATCA prepayment invoice will be issued. Tick 'Prepayment Invoice' "
                "if this is a contract advance."
            ).format(contract.name),
            indicator="orange",
        )
        return
    if contract.status != "Active":
        frappe.throw(
            _("Contract {0} is {1}. Advances can only be recorded on Active contracts.").format(
                contract.name, _(contract.status)
            )
        )
    _validate_zatca_requirements(doc)
    _validate_advance_limit(doc, contract)


def _validate_zatca_requirements(doc):
    """The XML factories read the tax rate from the PE's taxes template, and
    the Deduct row must hit the clearing account (verified on 0.61.4)."""
    settings = get_settings(doc.company)
    if not doc.get("sales_taxes_and_charges_template"):
        frappe.throw(
            _(
                "Contract advances need a Sales Taxes and Charges Template on the "
                "Payment Entry - the ZATCA prepayment invoice takes its VAT rate "
                "from it."
            ),
            title=_("ZATCA Requirement"),
        )
    for row in doc.get("taxes") or []:
        if row.account_head != settings.advance_vat_clearing_account:
            frappe.throw(
                _(
                    "The advance tax row must use the clearing account {0} (see "
                    "Contracting Settings). The real Output VAT is credited "
                    "automatically by a Journal Entry when you submit - this keeps "
                    "your VAT return correct while the clearing account amortizes "
                    "as the advance is recovered."
                ).format(frappe.bold(settings.advance_vat_clearing_account)),
                title=_("Wrong Tax Account"),
            )


def _validate_advance_limit(doc, contract):
    if not flt(contract.advance_percent):
        return
    limit = flt(contract.advance_percent) / 100 * flt(contract.contract_value)
    gross = flt(doc.paid_amount)
    tax = abs(flt(doc.total_taxes_and_charges))
    projected = flt(contract.advance_received_net) + flt(gross - tax)
    if projected <= limit:
        return
    message = _(
        "Advance received (net) would reach {0}, exceeding {1}% of contract value ({2})."
    ).format(
        frappe.format_value(projected, {"fieldtype": "Currency"}),
        flt(contract.advance_percent),
        frappe.format_value(limit, {"fieldtype": "Currency"}),
    )
    if "Contracting Manager" in frappe.get_roles():
        frappe.msgprint(message, indicator="orange")
    else:
        frappe.throw(message + " " + _("A Contracting Manager can override this."))


def on_submit(doc, method=None):
    if not _is_contract_advance(doc):
        return
    contract = frappe.get_doc("Contracting Contract", doc.contracting_contract)
    # ksa_compliance semantics (verified 0.61.4): paid_amount is GROSS
    # (VAT-inclusive); Deduct taxes are stored negative, hence abs().
    gross = flt(doc.paid_amount, 2)
    tax = abs(flt(doc.total_taxes_and_charges, 2))
    net = flt(gross - tax, 2)
    contract.append(
        "advances",
        {
            "payment_entry": doc.name,
            "posting_date": doc.posting_date,
            "net_amount": net,
            "tax_amount": tax,
            "gross_amount": gross,
            "recovered_gross": 0,
            "balance_gross": gross,
        },
    )
    contract.save(ignore_permissions=True)
    contract.refresh_counters()
    if tax:
        _post_advance_vat_je(doc, contract, tax)
    _post_advance_reclass_je(doc, contract, net, tax)


def _post_advance_reclass_je(doc, contract, net: float, tax: float):
    """Move the advance net amount from the customer's receivable credit (the
    Payment Entry credits Debtors) to the Customer Advances liability, and clear
    the VAT-on-Advances clearing account. Recovery (an invoice-level allowance)
    then debits the liability, so revenue and VAT stay correct."""
    settings = get_settings(doc.company)
    liability = settings.get("advance_liability_account")
    if not liability:
        frappe.throw(
            _("Set 'Customer Advances (Liability) Account' in Contracting Settings {0}.").format(
                settings.name
            )
        )
    accounts = [
        {
            "account": doc.paid_from,
            "party_type": "Customer",
            "party": doc.party,
            "debit_in_account_currency": flt(net + tax, 2),
        },
        {"account": liability, "credit_in_account_currency": flt(net, 2)},
    ]
    if tax:
        accounts.append(
            {
                "account": settings.advance_vat_clearing_account,
                "credit_in_account_currency": flt(tax, 2),
            }
        )
    je = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": doc.company,
            "posting_date": doc.posting_date,
            "contracting_purpose": "Advance Reclass",
            "contracting_reference_doctype": "Payment Entry",
            "contracting_reference_name": doc.name,
            "user_remark": _(
                "Reclass advance {0} for contract {1}: net {2} moved from Debtors to "
                "{3}; the VAT-on-Advances clearing {4} is closed because Output VAT "
                "was declared separately on receipt. Recovery on progress invoices "
                "debits {3} (not revenue). Managed by Contracting Invoicing - cancels "
                "with the Payment Entry."
            ).format(doc.name, contract.name, net, liability, tax),
            "accounts": accounts,
        }
    )
    je.flags.ignore_permissions = True
    je.submit()


def _post_advance_vat_je(doc, contract, tax: float):
    """Dr Bank / Cr Output VAT. Combined with the PE's clearing-account Deduct
    row, the net posting is: Dr Bank gross / Cr Customer gross /
    Cr Output VAT tax / Dr Clearing tax."""
    settings = get_settings(doc.company)
    je = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": doc.company,
            "posting_date": doc.posting_date,
            "contracting_purpose": "Advance VAT",
            "contracting_reference_doctype": "Payment Entry",
            "contracting_reference_name": doc.name,
            "user_remark": _(
                "Output VAT {0} on advance {1} for contract {2}. KSA VAT is due when "
                "the advance is received; the Payment Entry's tax row parks the same "
                "amount in {3}, which amortizes as the advance is recovered on "
                "progress invoices. Managed by Contracting Invoicing - cancels with "
                "the Payment Entry."
            ).format(tax, doc.name, contract.name, settings.advance_vat_clearing_account),
            "accounts": [
                {"account": doc.paid_to, "debit_in_account_currency": tax},
                {
                    "account": settings.output_vat_account,
                    "credit_in_account_currency": tax,
                },
            ],
        }
    )
    je.flags.ignore_permissions = True
    je.submit()


def on_cancel(doc, method=None):
    if not _is_contract_advance(doc):
        return
    contract = frappe.get_doc("Contracting Contract", doc.contracting_contract)
    rows = [row for row in contract.advances if row.payment_entry == doc.name]
    for row in rows:
        if flt(row.recovered_gross) > 0:
            frappe.throw(
                _(
                    "Cannot cancel: {0} of this advance has already been recovered on "
                    "progress invoices."
                ).format(frappe.format_value(row.recovered_gross, {"fieldtype": "Currency"}))
            )
        contract.remove(row)
    contract.save(ignore_permissions=True)
    contract.refresh_counters()
    _cancel_linked_jes(doc)


def _cancel_linked_jes(doc):
    jes = frappe.get_all(
        "Journal Entry",
        filters={
            "contracting_reference_doctype": "Payment Entry",
            "contracting_reference_name": doc.name,
            "docstatus": 1,
        },
        pluck="name",
    )
    for je_name in jes:
        je = frappe.get_doc("Journal Entry", je_name)
        frappe.flags.contracting_system_cancel = True
        try:
            je.cancel()
        finally:
            frappe.flags.contracting_system_cancel = False
