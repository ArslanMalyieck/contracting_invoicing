// Copyright (c) 2026, Arslan
// Retention Release form: "Get Unreleased Retention" button to auto-populate
// entries from the contract's submitted invoices with unreleased retention.

frappe.ui.form.on("Retention Release", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Get Unreleased Retention"), () => {
			if (!frm.doc.contract) {
				frappe.msgprint(__("Select a contract first."));
				return;
			}
			frappe.call({
				method: "contracting_invoicing.contracting_invoicing.doctype.retention_release.retention_release.get_unreleased_retention",
				args: { contract: frm.doc.contract },
				callback: (r) => {
					if (!r.message || !r.message.length) {
						frappe.msgprint(__("No unreleased retention found for this contract."));
						return;
					}
					frm.clear_table("entries");
					r.message.forEach((row) => {
						frm.add_child("entries", row);
					});
					frm.refresh_field("entries");
					frm.dirty();
				},
			});
		});
	},
});
