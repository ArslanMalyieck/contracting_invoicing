// Copyright (c) 2026, Arslan
// Contracting Contract form: "Record Advance" and "New Progress Claim" buttons
// + dashboard counts of linked claims and advances.

frappe.ui.form.on("Contracting Contract", {
	refresh(frm) {
		if (frm.doc.__islocal) return;
		_advance_button(frm);
		_claim_button(frm);
		_dashboard(frm);
	},
});

function _advance_button(frm) {
	if (frm.doc.status !== "Active") return;
	frm.add_custom_button(__("Record Advance"), () =>
		frappe.model.open_mapped_doc({
			method: "contracting_invoicing.api.make_advance_payment_entry",
			frm: frm,
		})
	);
}

function _claim_button(frm) {
	if (frm.doc.status !== "Active") return;
	frm.add_custom_button(__("New Progress Claim"), () =>
		frappe.model.open_mapped_doc({
			method: "contracting_invoicing.api.make_progress_claim",
			frm: frm,
		})
	);
}

function _dashboard(frm) {
	if (frm.doc.__unsaved) return;
	// Contract Advance is a CHILD TABLE (istable=1) - it has no permission
	// rows of its own by Frappe convention (access flows through the parent
	// only). Querying it directly via frappe.db.count() hits the generic
	// permission-checked list/count API and throws Insufficient Permission
	// for any non-Administrator user. It's already loaded as frm.doc.advances
	// as part of this document, so just count that - no server call needed.
	const advances = (frm.doc.advances || []).length;
	frm.dashboard.add_indicator(__("Advances: {0}", [advances]), advances ? "blue" : "grey");

	// Progress Claim is a real standalone doctype with its own permissions,
	// so a server count is correct and safe here.
	frappe.db.count("Progress Claim", { contract: frm.doc.name }).then((claims) => {
		frm.dashboard.add_indicator(__("Progress Claims: {0}", [claims]), claims ? "blue" : "grey");
		frm.dashboard.add_indicator(
			__("Advance Balance: {0} SAR", [frm.doc.advance_balance_gross || 0]),
			flt(frm.doc.advance_balance_gross) > 0 ? "green" : "grey"
		);
		frm.dashboard.add_indicator(
			__("Retention Held: {0} SAR", [frm.doc.retention_held || 0]),
			flt(frm.doc.retention_held) > 0 ? "orange" : "grey"
		);
	});
}

// ---------------------------------------------------------------------------
// Auto Advance Payment (server creates + submits the Payment Entry itself,
// with mode-of-payment account, VAT Deduct row -> clearing account and
// ZATCA prepayment flags). Added by the audit fix.
// ---------------------------------------------------------------------------
frappe.ui.form.on("Contracting Contract", {
	onload(frm) {
		if (!frm.doc.advance_posting_date) {
			frm.set_value("advance_posting_date", frappe.datetime.get_today());
		}
	},
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.advance_posting_date && !frm.doc.advance_reference_date) {
			frm.set_value("advance_reference_date", frm.doc.advance_posting_date);
		}
		if (!frm.doc.advance_reference_no) {
			frm.set_value("advance_reference_no", "ADV-" + frm.doc.name);
		}
		if (frm.doc.status === "Active" && flt(frm.doc.advance_percent) > 0) {
			frm.add_custom_button(__("Create Advance Payment"), function () {
				frappe.confirm(
					__(
						"Advance % ki limit ke andar Payment Entry banai jaegi (mode of payment aur VAT template ke sath) aur submit ho jayegi. Continue?"
					),
					function () {
						frappe.call({
							method: "contracting_invoicing.contracting_invoicing.doctype.contracting_contract.contracting_contract.create_advance_payment",
							args: { contract_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Creating advance Payment Entry..."),
							callback: function (r) {
								if (r.message) {
									frappe.show_alert({
										message: __("Advance Payment Entry {0} created", [r.message]),
										indicator: "green",
									});
									frm.reload_doc();
									frappe.set_route("Form", "Payment Entry", r.message);
								}
							},
						});
					}
				);
			});
		}
	},
	setup(frm) {
		frm.set_query("advance_mode_of_payment", function () {
			return { filters: { enabled: 1 } };
		});
		frm.set_query("advance_taxes_template", function () {
			return { filters: { company: frm.doc.company, docstatus: ["<", 2] } };
		});
	},
});
