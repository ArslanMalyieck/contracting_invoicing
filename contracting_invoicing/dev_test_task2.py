import frappe
def run():
    from frappe.utils import flt

    frappe.set_user("Administrator")

    # --- contract ---
    contract = frappe.get_doc({
        "doctype": "Contracting Contract",
        "contract_title": "JIP Dredging Works - Test",
        "customer": "Modern Building Demo Client",
        "company": "Demo Contracting Co",
        "contract_value": 10_000_000,
        "status": "Active",
        "advance_percent": 20,
        "recovery_percent": 10,
        "retention_percent": 10,
        "retention_cap_percent": 5,
        "defect_liability_months": 12,
    }).insert(ignore_permissions=True)
    print("CONTRACT:", contract.name)

    def make_advance_pe(amount, tax):
        return frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "company": "Demo Contracting Co",
            "party_type": "Customer",
            "party": "Modern Building Demo Client",
            "paid_from": "Debtors - DCC",
            "paid_to": frappe.db.get_value("Account", {"company": "Demo Contracting Co", "account_type": "Cash", "is_group": 0}),
            "paid_amount": amount,
            "received_amount": amount,
            "contracting_contract": contract.name,
            "custom_prepayment_invoice": 1,
            "custom_prepayment_invoice_description": "Advance Payment - JIP Dredging",
            "taxes": [{
                "charge_type": "Actual",
                "add_deduct_tax": "Deduct",
                "included_in_paid_amount": 0,
                "account_head": "VAT 15% - DCC",
                "description": "VAT 15% on advance",
                "tax_amount": tax,
            }],
        })

    pe = make_advance_pe(1_000_000, 150_000)
    pe.insert(ignore_permissions=True)
    pe.submit()
    print("PE submitted:", pe.name, "| paid:", pe.paid_amount, "| tax:", pe.total_taxes_and_charges)

    contract.reload()
    row = contract.advances[0]
    assert len(contract.advances) == 1, "advance row missing"
    assert flt(row.net_amount) == 1_000_000 and flt(row.tax_amount) == 150_000 and flt(row.gross_amount) == 1_150_000, f"row wrong: {row.as_dict()}"
    assert flt(contract.advance_received_net) == 1_000_000, contract.advance_received_net
    assert flt(contract.advance_balance_gross) == 1_150_000, contract.advance_balance_gross
    print("OK advance registered + counters:", contract.advance_received_net, contract.advance_balance_gross)

    # --- cancel restores ---
    pe.cancel()
    contract.reload()
    assert len(contract.advances) == 0 and flt(contract.advance_balance_gross) == 0, "cancel did not restore"
    print("OK cancel restored counters")

    # --- negative: advance on Draft contract blocked ---
    contract.db_set("status", "Draft")
    pe2 = make_advance_pe(100_000, 15_000)
    try:
        pe2.insert(ignore_permissions=True)
        print("FAIL: draft contract accepted advance")
    except Exception as e:
        print("OK negative (draft contract):", str(e)[:70])
    contract.db_set("status", "Active")

    # --- negative: wrong customer blocked ---
    if not frappe.db.exists("Customer", "Wrong Client"):
        frappe.get_doc({"doctype": "Customer", "customer_name": "Wrong Client",
            "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
            "territory": frappe.db.get_value("Territory", {"is_group": 0})}).insert(ignore_permissions=True)
    pe3 = make_advance_pe(100_000, 15_000)
    pe3.party = "Wrong Client"
    try:
        pe3.insert(ignore_permissions=True)
        print("FAIL: wrong customer accepted")
    except Exception as e:
        print("OK negative (wrong customer):", str(e)[:70])

    # --- resubmit a real advance for next tasks and leave it in place ---
    pe4 = make_advance_pe(1_000_000, 150_000)
    pe4.insert(ignore_permissions=True)
    pe4.submit()
    contract.reload()
    print("FINAL STATE - contract:", contract.name, "| advances:", len(contract.advances), "| balance_gross:", contract.advance_balance_gross)
    frappe.db.commit()

