# Copyright (c) 2026, Arslan
"""Per-company account and role setup. Idempotent - safe on every migrate."""

import frappe
from frappe import _

ROLES = ["Contracting Manager", "Contracting User"]


def create_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1}
            ).insert(ignore_permissions=True)


def create_accounts_for_company(company: str) -> str | None:
    """Create 'Retention Receivable' under the AR group for a SAR company.

    Returns the account name, or None if the company is skipped (non-SAR or
    no receivable group found - e.g. a template/holding company).
    """
    currency = frappe.get_cached_value("Company", company, "default_currency")
    if currency != "SAR":
        return None

    abbr = frappe.get_cached_value("Company", company, "abbr")
    account_name = f"Retention Receivable - {abbr}"
    if frappe.db.exists("Account", account_name):
        return account_name

    parent = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "account_type": "Receivable",
            "is_group": 1,
        },
    ) or frappe.db.get_value(
        "Account",
        {"company": company, "root_type": "Asset", "is_group": 1, "account_name": ["like", "%Receivable%"]},
    )
    if not parent:
        # Fall back to the parent of the default receivable account
        default_receivable = frappe.get_cached_value(
            "Company", company, "default_receivable_account"
        )
        if default_receivable:
            parent = frappe.db.get_value("Account", default_receivable, "parent_account")
    if not parent:
        return None

    account = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": "Retention Receivable",
            "parent_account": parent,
            "company": company,
            "account_type": "Receivable",
            "account_currency": "SAR",
        }
    )
    account.insert(ignore_permissions=True)
    return account.name


def create_advance_vat_clearing_account(company: str) -> str | None:
    """Create 'VAT on Advances' clearing account under the tax liabilities group.

    Absorbs the prepayment PE's Deduct tax row (ksa_compliance-enforced) and is
    amortized by recovery JEs. See SPIKE_FINDINGS.md - adopted accounting model.
    """
    currency = frappe.get_cached_value("Company", company, "default_currency")
    if currency != "SAR":
        return None
    abbr = frappe.get_cached_value("Company", company, "abbr")
    account_name = f"VAT on Advances - {abbr}"
    if frappe.db.exists("Account", account_name):
        return account_name
    parent = frappe.db.get_value(
        "Account",
        {"company": company, "is_group": 1, "account_name": ["like", "%Duties and Taxes%"]},
    ) or frappe.db.get_value(
        "Account", {"company": company, "root_type": "Liability", "is_group": 1}
    )
    if not parent:
        return None
    account = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": "VAT on Advances",
            "parent_account": parent,
            "company": company,
            "account_type": "Tax",
            "account_currency": "SAR",
        }
    )
    account.insert(ignore_permissions=True)
    return account.name


def create_accounts():
    for company in frappe.get_all("Company", pluck="name"):
        create_accounts_for_company(company)
        create_advance_vat_clearing_account(company)
