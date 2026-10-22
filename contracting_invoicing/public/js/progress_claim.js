// Copyright (c) 2026, Arslan
// Progress Claim form: "View Invoice" button when the Sales Invoice exists.

frappe.ui.form.on("Progress Claim", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
			frm.add_custom_button(__("View Invoice"), () =>
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice)
			);
		}
	},
});
