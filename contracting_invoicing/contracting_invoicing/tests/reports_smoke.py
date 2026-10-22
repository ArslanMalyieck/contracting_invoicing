"""Smoke-test the 4 contracting_invoicing reports via bench execute path."""
from __future__ import annotations

import json

import frappe

from contracting_invoicing.contracting_invoicing.report.retention_ledger.retention_ledger import (
    execute as rl_execute,
)
from contracting_invoicing.contracting_invoicing.report.advance_recovery_statement.advance_recovery_statement import (
    execute as ar_execute,
)
from contracting_invoicing.contracting_invoicing.report.contract_progress_statement.contract_progress_statement import (
    execute as cp_execute,
)
from contracting_invoicing.contracting_invoicing.report.contracting_invoice_summary.contracting_invoice_summary import (
    execute as cs_execute,
)


def _print(name: str, result: tuple) -> None:
    columns, rows = result
    print(f"\n=== {name} ===")
    print("cols:", [c.get("label") for c in columns])
    print("rows:", len(rows))
    for r in rows[:3]:
        print(json.dumps(r, default=str))


def run() -> None:
    frappe.flags.in_test = True
    _print("retention_ledger", rl_execute(filters={}))
    _print("advance_recovery_statement", ar_execute(filters={}))
    _print("contract_progress_statement", cp_execute(filters={}))
    _print("contracting_invoice_summary", cs_execute(filters={}))


if __name__ == "__main__":
    run()
