# Copyright (c) 2026, Arslan
"""Sales Invoice hooks for contracting invoices.

on_submit posts (in one transaction): retention JE, payment-side deduction
JEs, the recovery-VAT JE (amortizing VAT on Advances), updates contract
counters, then asserts net_amount_due == the invoice's real outstanding.
on_cancel reverses all of it.
"""

import frappe
from frappe import _
from frappe.utils import flt

from contracting_invoicing.contracting_invoicing.doctype.contracting_settings.contracting_settings import (
    get_settings,
)


def before_validate(doc, method=None):
    # Must run BEFORE ERPNext's own validate: make_sales_return copies the
    # advances rows onto the return and core validation rejects/misreads them
    # before our validate hook would fire.
    _clear_advances_on_contracting_return(doc)


def validate(doc, method=None):
    _clear_advances_on_contracting_return(doc)


def before_cancel(doc, method=None):
    pass


def _clear_advances_on_contracting_return(doc):
    if not doc.get("is_return") or not doc.get("return_against"):
        return
    if not frappe.db.get_value("Sales Invoice", doc.return_against, "contracting_claim"):
        return
    if doc.get("advances"):
        doc.set("advances", [])
        frappe.msgprint(
            _(
                "Advance allocations were removed from this credit note: advance "
                "recovery is never reversed through returns. Recover less on the "
                "next Progress Claim instead."
            ),
            indicator="orange",
        )
def on_submit(doc, method=None):
    if doc.get("is_return"):
        _handle_contracting_return_submit(doc)
        return
    if not doc.get("contracting_claim"):
        return
    claim = frappe.get_doc("Progress Claim", doc.contracting_claim)
    contract = frappe.get_doc("Contracting Contract", claim.contract)
    settings = get_settings(doc.company)

    if flt(claim.retention_amount) and not flt(doc.get("contracting_retention_deducted")):
        _post_retention_je(doc, claim, contract, settings)
    _post_deduction_jes(doc, claim, settings)
    _post_recovery_reclass_je(doc, claim, contract, settings)
    _apply_recovery_to_contract(doc, contract, reverse=False)
    _update_contract_counters(claim, contract, reverse=False)
    _assert_outstanding(doc, claim)


def _get_return_context(doc):
    """(original_si_doc, claim, contract) for a return against a contracting
    invoice, else (None, None, None)."""
    if not doc.get("is_return") or not doc.get("return_against"):
        return None, None, None
    original_claim = frappe.db.get_value("Sales Invoice", doc.return_against, "contracting_claim")
    if not original_claim:
        return None, None, None
    original = frappe.get_doc("Sales Invoice", doc.return_against)
    claim = frappe.get_doc("Progress Claim", original_claim)
    contract = frappe.get_doc("Contracting Contract", claim.contract)
    return original, claim, contract


def _handle_contracting_return_submit(doc):
    """Credit note against a contracting invoice: reverse retention
    proportionally (unless skipped) and reduce contract counters by the
    credited certified value. Advance recovery is intentionally NOT restored
    - recover less on the next claim instead (see BUILD SPEC / Part 3 2.1)."""
    original, claim, contract = _get_return_context(doc)
    if not original:
        return
    settings = get_settings(doc.company)
    credited_net = abs(flt(doc.net_total, 2))
    reversal = 0.0
    if not doc.get("contracting_skip_retention_reversal"):
        from contracting_invoicing.contracting_invoicing.doctype.retention_release.retention_release import (
            released_for_invoice,
        )

        proportional = flt(flt(contract.retention_percent) / 100 * credited_net, 2)
        available = flt(
            flt(original.contracting_retention_amount) - released_for_invoice(original.name), 2
        )
        reversal = min(proportional, max(available, 0))
        if reversal:
            _post_return_retention_reversal_je(doc, original, contract, settings, reversal)
    contract.db_set(
        "certified_to_date", flt(flt(contract.certified_to_date) - credited_net, 2)
    )
    contract.db_set(
        "retention_held", flt(flt(contract.retention_held) - reversal, 2)
    )
    contract.db_set(
        "retention_balance",
        flt(flt(contract.retention_held) - flt(contract.retention_released), 2),
    )
    doc.db_set("contracting_retention_amount", -reversal)
    frappe.msgprint(
        _(
            "Contracting credit note: certified value reduced by {0}; retention "
            "reversed {1} (proportional, capped at the invoice's unreleased "
            "retention). Advance recovery is never restored by credit notes - "
            "recover less on the next Progress Claim if needed."
        ).format(credited_net, reversal),
        indicator="blue",
    )


def _post_return_retention_reversal_je(doc, original, contract, settings, amount):
    je = _je_base(
        doc,
        "Retention Reversal",
        _(
            "Retention reversal {0} due to credit note {1} against {2} (contract "
            "{3}): the credited portion of the works is no longer retained, so the "
            "amount moves back from {4} to Debtors. Managed by Contracting "
            "Invoicing - cancels with the credit note."
        ).format(amount, doc.name, original.name, contract.name, settings.retention_receivable_account),
    )
    je.append(
        "accounts",
        {
            "account": original.debit_to,
            "party_type": "Customer",
            "party": original.customer,
            "debit_in_account_currency": amount,
            "reference_type": "Sales Invoice",
            "reference_name": original.name,
        },
    )
    je.append(
        "accounts",
        {
            "account": settings.retention_receivable_account,
            "party_type": "Customer",
            "party": original.customer,
            "credit_in_account_currency": amount,
        },
    )
    je.flags.ignore_permissions = True
    je.submit()


def _je_base(doc, purpose, remark):
    return frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": doc.company,
            "posting_date": doc.posting_date,
            "contracting_purpose": purpose,
            "contracting_reference_doctype": "Sales Invoice",
            "contracting_reference_name": doc.name,
            "user_remark": remark,
            "accounts": [],
        }
    )


def _post_retention_je(doc, claim, contract, settings):
    amount = flt(claim.retention_amount, 2)
    je = _je_base(
        doc,
        "Retention",
        _(
            "Retention {0}% withheld on {1} per contract {2} - moved from Debtors to "
            "{3} so AR aging shows only the collectible amount. VAT was charged on "
            "the full certified value per the ZATCA contracting guideline. Managed "
            "by Contracting Invoicing - cancels with the invoice."
        ).format(contract.retention_percent, doc.name, contract.name, settings.retention_receivable_account),
    )
    je.append(
        "accounts",
        {
            "account": settings.retention_receivable_account,
            "party_type": "Customer",
            "party": doc.customer,
            "debit_in_account_currency": amount,
        },
    )
    je.append(
        "accounts",
        {
            "account": doc.debit_to,
            "party_type": "Customer",
            "party": doc.customer,
            "credit_in_account_currency": amount,
            "reference_type": "Sales Invoice",
            "reference_name": doc.name,
        },
    )
    je.flags.ignore_permissions = True
    je.submit()


def _post_deduction_jes(doc, claim, settings):
    for row in claim.deductions:
        if row.treatment != "Payment-side Deduction":
            continue
        account = (
            frappe.db.get_value("Deduction Type", row.deduction_type, "default_account")
            or settings.deduction_expense_account
        )
        je = _je_base(
            doc,
            "Deduction",
            _(
                "{0} of {1} deducted by the client on {2} ({3}). Payment-side "
                "deduction: no VAT effect. Managed by Contracting Invoicing - "
                "cancels with the invoice."
            ).format(row.deduction_type, row.amount, doc.name, row.remarks or "-"),
        )
        je.append("accounts", {"account": account, "debit_in_account_currency": flt(row.amount, 2)})
        je.append(
            "accounts",
            {
                "account": doc.debit_to,
                "party_type": "Customer",
                "party": doc.customer,
                "credit_in_account_currency": flt(row.amount, 2),
                "reference_type": "Sales Invoice",
                "reference_name": doc.name,
            },
        )
        je.flags.ignore_permissions = True
        je.submit()


def _recovery_rows(doc):
    """Prepayment allocations on this invoice: [(pe, allocated_gross)]."""
    rows = []
    for a in doc.get("advances") or []:
        if a.reference_type == "Payment Entry" and frappe.db.get_value(
            "Payment Entry", a.reference_name, "custom_prepayment_invoice"
        ):
            rows.append((a.reference_name, flt(a.allocated_amount, 2)))
    return rows


def _post_recovery_reclass_je(doc, claim, contract, settings):
    """Restore revenue for the invoice's allowance and park the deduction in
    the right balance-sheet account:
      - advance recovery  -> Customer Advances (liability)
      - retention deducted -> Retention Receivable (asset)
    The invoice itself carries the deduction as a document allowance, so VAT is
    computed net of it; this JE keeps Sales at the certified value."""
    total_discount = flt(doc.get("discount_amount") or 0, 2)
    if not total_discount:
        return
    retention_deducted = flt(doc.get("contracting_retention_deducted") or 0, 2)
    recovery_net = flt(total_discount - retention_deducted, 2)
    income_account = (
        doc.items[0].income_account
        or frappe.db.get_value("Company", doc.company, "default_income_account")
    )
    purpose = "Retention Deduction" if retention_deducted else "Advance Recovery"
    je = _je_base(
        doc,
        purpose,
        _(
            "Deduction {0} on {1}: the invoice carries it as an allowance so VAT "
            "is charged net of it, while revenue stays at the certified value. "
            "Advance {2} clears Customer Advances; retention {3} moves to "
            "Retention Receivable. Managed by Contracting Invoicing - cancels "
            "with the invoice."
        ).format(total_discount, doc.name, recovery_net, retention_deducted),
    )
    if recovery_net:
        je.append(
            "accounts",
            {
                "account": settings.advance_liability_account,
                "debit_in_account_currency": recovery_net,
            },
        )
    if retention_deducted:
        je.append(
            "accounts",
            {
                "account": settings.retention_receivable_account,
                "party_type": "Customer",
                "party": doc.customer,
                "debit_in_account_currency": retention_deducted,
            },
        )
    je.append(
        "accounts",
        {
            "account": income_account,
            "credit_in_account_currency": total_discount,
        },
    )
    je.flags.ignore_permissions = True
    je.submit()


def _apply_recovery_to_contract(doc, contract, reverse: bool):
    gross = flt(doc.get("contracting_advance_recovery"), 2)
    if not gross:
        return
    rows = sorted(
        contract.advances, key=lambda r: (str(r.posting_date or ""), r.idx or 0)
    )
    if reverse:
        rows = list(reversed(rows))
    remaining = gross
    changed = False
    for row in rows:
        if remaining <= 0:
            break
        if reverse:
            room = flt(row.recovered_gross, 2)
            take = min(room, remaining)
            row.recovered_gross = flt(flt(row.recovered_gross) - take, 2)
        else:
            room = flt(flt(row.gross_amount) - flt(row.recovered_gross), 2)
            take = min(room, remaining)
            row.recovered_gross = flt(flt(row.recovered_gross) + take, 2)
        if take:
            row.balance_gross = flt(flt(row.gross_amount) - flt(row.recovered_gross), 2)
            if row.balance_gross < 0 or row.recovered_gross < 0:
                frappe.throw(
                    _("Recovery on advance {0} would exceed its balance.").format(
                        row.payment_entry
                    )
                )
            row.db_update()
            remaining = flt(remaining - take, 2)
            changed = True
    if changed:
        contract.refresh_counters()


def _update_contract_counters(claim, contract, reverse: bool):
    sign = -1 if reverse else 1
    contract.db_set(
        "certified_to_date",
        flt(flt(contract.certified_to_date) + sign * flt(claim.current_certified_value), 2),
    )
    contract.db_set(
        "retention_held",
        flt(flt(contract.retention_held) + sign * flt(claim.retention_amount), 2),
    )
    contract.db_set(
        "retention_balance",
        flt(flt(contract.retention_held) - flt(contract.retention_released), 2),
    )


def _assert_outstanding(doc, claim):
    doc.reload()
    # ERPNext's outstanding already reflects the retention JE (it posts a
    # payment-ledger entry against the invoice before this check), so the
    # expected value is the claim's Net Amount Due itself. Small rounding
    # tolerance for VAT/advance rounding differences.
    expected = flt(claim.net_amount_due, 2)
    actual = flt(doc.outstanding_amount, 2)
    if abs(expected - actual) > 0.5:
        frappe.throw(
            _(
                "Accounting safety check failed on {0}: computed Net Amount Due {1} "
                "does not equal the invoice outstanding {2}. Nothing was posted - "
                "please report this."
            ).format(doc.name, expected, actual)
        )


def on_cancel(doc, method=None):
    if doc.get("is_return"):
        original, claim, contract = _get_return_context(doc)
        if original:
            doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ())
            _cancel_linked_contracting_jes(doc)
            reversal = abs(flt(doc.get("contracting_retention_amount"), 2))
            contract.db_set(
                "certified_to_date",
                flt(flt(contract.certified_to_date) + abs(flt(doc.net_total, 2)), 2),
            )
            contract.db_set(
                "retention_held", flt(flt(contract.retention_held) + reversal, 2)
            )
            contract.db_set(
                "retention_balance",
                flt(flt(contract.retention_held) - flt(contract.retention_released), 2),
            )
        return
    if doc.get("contracting_claim"):
        # ERPNext's own SalesInvoice.on_cancel() sets doc.ignore_linked_doctypes
        # to its own hardcoded tuple (GL Entry, Payment Ledger Entry, etc) as
        # part of the SAME dispatch, running just before this hook. We EXTEND
        # that tuple rather than replace it - the sanctioned Frappe mechanism
        # (the same one Journal Entry uses for GL Entry) - so the SI can
        # cancel even though the submitted Progress Claim still links to it.
        existing = tuple(doc.get("ignore_linked_doctypes") or ())
        doc.ignore_linked_doctypes = (*existing, "Progress Claim")
        _block_if_retention_released(doc)
    _cancel_linked_contracting_jes(doc)
    if doc.get("contracting_claim") and not doc.get("is_return"):
        claim = frappe.get_doc("Progress Claim", doc.contracting_claim)
        contract = frappe.get_doc("Contracting Contract", claim.contract)
        _apply_recovery_to_contract(doc, contract, reverse=True)
        _update_contract_counters(claim, contract, reverse=True)


def _block_if_retention_released(doc):
    """Block cancelling an invoice whose retention has already been released -
    the Retention Reversal JE references it. Cancel the Retention Release first."""
    if not doc.get("contracting_retention_amount"):
        return
    released = frappe.db.sql(
        """
        select coalesce(sum(jea.debit_in_account_currency), 0)
        from `tabJournal Entry Account` jea
        join `tabJournal Entry` je on je.name = jea.parent
        where je.contracting_purpose = 'Retention Reversal'
          and je.docstatus = 1
          and jea.reference_name = %s
        """,
        doc.name,
    )[0][0]
    if flt(released, 2) > 0:
        frappe.throw(
            _(
                "Cannot cancel {0}: {1} of its retention has already been released "
                "via a Retention Release. Cancel that Retention Release first."
            ).format(doc.name, flt(released, 2))
        )


def _cancel_linked_contracting_jes(doc):
    jes = frappe.get_all(
        "Journal Entry",
        filters={
            "contracting_reference_doctype": "Sales Invoice",
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
