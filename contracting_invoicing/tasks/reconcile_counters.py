# Copyright (c) 2026, Arslan
"""Nightly reconcile of Contracting Contract counters against GL.

Compares the contract's advance/retention/certified counters with the actual
GL postings and logs any drift via frappe.log_error. Never auto-corrects - a
human must investigate discrepancies (typically caused by manual JEs or direct
ledger edits outside the app's managed flow).
"""

import frappe
from frappe.utils import flt


def run():
	for contract in frappe.get_all("Contracting Contract", pluck="name"):
		try:
			_check_contract(contract)
		except Exception:
			frappe.log_error(title=f"Counter reconcile failed: {contract}")


def _check_contract(name):
	doc = frappe.get_cached_doc("Contracting Contract", name)
	settings = frappe.get_cached_doc("Contracting Settings", {"company": doc.company})

	gl_advance = _gl_recovered(doc)
	gl_retention = _gl_retention_held(doc, settings)
	gl_certified = _gl_certified(doc)

	drift = []
	if flt(doc.advance_recovered_gross - gl_advance, 2) != 0:
		drift.append(
			f"advance_recovered_gross: counter={doc.advance_recovered_gross} gl={gl_advance}"
		)
	if flt(doc.retention_held - gl_retention, 2) != 0:
		drift.append(f"retention_held: counter={doc.retention_held} gl={gl_retention}")
	if flt(doc.certified_to_date - gl_certified, 2) != 0:
		drift.append(f"certified_to_date: counter={doc.certified_to_date} gl={gl_certified}")
	if drift:
		frappe.log_error(
			title=f"Counter drift: {name}",
			message="; ".join(drift) + "\n\nInvestigate manually - no auto-correction applied.",
		)


def _gl_recovered(doc):
	"""Sum of allocated_amount on submitted SIs for this contract's submitted claims."""
	return flt(
		frappe.db.sql(
			"""
			select coalesce(sum(sia.allocated_amount), 0)
			from `tabSales Invoice Advance` sia
			join `tabSales Invoice` si on si.name = sia.parent
			where si.docstatus = 1
			  and si.contracting_claim in (
			    select name from `tabProgress Claim`
			    where contract = %s and docstatus = 1
			  )
			""",
			doc.name,
		)[0][0],
		2,
	)


def _gl_retention_held(doc, settings):
	"""Sum of net debits to the retention account via JEs linked to this contract's SIs."""
	posted = frappe.db.sql(
		"""
		select coalesce(sum(jea.debit_in_account_currency)
		       - sum(jea.credit_in_account_currency), 0)
		from `tabJournal Entry Account` jea
		join `tabJournal Entry` je on je.name = jea.parent
		where jea.account = %s
		  and je.docstatus = 1
		  and je.contracting_purpose = 'Retention'
		  and je.contracting_reference_name in (
		    select name from `tabSales Invoice`
		    where contracting_claim in (
		      select name from `tabProgress Claim`
		      where contract = %s and docstatus = 1
		    )
		  )
		""",
		(settings.retention_receivable_account, doc.name),
	)[0][0]
	return flt(posted or 0, 2)


def _gl_certified(doc):
	"""Sum of net_total on submitted SIs for this contract's submitted claims."""
	return flt(
		frappe.db.sql(
			"""
			select coalesce(sum(net_total), 0)
			from `tabSales Invoice`
			where docstatus = 1
			  and contracting_claim in (
			    select name from `tabProgress Claim`
			    where contract = %s and docstatus = 1
			  )
			""",
			doc.name,
		)[0][0],
		2,
	)
