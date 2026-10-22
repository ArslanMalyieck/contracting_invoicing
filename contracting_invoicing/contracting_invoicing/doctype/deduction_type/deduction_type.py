# Copyright (c) 2026, Arslan
import frappe
from frappe import _
from frappe.model.document import Document


class DeductionType(Document):
    def validate(self):
        if self.treatment == "Back-charge":
            frappe.msgprint(
                _("Back-charge treatment lands in a later release. Claims using this "
                  "type will be blocked at submission - record as Payment-side "
                  "Deduction for now."),
                indicator="orange",
            )
        if self.treatment != "Contract Value Adjustment":
            self.reverses_retention = 0
