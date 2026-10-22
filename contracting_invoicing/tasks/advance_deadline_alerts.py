# Copyright (c) 2026, Arslan
"""Daily alert: advances whose ZATCA prepayment invoice has not cleared as the
statutory deadline (month-end + 15 days) approaches.

ZATCA requires the advance (prepayment) invoice within 15 days after the end
of the month the advance was received. Sends warnings to Contracting Managers
at day 8 and day 13 after month end. Enabled per-company via the
'Advance Invoice Deadline Alerts' setting (Contracting Settings).
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_last_day, getdate, nowdate

DEADLINE_DAYS = 15
ALERT_DAYS = (8, 13, 0)


def run():
	today = getdate(nowdate())
	for company in _enabled_companies():
		managers = _contracting_managers()
		if not managers:
			continue
		for adv in _pending_advances(company, today):
			deadline = add_days(get_last_day(adv.posting_date), DEADLINE_DAYS)
			days_left = (deadline - today).days
			if days_left in ALERT_DAYS:
				_notify(managers, adv, days_left, deadline)


def _enabled_companies():
	return frappe.get_all(
		"Contracting Settings", filters={"advance_deadline_alert": 1}, pluck="company"
	)


def _contracting_managers():
	return frappe.get_all(
		"Has Role",
		filters={"role": "Contracting Manager", "parenttype": "User"},
		pluck="parent",
	)


def _pending_advances(company, today):
	"""Contract advances from the last 45 days whose PE has no accepted SIAF."""
	rows = frappe.db.sql(
		"""
		select ca.payment_entry, ca.posting_date, ca.gross_amount,
		       ca.parent as contract
		from `tabContract Advance` ca
		join `tabContracting Contract` cc on cc.name = ca.parent
		where cc.company = %s
		  and ca.posting_date >= date_sub(%s, interval 45 day)
		""",
		(company, today),
		as_dict=True,
	)
	pending = []
	for r in rows:
		if not _is_zatca_cleared(r.payment_entry):
			pending.append(r)
	return pending


def _is_zatca_cleared(payment_entry):
	"""True when ZATCA integration is off, or the 386 was accepted."""
	siaf_status = frappe.db.get_value(
		"Sales Invoice Additional Fields",
		{"sales_invoice": payment_entry, "docstatus": ["<", 2]},
		"integration_status",
	)
	if siaf_status is None:
		return not frappe.db.get_value(
			"ZATCA Business Settings",
			{
				"company": frappe.db.get_value("Payment Entry", payment_entry, "company"),
				"enable_zatca_integration": 1,
			},
		)
	return siaf_status in ("Accepted", "Accepted with warnings", "Clearance switched off")


def _notify(managers, adv, days_left, deadline):
	subject = _("ZATCA advance invoice deadline: {0}").format(adv.payment_entry)
	if days_left > 0:
		body = _(
			"Advance {0} on contract {1} ({2} SAR) was received on {3}. The ZATCA "
			"prepayment invoice is due by {4} - {5} days left. Submit it from the "
			"Payment Entry before the deadline."
		).format(
			adv.payment_entry, adv.contract, adv.gross_amount,
			adv.posting_date, deadline, days_left,
		)
	else:
		body = _(
			"Advance {0} on contract {1} ({2} SAR) - the ZATCA prepayment invoice "
			"deadline ({3}) is TODAY. Submit immediately to avoid non-compliance."
		).format(adv.payment_entry, adv.contract, adv.gross_amount, deadline)
	for user in managers:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"subject": subject,
				"document_type": "Payment Entry",
				"document_name": adv.payment_entry,
				"for_user": user,
				"email_content": body,
			}
		).insert(ignore_permissions=True)
