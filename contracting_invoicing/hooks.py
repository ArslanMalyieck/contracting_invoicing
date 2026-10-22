app_name = "contracting_invoicing"
app_title = "Contracting Invoicing"
app_publisher = "Arslan"
app_description = (
    "Progress billing, advance recovery, retention and deductions for KSA "
    "contracting companies with ZATCA compliance"
)
app_email = "89395532+ArslanMalyieck@users.noreply.github.com"
app_license = "agpl-3.0"

required_apps = ["erpnext", "ksa_compliance"]

after_install = "contracting_invoicing.setup.install.after_install"
after_migrate = "contracting_invoicing.setup.install.after_migrate"

doctype_js = {
    "Contracting Contract": "public/js/contracting_contract.js",
    "Progress Claim": "public/js/progress_claim.js",
    "Retention Release": "public/js/retention_release.js",
    "Payment Entry": "public/js/zatca_now.js",
    "Sales Invoice": "public/js/zatca_now.js",
}

doc_events = {
    "Sales Invoice": {
        "before_validate": "contracting_invoicing.overrides.sales_invoice.before_validate",
        "validate": "contracting_invoicing.overrides.sales_invoice.validate",
        "on_submit": "contracting_invoicing.overrides.sales_invoice.on_submit",
        "before_cancel": "contracting_invoicing.overrides.sales_invoice.before_cancel",
        "on_cancel": "contracting_invoicing.overrides.sales_invoice.on_cancel",
    },
    "Payment Entry": {
        "validate": "contracting_invoicing.overrides.payment_entry.validate",
        "on_submit": "contracting_invoicing.overrides.payment_entry.on_submit",
        "on_cancel": "contracting_invoicing.overrides.payment_entry.on_cancel",
    },
    "Journal Entry": {
        "on_cancel": "contracting_invoicing.overrides.journal_entry.on_cancel",
        "on_trash": "contracting_invoicing.overrides.journal_entry.on_trash",
    },
}

scheduler_events = {
    "daily": [
        "contracting_invoicing.tasks.advance_deadline_alerts.run",
        "contracting_invoicing.tasks.reconcile_counters.run",
    ],
}
