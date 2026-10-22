# Copyright (c) 2026, Arslan
"""Contracting Contract: the anchor document.

Advance counters are system-managed, updated in-transaction by Payment Entry
hooks via refresh_counters(), and reconciled nightly against GL. Retention and
certified counters are owned by the Progress Claim / Retention Release hooks.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from contracting_invoicing.contracting_invoicing.doctype.contracting_settings.contracting_settings import (
    get_settings,
)

ADVANCE_BASIS_NET = "Net (VAT added on top)"
ADVANCE_BASIS_GROSS = "Gross (VAT inclusive)"


class ContractingContract(Document):
    def validate(self):
        self._validate_currency()
        self._validate_percents()
        self._reset_managed_on_new()

    def _reset_managed_on_new(self):
        """A contract copied/duplicated from another one (same or different
        customer) must NEVER start with the source's system-managed data.
        frappe.copy_doc(ignore_no_copy=True) - used by the Desk Duplicate
        action - copies no_copy fields anyway, so clear them explicitly."""
        if not self.is_new():
            return
        self.set("advances", [])
        for field in (
            "advance_received_net",
            "advance_recovered_gross",
            "advance_balance_gross",
            "retention_held",
            "retention_released",
            "retention_balance",
            "certified_to_date",
        ):
            self.set(field, 0)

    def _validate_currency(self):
        currency = frappe.get_cached_value("Company", self.company, "default_currency")
        if currency != "SAR":
            frappe.throw(_("Contracting Invoicing supports SAR companies only."))

    def _validate_percents(self):
        for field in (
            "advance_percent",
            "recovery_percent",
            "retention_percent",
            "retention_cap_percent",
        ):
            value = flt(self.get(field))
            if value < 0 or value > 100:
                frappe.throw(
                    _("{0} must be between 0 and 100.").format(_(self.meta.get_label(field)))
                )
        if flt(self.retention_cap_percent) and flt(self.retention_percent) == 0:
            frappe.msgprint(
                _("A retention cap is set but Retention % is 0 - no retention will be withheld."),
                indicator="orange",
            )

    def refresh_counters(self):
        """Recompute advance counters from the child table and persist."""
        self.advance_received_net = flt(sum(flt(row.net_amount) for row in self.advances), 2)
        self.advance_recovered_gross = flt(
            sum(flt(row.recovered_gross) for row in self.advances), 2
        )
        gross = flt(sum(flt(row.gross_amount) for row in self.advances), 2)
        self.advance_balance_gross = flt(gross - self.advance_recovered_gross, 2)
        self.db_update()
        self.notify_update()


def get_open_advances(contract: str) -> list[dict]:
    """Advance rows with remaining gross balance, oldest first (FIFO base)."""
    rows = frappe.get_all(
        "Contract Advance",
        filters={"parent": contract, "parenttype": "Contracting Contract"},
        fields=["name", "payment_entry", "posting_date", "gross_amount", "recovered_gross"],
        order_by="posting_date asc, idx asc",
    )
    open_rows = []
    for row in rows:
        row["balance_gross"] = flt(row.gross_amount - row.recovered_gross, 2)
        if row["balance_gross"] > 0:
            open_rows.append(row)
    return open_rows


def get_advance_vat_rate(contract) -> float:
    """Total VAT rate applied by the contract's Advance Taxes Template."""
    template = contract.get("advance_taxes_template")
    if not template:
        return 0.0
    rows = frappe.get_all(
        "Sales Taxes and Charges",
        filters={"parent": template, "parenttype": "Sales Taxes and Charges Template"},
        fields=["rate"],
    )
    return sum(abs(flt(row.rate)) for row in rows)


def get_advance_entitlement(contract) -> dict:
    """Remaining advance entitlement in both net and gross terms, honouring the
    contract's Advance Amount Basis.

    Net (VAT added on top): Advance % x Contract Value is a NET entitlement and
    VAT is added on top to reach the gross to collect.

    Gross (VAT inclusive): the same figure is a GROSS ceiling; the net taxable
    amount is gross / (1 + rate/100).

    The Payment Entry itself is identical in both cases (paid_amount = gross,
    ZATCA tax row Actual + Deduct with tax = net x rate); only the auto amount
    and the entitlement check differ.
    """
    vat_rate = get_advance_vat_rate(contract)
    entitlement = flt(contract.advance_percent) / 100 * flt(contract.contract_value)
    received_net = flt(contract.advance_received_net)
    received_gross = flt(sum(flt(row.gross_amount) for row in contract.advances), 2)
    factor = 1 + vat_rate / 100

    if (contract.get("advance_amount_basis") or ADVANCE_BASIS_NET) == ADVANCE_BASIS_GROSS:
        remaining_gross = entitlement - received_gross
        remaining_net = remaining_gross / factor if vat_rate else remaining_gross
    else:
        remaining_net = entitlement - received_net
        remaining_gross = remaining_net * factor if vat_rate else remaining_net

    return {
        "basis": contract.get("advance_amount_basis") or ADVANCE_BASIS_NET,
        "vat_rate": vat_rate,
        "remaining_net": flt(remaining_net, 2),
        "remaining_gross": flt(remaining_gross, 2),
    }


def compute_advance_totals(contract) -> dict:
    """Net / VAT / gross for the advance, honouring the contract's Advance
    Amount Basis and the optional explicit amount.

    Net (VAT added on top): an explicit Advance Amount is the NET (taxable)
    value, and VAT is added on top -> gross = net x (1 + rate/100). Leave it
    blank to use the Advance % entitlement.

    Gross (VAT inclusive): an explicit amount is the VAT-inclusive gross ->
    net = gross / (1 + rate/100). Leave it blank to use the entitlement.

    Either way the Payment Entry records paid_amount = gross with a ZATCA
    Actual + Deduct tax row, so taxable = net and tax = net x rate.
    """
    entitlement = get_advance_entitlement(contract)
    vat_rate = entitlement["vat_rate"]
    factor = 1 + vat_rate / 100 if vat_rate else 1
    amount = flt(contract.get("advance_amount_gross"), 2)

    if amount > 0:
        if entitlement["basis"] == ADVANCE_BASIS_GROSS:
            gross = amount
        else:
            gross = round(amount * factor, 2)  # Net: amount is net, VAT added
    else:
        gross = round(entitlement["remaining_gross"], 2)

    net = round(gross / factor, 2) if vat_rate else round(gross, 2)
    return {
        "basis": entitlement["basis"],
        "vat_rate": vat_rate,
        "net": net,
        "tax": round(gross - net, 2),
        "gross": round(gross, 2),
        "remaining_net": entitlement["remaining_net"],
    }


def populate_payment_entry_accounts(pe):
    """Fill the derived account fields that ERPNext's PaymentEntry.validate()
    would normally set on save: account currencies, the party's receivable
    account, and the exchange rates. A Payment Entry built server-side (or
    returned as an in-memory mapped doc) has these blank, and the Desk
    mandatory-field check (Account Currency (From)/(To) are reqd) fires before
    the server-side validate() ever runs."""
    pe.setup_party_account_field()
    pe.set_missing_values()
    if not pe.source_exchange_rate:
        pe.source_exchange_rate = 1
    if not pe.target_exchange_rate:
        pe.target_exchange_rate = 1
    return pe


@frappe.whitelist()
def create_advance_payment(contract_name):
    """Create (and optionally submit) the advance Payment Entry for this
    contract, fully configured: mode of payment from the contract, VAT tax
    row(s) copied from the Advance Taxes Template, ZATCA prepayment flags,
    reference number/date auto-filled. On submit the Payment Entry override
    registers the advance on the contract and posts the Output VAT JE
    automatically.
    """
    contract = frappe.get_doc("Contracting Contract", contract_name)
    if contract.status != "Active":
        frappe.throw(_("Contract {0} is {1}. Advances only on Active contracts.").format(
            contract.name, _(contract.status)))

    settings = get_settings(contract.company)

    if not flt(contract.advance_percent):
        frappe.throw(_("Set Advance % on the contract first."))
    if not contract.advance_mode_of_payment:
        frappe.throw(_("Select Advance Mode of Payment."))
    if not contract.advance_taxes_template:
        frappe.throw(_("Select Advance Taxes Template (VAT)."))

    mode_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": contract.advance_mode_of_payment, "company": contract.company},
        "default_account",
    )
    if not mode_account:
        frappe.throw(_("Mode of Payment {0} has no default account for company {1}. Set it in Mode of Payment Account.").format(
            contract.advance_mode_of_payment, contract.company))

    template = frappe.get_doc("Sales Taxes and Charges Template", contract.advance_taxes_template)
    if not template.taxes:
        frappe.throw(_("Advance Taxes Template {0} has no tax rows configured.").format(
            contract.advance_taxes_template))

    entitlement = get_advance_entitlement(contract)
    vat_rate = entitlement["vat_rate"]
    if not vat_rate:
        frappe.throw(_("Advance Taxes Template {0} has a 0% rate. Set a valid percentage-based VAT rate.").format(
            contract.advance_taxes_template))

    # Basis-aware amount: on Net basis an explicit Advance Amount is treated as
    # the NET (taxable) value and VAT is added on top; on Gross basis it is the
    # VAT-inclusive total. Blank = auto from the Advance % entitlement.
    totals = compute_advance_totals(contract)
    gross = totals["gross"]
    net = totals["net"]

    if gross <= 0:
        frappe.throw(_("Advance limit already reached (Advance Received {0}).").format(
            frappe.format_value(contract.advance_received_net, {"fieldtype": "Currency"})))

    # net (taxable amount) must stay within the remaining net entitlement.
    if net - 0.05 > (entitlement["remaining_net"] + 0.05):
        frappe.throw(_("Advance amount {0} (net {1}) exceeds the remaining advance entitlement (net {2}). Reduce the amount.").format(
            frappe.format_value(gross, {"fieldtype": "Currency"}),
            frappe.format_value(net, {"fieldtype": "Currency"}),
            frappe.format_value(entitlement["remaining_net"], {"fieldtype": "Currency"})))

    posting_date = contract.advance_posting_date or nowdate()
    reference_no = contract.advance_reference_no or ("ADV-" + contract.name)
    reference_date = contract.advance_reference_date or posting_date
    company_cc = frappe.db.get_value("Company", contract.company, "cost_center")

    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "company": contract.company,
        "party_type": "Customer",
        "party": contract.customer,
        "posting_date": posting_date,
        "mode_of_payment": contract.advance_mode_of_payment,
        "paid_from": frappe.db.get_value("Company", contract.company, "default_receivable_account"),
        "paid_to": mode_account,
        "paid_amount": gross,
        "received_amount": gross,
        "reference_no": reference_no,
        "reference_date": reference_date,
        "sales_taxes_and_charges_template": contract.advance_taxes_template,
        "custom_prepayment_invoice": 1,
        "custom_prepayment_invoice_description": _("Advance Payment - {0}").format(
            contract.contract_title
        ),
        "contracting_contract": contract.name,
    })

    # KSA Compliance requires Charge Type = "Actual" for Prepayment Invoices
    # with no Sales Order, so Rate is ignored - we compute tax_amount
    # ourselves, on the NET (taxable) amount, not on gross. The row must be a
    # Deduct row pointed at the clearing account (the Payment Entry override
    # enforces this and the Output VAT JE posts the real tax).
    for row in template.taxes:
        row_rate = flt(row.rate)
        row_tax_amount = flt(net * row_rate / 100, 2)
        pe.append("taxes", {
            "add_deduct_tax": "Deduct",
            "charge_type": "Actual",
            "included_in_paid_amount": 0,
            "account_head": settings.advance_vat_clearing_account,
            "description": row.description or _("VAT {0}% on advance").format(row_rate),
            "rate": row_rate,
            "tax_amount": row_tax_amount,
            "cost_center": row.cost_center or company_cc,
            "project": contract.project or None,
        })

    populate_payment_entry_accounts(pe)
    pe.flags.ignore_permissions = True
    pe.insert()

    if settings.auto_submit_generated_invoice:
        pe.submit()

    return pe.name
