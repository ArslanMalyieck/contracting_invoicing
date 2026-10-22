// Copyright (c) 2026, Arslan
// Manual "Submit to ZATCA Now" button - bypasses ksa_compliance's background
// batch queue for immediate, synchronous submission. Shows on Payment Entry
// (prepayment/386) and Sales Invoice (progress/388, credit notes/383) when
// there is a pending ("Ready For Batch") ZATCA submission.

function add_zatca_now_button(frm, sales_invoice_field) {
	if (frm.doc.__islocal || frm.doc.docstatus !== 1) return;
	const invoice_name = sales_invoice_field ? frm.doc.name : frm.doc.name;
	frappe.db.get_value(
		"Sales Invoice Additional Fields",
		{ sales_invoice: invoice_name, docstatus: ["<", 2] },
		"integration_status"
	).then(({ message }) => {
		const status = message && message.integration_status;
		if (!["Ready For Batch", "Resend", "Corrected"].includes(status)) return;
		frm.add_custom_button(__("Submit to ZATCA Now"), () => {
			frappe.call({
				method: "contracting_invoicing.api.submit_now",
				args: { sales_invoice: invoice_name },
				freeze: true,
				freeze_message: __("Submitting to ZATCA..."),
			}).then((r) => {
				frappe.show_alert({ message: r.message, indicator: "green" }, 8);
				frm.reload_doc();
			});
		}).addClass("btn-primary");
	});
}

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		if (frm.doc.custom_prepayment_invoice) add_zatca_now_button(frm, true);
		recompute_prepayment_tax(frm);
	},
	paid_amount(frm) {
		recompute_prepayment_tax(frm);
	},
	received_amount(frm) {
		recompute_prepayment_tax(frm);
	},
	taxes_on_form_rendered(frm) {
		recompute_prepayment_tax(frm);
	},
	custom_prepayment_invoice(frm) {
		recompute_prepayment_tax(frm);
	},
	validate(frm) {
		recompute_prepayment_tax(frm);
	},
});

// KSA compliance requires Charge Type = "Actual" on prepayment invoices with no
// Sales Order, so ERPNext will not auto-calculate the tax. The amount must equal
// net x rate where net = paid_amount / (1 + rate/100), keeping the Actual +
// Deduct row in sync with the gross amount the user enters. This covers both
// the "VAT added on top" and "VAT inclusive" amount bases - the Payment Entry
// always treats paid_amount as the VAT-inclusive gross.
function recompute_prepayment_tax(frm) {
	if (!frm.doc.custom_prepayment_invoice) return;
	const gross = flt(frm.doc.paid_amount);
	if (!gross) return;
	(frm.doc.taxes || []).forEach((row) => {
		if (row.charge_type !== "Actual" || row.add_deduct_tax !== "Deduct") return;
		const rate = flt(row.rate);
		if (!rate) return;
		const tax = flt(gross - gross / (1 + rate / 100), 2);
		if (flt(row.tax_amount, 2) !== tax) {
			frappe.model.set_value(row.doctype, row.name, "tax_amount", tax);
		}
	});
}

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.contracting_claim || frm.doc.is_return) add_zatca_now_button(frm, true);
	},
});
