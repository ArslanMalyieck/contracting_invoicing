# Copyright (c) 2026, Arslan
"""Contracting Settings: per-company configuration for contracting billing.

Basis and account fields are locked once submitted Progress Claims exist for
the company, because changing them would make historical figures inconsistent.
"""

import frappe
from frappe import _
from frappe.model.document import Document

LOCKED_FIELDS = [
    "retention_basis",
    "advance_recovery_basis",
    "retention_receivable_account",
]


class ContractingSettings(Document):
    def validate(self):
        self._validate_currency()
        self._validate_retention_account()
        self._validate_locked_fields()
        self._validate_retention_posting()

    def _validate_currency(self):
        currency = frappe.get_cached_value("Company", self.company, "default_currency")
        if currency != "SAR":
            frappe.throw(
                _("Contracting Invoicing supports SAR companies only. {0} uses {1}.").format(
                    self.company, currency
                )
            )

    def _validate_retention_account(self):
        account_type, company = frappe.db.get_value(
            "Account", self.retention_receivable_account, ["account_type", "company"]
        )
        if account_type != "Receivable":
            frappe.throw(
                _("Retention Receivable Account must be of type Receivable so that "
                  "customer-wise balances and collection via Payment Entry work.")
            )
        if company != self.company:
            frappe.throw(_("Retention Receivable Account must belong to {0}.").format(self.company))

    def _validate_locked_fields(self):
        if self.is_new():
            return
        if not frappe.db.exists("DocType", "Progress Claim"):
            return
        if not frappe.db.exists(
            "Progress Claim", {"company": self.company, "docstatus": 1}
        ):
            return
        before = self.get_doc_before_save()
        if not before:
            return
        for field in LOCKED_FIELDS:
            if before.get(field) != self.get(field):
                frappe.throw(
                    _("{0} is locked because submitted Progress Claims exist for {1}. "
                      "Changing it would make historical retention/recovery figures inconsistent.").format(
                        _(self.meta.get_label(field)), self.company
                    )
                )

    def _validate_retention_posting(self):
        if self.retention_posting == "On Payment":
            frappe.throw(
                _("Retention Posting 'On Payment' is planned for a later release. "
                  "Use 'On Invoice Submit'.")
            )


def get_settings(company: str) -> "ContractingSettings":
    """Fetch settings for a company or throw with a helpful message."""
    name = frappe.db.exists("Contracting Settings", {"company": company})
    if not name:
        frappe.throw(
            _("Contracting Settings not found for {0}. Create it under "
              "Contracting Invoicing > Contracting Settings before submitting claims.").format(company)
        )
    return frappe.get_cached_doc("Contracting Settings", name)
