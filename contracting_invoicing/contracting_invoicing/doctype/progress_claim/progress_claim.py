# Copyright (c) 2026, Arslan
"""Progress Claim: the one document accountants touch.

On submit it computes recovery/retention/deductions, generates the Sales
Invoice with FULL-value lines plus ZATCA prepayment allocations, and links it.
All GL side-effects (retention JE, deduction JEs, recovery-VAT JE, counter
updates) post when the Sales Invoice is submitted - see overrides/sales_invoice.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from contracting_invoicing.contracting_invoicing.doctype.contracting_settings.contracting_settings import (
    get_settings,
)

DEFAULT_ITEM = "Works Executed"


class ProgressClaim(Document):
    def _reset_managed_on_new(self):
        """Duplicated claims must not carry the source's generated links and
        counters. Clear every system-managed field on new documents."""
        if not self.is_new():
            return
        self.sales_invoice = None
        self.retention_amount = 0
        self.advance_recovery_gross = 0
        self.net_amount_due = 0
        self.previous_certified_value = 0
        # Keep a genuine amend link (amended_from -> cancelled document); only
        # clear a stale link that the Duplicate action copied from a live doc
        # (Frappe rejects an amended_from that does not point to a cancelled doc).
        if self.amended_from and frappe.db.get_value(
            "Progress Claim", self.amended_from, "docstatus"
        ) != 2:
            self.amended_from = None

    def validate(self):
        self._reset_managed_on_new()
        self._clear_stale_links_on_amend()
        self._set_period_values()
        self._validate_items_total()
        count = self.claim_no or (self._submitted_claim_count() + 1)
        self.title = _("{0} - Claim {1}").format(self.contract, count)

    def _clear_stale_links_on_amend(self):
        """Defensive: sales_invoice is no_copy so the UI Amend clears it, but
        server-side frappe.copy_doc(ignore_no_copy=True) - the default - can
        drag a cancelled invoice's link along. Never trust a stale link."""
        if self.docstatus == 0 and self.sales_invoice:
            if frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus") != 1:
                self.sales_invoice = None
                self.claim_no = None

    def _submitted_claim_count(self) -> int:
        return frappe.db.count(
            "Progress Claim",
            {"contract": self.contract, "docstatus": 1, "name": ["!=", self.name]},
        )

    def _set_period_values(self):
        rows = frappe.get_all(
            "Progress Claim",
            filters={"contract": self.contract, "docstatus": 1, "name": ["!=", self.name]},
            fields=["cumulative_certified_value"],
        )
        prev = max([flt(r.cumulative_certified_value) for r in rows], default=0)
        self.previous_certified_value = flt(prev, 2)
        self.current_certified_value = flt(
            flt(self.cumulative_certified_value) - self.previous_certified_value, 2
        )
        if self.current_certified_value <= 0:
            frappe.throw(
                _(
                    "Cumulative certified value ({0}) must exceed the previously "
                    "certified value ({1})."
                ).format(self.cumulative_certified_value, self.previous_certified_value)
            )

    def _validate_items_total(self):
        if not self.items:
            return
        for row in self.items:
            row.amount = flt(flt(row.qty) * flt(row.rate), 2)
        total = flt(sum(flt(r.amount) for r in self.items), 2)
        if total != flt(self.current_certified_value, 2):
            frappe.throw(
                _("Items total ({0}) must equal This Period (Net) ({1}).").format(
                    total, self.current_certified_value
                )
            )

    def before_submit(self):
        self.claim_no = self._submitted_claim_count() + 1
        settings = get_settings(self.company)
        contract = frappe.get_doc("Contracting Contract", self.contract)
        if contract.status != "Active":
            frappe.throw(_("Contract {0} is {1}, not Active.").format(contract.name, _(contract.status)))
        self._validate_deductions()
        si = self._build_invoice(settings, contract)
        self._compute_retention(si, settings, contract)
        self._allocate_recovery(si, settings, contract)
        si.insert(ignore_permissions=True)
        self.sales_invoice = si.name
        self._compute_net_amount_due(si)
        si.db_set("contracting_claim", self.name)
        si.db_set("contracting_retention_amount", self.retention_amount)
        si.db_set("contracting_retention_deducted", self.retention_deducted)
        si.db_set("contracting_advance_recovery", self.advance_recovery_gross)
        si.db_set("contracting_net_amount_due", self.net_amount_due)
        self.db_set("retention_amount", self.retention_amount, update_modified=False)
        self.db_set("advance_recovery_gross", self.advance_recovery_gross, update_modified=False)
        self.db_set("net_amount_due", self.net_amount_due, update_modified=False)
        if settings.auto_submit_generated_invoice:
            si.submit()

    def _validate_deductions(self):
        for row in self.deductions:
            treatment = frappe.db.get_value("Deduction Type", row.deduction_type, "treatment")
            row.treatment = treatment
            if flt(row.amount) <= 0:
                frappe.throw(_("Deduction amounts must be positive."))
            if treatment in ("Back-charge", "Contract Value Adjustment"):
                frappe.throw(
                    _(
                        "Deduction treatment '{0}' lands in the next release. Use "
                        "Payment-side Deduction for now."
                    ).format(_(treatment))
                )

    def _build_invoice(self, settings, contract):
        items = []
        if self.items:
            for row in self.items:
                items.append(
                    {
                        "item_code": row.item,
                        "description": row.description,
                        "qty": row.qty,
                        "rate": row.rate,
                    }
                )
        else:
            items.append(
                {
                    "item_code": DEFAULT_ITEM,
                    "description": _("Value of Works Executed - {0} to {1}").format(
                        self.period_from, self.period_to
                    ),
                    "qty": 1,
                    "rate": self.current_certified_value,
                }
            )
        si = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "company": self.company,
                "customer": self.customer,
                "posting_date": self.posting_date,
                "set_posting_time": 1,
                "currency": "SAR",
                "disable_rounded_total": 1,
                "project": contract.project,
                "taxes_and_charges": self.taxes_template,
                "items": items,
            }
        )
        si.set_missing_values()
        # pull taxes from the template explicitly (set_missing_values may skip
        # when tax categories are configured)
        if not si.taxes:
            template = frappe.get_doc("Sales Taxes and Charges Template", self.taxes_template)
            for tax in template.taxes:
                si.append("taxes", tax.as_dict(no_default_fields=True))
        si.calculate_taxes_and_totals()
        return si

    def _basis(self, si, which: str) -> float:
        return flt(si.net_total if which == "Net Total" else si.grand_total, 2)

    def _compute_retention(self, si, settings, contract):
        if (
            (contract.get("retention_mode") or "Percentage") == "Amount"
            and flt(self.cumulative_certified_value) == flt(contract.contract_value)
            and flt(self.previous_certified_value) == 0
        ):
            # Single certificate covering the whole contract: withhold the exact
            # amount entered on the contract (the 4-decimal % is only a display
            # derivation and could differ by a few halalas).
            retention = flt(contract.retention_amount, 2)
        else:
            retention = flt(
                flt(contract.retention_percent) / 100 * self._basis(si, settings.retention_basis), 2
            )
        if flt(contract.retention_cap_percent):
            cap = flt(
                flt(contract.retention_cap_percent) / 100 * flt(contract.contract_value), 2
            )
            room = flt(cap - flt(contract.retention_held), 2)
            retention = min(retention, max(room, 0))
        self.retention_amount = flt(retention, 2)

    def _allocate_recovery(self, si, settings, contract):
        """Apply the advance recovery as an item-level allowance (ZATCA
        discount), so VAT is charged on the value of works NET of the recovered
        advance. The allowance is posted against the Customer Advances
        liability (not revenue) by a reclass JE on invoice submit, keeping the
        certified revenue intact."""
        from contracting_invoicing.contracting_invoicing.doctype.contracting_contract.contracting_contract import (
            get_advance_vat_rate,
            get_open_advances,
        )

        target = flt(
            flt(contract.recovery_percent)
            / 100
            * self._basis(si, settings.advance_recovery_basis),
            2,
        )
        open_advances = get_open_advances(contract.name)
        for adv in open_advances:
            if not self._advance_is_zatca_cleared(adv["payment_entry"]):
                frappe.throw(
                    _(
                        "Advance {0} has not been accepted by ZATCA yet, so it cannot "
                        "be recovered on this claim. Submit it to ZATCA first (see the "
                        "Payment Entry's e-invoicing status)."
                    ).format(adv["payment_entry"])
                )

        if target <= 0 or not open_advances:
            retention_deducted = 0.0
            if (
                flt(contract.get("retention_deduct_when_no_advance"))
                and flt(self.retention_amount) > 0
            ):
                retention_deducted = flt(self.retention_amount, 2)
            if retention_deducted > 0:
                si.apply_discount_on = "Net Total"
                si.discount_amount = retention_deducted
                if si.meta.has_field("custom_zatca_discount_reason"):
                    si.custom_zatca_discount_reason = "Discount"
                si.calculate_taxes_and_totals()
            self.advance_recovery_gross = 0.0
            self.advance_recovery_net = 0.0
            self.retention_deducted = retention_deducted
            return

        vat_rate = flt(get_advance_vat_rate(contract), 2)
        ratio = 1 + vat_rate / 100
        open_gross = flt(sum(flt(a["balance_gross"], 2) for a in open_advances), 2)
        if settings.advance_recovery_basis == "Net Total":
            recovery_net = min(target, flt(open_gross / ratio, 2))
            recovery_gross = flt(recovery_net * ratio, 2)
        else:
            recovery_gross = min(target, open_gross)
            recovery_net = flt(recovery_gross / ratio, 2)

        total_amount = flt(sum(flt(item.amount, 2) for item in si.items), 2)
        if total_amount <= 0 or recovery_net <= 0:
            self.advance_recovery_gross = 0.0
            self.advance_recovery_net = 0.0
            self.retention_deducted = 0.0
            return
        si.apply_discount_on = "Net Total"
        si.discount_amount = flt(recovery_net, 2)
        if si.meta.has_field("custom_zatca_discount_reason"):
            si.custom_zatca_discount_reason = "Discount"
        si.calculate_taxes_and_totals()
        self.advance_recovery_gross = recovery_gross
        self.advance_recovery_net = recovery_net
        self.retention_deducted = 0.0

    @staticmethod
    def _advance_is_zatca_cleared(payment_entry: str) -> bool:
        """True when no ZATCA integration applies, or the 386 was accepted."""
        siaf = frappe.db.get_value(
            "Sales Invoice Additional Fields",
            {"sales_invoice": payment_entry, "docstatus": ["<", 2]},
            "integration_status",
        )
        if siaf is None:
            # no SIAF: integration off for this company/document
            return not frappe.db.get_value(
                "ZATCA Business Settings",
                {
                    "company": frappe.db.get_value("Payment Entry", payment_entry, "company"),
                    "enable_zatca_integration": 1,
                },
            )
        return siaf in ("Accepted", "Accepted with warnings", "Clearance switched off")

    def _compute_net_amount_due(self, si):
        payment_side = flt(
            sum(flt(d.amount) for d in self.deductions if d.treatment == "Payment-side Deduction"),
            2,
        )
        base = flt(si.rounded_total) or flt(si.grand_total)
        retention = (
            0.0
            if flt(getattr(self, "retention_deducted", 0))
            else flt(self.retention_amount)
        )
        self.net_amount_due = flt(base - retention - payment_side, 2)

    def on_cancel(self):
        if not self.sales_invoice or not frappe.db.exists("Sales Invoice", self.sales_invoice):
            return
        si_docstatus = frappe.db.get_value(
            "Sales Invoice", self.sales_invoice, "docstatus"
        )
        if si_docstatus == 1:
            frappe.throw(
                _("Cancel the linked Sales Invoice {0} first.").format(self.sales_invoice)
            )
        if si_docstatus == 0:
            # The claim was cancelled before its draft invoice was submitted:
            # remove that draft so it does not stay orphaned. Submitted invoices
            # are never touched (the user must cancel them first, which posts the
            # reversing entries).
            si_name = self.sales_invoice
            self.db_set("sales_invoice", None, update_modified=False)
            self.sales_invoice = None
            frappe.delete_doc(
                "Sales Invoice",
                si_name,
                force=1,
                ignore_permissions=True,
            )
