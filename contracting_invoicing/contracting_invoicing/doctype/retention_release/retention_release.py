# Copyright (c) 2026, Arslan
"""Retention Release: moves withheld retention back to Debtors so the client
pays it (typically after the defect liability period ends).

Each entry reverses one invoice's Retention JE (Dr Retention Receivable /
Cr Debtors) by posting Dr Debtors / Cr Retention Receivable with the same
party and SI reference. Contract counters (retention_released,
retention_balance) are updated on submit and restored on cancel.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from contracting_invoicing.contracting_invoicing.doctype.contracting_settings.contracting_settings import (
    get_settings,
)


class RetentionRelease(Document):
    def validate(self):
        self.title = _("Retention Release - {0}").format(self.contract)
        self._validate_entries()
        self.total_release = flt(sum(flt(r.amount) for r in self.entries), 2)
        contract_held = flt(
            frappe.db.get_value("Contracting Contract", self.contract, "retention_held")
        )
        released_so_far = flt(
            frappe.db.get_value("Contracting Contract", self.contract, "retention_released")
        )
        self.retention_balance_before = flt(contract_held - released_so_far, 2)
        self.retention_balance_after = flt(self.retention_balance_before - self.total_release, 2)
        if self.retention_balance_after < 0:
            frappe.throw(
                _(
                    "Release total {0} exceeds the contract's retention balance {1}."
                ).format(self.total_release, self.retention_balance_before)
            )

    def _validate_entries(self):
        seen = set()
        for row in self.entries:
            if row.sales_invoice in seen:
                frappe.throw(_("Row {0}: invoice {1} appears twice.").format(row.idx, row.sales_invoice))
            seen.add(row.sales_invoice)
            # Authoritative figures from the DB, not the client-supplied row:
            # retained on the invoice, minus what submitted releases already took.
            retained = flt(
                frappe.db.get_value(
                    "Sales Invoice", row.sales_invoice, "contracting_retention_amount"
                ),
                2,
            )
            row.retained_amount = retained
            already = released_for_invoice(row.sales_invoice, exclude_release=self.name)
            available = flt(retained - already, 2)
            if flt(row.amount, 2) > available:
                frappe.throw(
                    _(
                        "Row {0}: release amount {1} exceeds the unreleased retention "
                        "{2} on {3} (retained {4}, already released {5})."
                    ).format(
                        row.idx, row.amount, available, row.sales_invoice, retained, already
                    )
                )
            row.balance = flt(available - flt(row.amount, 2), 2)

    def on_submit(self):
        contract = frappe.get_doc("Contracting Contract", self.contract)
        for row in self.entries:
            self._post_reversal_je(row, contract)
        released = flt(contract.retention_released, 2) + self.total_release
        contract.db_set("retention_released", released)
        contract.db_set("retention_balance", flt(contract.retention_held - released, 2))
        contract.notify_update()

    def _post_reversal_je(self, row, contract):
        settings = get_settings(self.company)
        si = frappe.get_cached_doc("Sales Invoice", row.sales_invoice)
        amount = flt(row.amount, 2)
        je = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "company": self.company,
                "posting_date": self.posting_date,
                "contracting_purpose": "Retention Reversal",
                "contracting_reference_doctype": "Retention Release",
                "contracting_reference_name": self.name,
                "user_remark": _(
                    "Retention release of {0} on {1} per contract {2}. Reverses the "
                    "retention withheld when that invoice was submitted: moves the "
                    "amount back from {3} to Debtors so the client pays it now. "
                    "Managed by Contracting Invoicing - cancels with the Retention "
                    "Release."
                ).format(amount, si.name, contract.name, settings.retention_receivable_account),
                "accounts": [
                    {
                        "account": si.debit_to,
                        "party_type": "Customer",
                        "party": self.customer,
                        "debit_in_account_currency": amount,
                        "reference_type": "Sales Invoice",
                        "reference_name": si.name,
                    },
                    {
                        "account": settings.retention_receivable_account,
                        "party_type": "Customer",
                        "party": self.customer,
                        "credit_in_account_currency": amount,
                    },
                ],
            }
        )
        je.flags.ignore_permissions = True
        je.submit()

    def on_cancel(self):
        self._cancel_reversal_jes()
        contract = frappe.get_doc("Contracting Contract", self.contract)
        released = flt(contract.retention_released, 2) - self.total_release
        contract.db_set("retention_released", released)
        contract.db_set("retention_balance", flt(contract.retention_held - released, 2))
        contract.notify_update()

    def _cancel_reversal_jes(self):
        jes = frappe.get_all(
            "Journal Entry",
            filters={
                "contracting_reference_doctype": "Retention Release",
                "contracting_reference_name": self.name,
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


def released_for_invoice(sales_invoice: str, exclude_release: str | None = None) -> float:
    """Retention already consumed for an invoice: released via submitted
    Retention Releases PLUS reversed by submitted credit notes against it.

    Sources of truth are the Retention Release Entry rows and the credit
    notes' contracting_retention_amount (stored negative) - not GL queries,
    because the reversal JE's SI reference sits on the Debtors row, not the
    retention row.
    """
    conditions = "rr.docstatus = 1 and rre.sales_invoice = %(si)s"
    values = {"si": sales_invoice}
    if exclude_release:
        conditions += " and rr.name != %(exclude)s"
        values["exclude"] = exclude_release
    released = flt(
        frappe.db.sql(
            f"""
            select coalesce(sum(rre.amount), 0)
            from `tabRetention Release Entry` rre
            join `tabRetention Release` rr on rr.name = rre.parent
            where {conditions}
            """,
            values,
        )[0][0],
        2,
    )
    reversed_by_returns = flt(
        frappe.db.sql(
            """
            select coalesce(sum(abs(contracting_retention_amount)), 0)
            from `tabSales Invoice`
            where is_return = 1 and docstatus = 1
              and return_against = %s
              and contracting_retention_amount < 0
            """,
            sales_invoice,
        )[0][0],
        2,
    )
    return flt(released + reversed_by_returns, 2)


@frappe.whitelist()
def get_unreleased_retention(contract: str) -> list[dict]:
    """Return submitted SIs on this contract with retention not yet fully released.

    Used by the 'Get Unreleased Retention' client action to populate entries.
    """
    frappe.has_permission("Retention Release", "create", throw=True)
    rows = []
    sis = frappe.db.sql(
        """
        select si.name, si.contracting_retention_amount
        from `tabSales Invoice` si
        join `tabProgress Claim` pc on pc.name = si.contracting_claim
        where si.docstatus = 1
          and pc.contract = %s
          and si.contracting_retention_amount > 0
        order by si.posting_date, si.name
        """,
        (contract,),
        as_dict=True,
    )
    for si in sis:
        retained = flt(si.contracting_retention_amount, 2)
        balance = flt(retained - released_for_invoice(si.name), 2)
        if balance <= 0:
            continue
        retention_je = frappe.db.get_value(
            "Journal Entry",
            {
                "contracting_purpose": "Retention",
                "contracting_reference_name": si.name,
                "docstatus": 1,
            },
            "name",
        )
        rows.append(
            {
                "sales_invoice": si.name,
                "retention_je": retention_je,
                "retained_amount": retained,
                "amount": balance,
                "balance": balance,
            }
        )
    return rows
