# SOP: Refunding an Advance (Prepayment Invoice 386) — Contract Termination / Reduction

Scope: the rare case where a contract is terminated or reduced and the
UNRECOVERED part of a mobilization advance must be refunded to the client.
Deliberately a manual procedure (Part 3 §2.3) — do not automate until a
client actually needs it repeatedly.

Never do any of this by cancelling documents. A cleared 386 is immutable.

## Preconditions
- Contract status set to Defect Liability or Closed (blocks new claims).
- Confirm the unrecovered balance in Advance Recovery Statement and agree
  the figure with the client in writing before posting anything.

## Steps

1. **Credit note (383) for the unrecovered advance.**
   Create a Sales Invoice manually (NOT via a Progress Claim):
   - Tick "Is Return", leave `return_against` empty (the 386 is a Payment
     Entry, there is no SI to return against). Put the 386's invoice number
     and UUID in ksa_compliance's return/billing reference fields; fill the
     Return Reason.
   - One line, service item "Advance Refund", qty -1,
     rate = unrecovered NET; VAT 15% applies (reduces output VAT — correct,
     that VAT was declared when the advance was received).
   - Submit → ksa_compliance sends the 383. Verify Accepted.
   - OPEN QUESTION to verify on sandbox first: does ZATCA accept a 383
     whose billing reference is a PE-based 386? (Part 3 §4.4, untested.)
     If rejected: reference the contract's earliest progress invoice and
     keep the 386 number in remarks; record the outcome in SPIKE_FINDINGS.

2. **Clearing-account adjustment JE** — the clearing account still holds the
   unamortized VAT of the refunded portion:
   **Dr Output VAT / Cr VAT on Advances** for the VAT portion of the
   unrecovered amount. Check afterward: recovery-VAT JEs + this JE must sum
   to the advance's original tax_amount (clearing nets to zero).

3. **Refund Payment Entry** (type Pay, to the customer):
   amount = unrecovered GROSS, allocated against the original 386 PE's open
   customer balance so the party ledger nets to zero.

4. **Contract bookkeeping:** the Contract Advance row still shows a balance
   (only claims decrement it). Run `manual_tests/repair_counters.py` for the
   contract, then the nightly reconcile stays quiet.

5. Attach the client's written agreement + ZATCA acceptance to the contract.
   That is the audit-defense package.

## What NOT to do
- Do not cancel the 386 PE (blocked by ksa_compliance, and wrong).
- Do not restore recovery on already-submitted progress invoices.
- Do not skip step 2 — otherwise the clearing account never zeroes and the
  VAT position is off by the refund's VAT forever.
