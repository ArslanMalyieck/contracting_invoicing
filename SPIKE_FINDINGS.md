# SPIKE FINDINGS — ksa_compliance 0.61.4 prepayment flow

STATUS: **SPIKE COMPLETE** — both code-level analysis AND live ZATCA sandbox
verification done (2026-07-04). Sandbox verdicts override my earlier
code-level conclusions where they differ; corrections noted honestly below.

## Sandbox setup (reproducible, all local)
- Onboarded ZATCA **Sandbox** from the local bench: compliance CSID +
  production CSID via `zbs.onboard(otp='123345')` / `get_production_csid`.
- ZATCA CLI 2.10.0 + Temurin JRE 11 **aarch64** at
  `sites/frontend/zatca-tools/` (their DEFAULT_JRE_URL is x64 — fails on
  Apple Silicon Docker with a qemu loader error; use the aarch64 tarball,
  java_home = .../jdk-arm).
- ZBS: `Demo Contracting Co-Saudi Arabia-SAR-03`, enable_zatca_integration=1.
- No queue workers on this bench → submissions run synchronously via
  `siaf.submit_to_zatca()`.

## VERDICTS (evidence: manual_tests/evidence/spike_388.xml + integration logs)

V1. **386 prepayment invoice (PE-based): ACCEPTED** by sandbox
    (ACC-PAY-2026-00008, "Accepted with warnings" — warnings are test-data
    cosmetics only: BR-KSA-08 seller CRN, BR-KSA-37, BR-KSA-81 buyer other ID).

V2. **388 with PARTIAL advance recovery: ACCEPTED.** SI 4,646,817.99 + 15%,
    allocation 534,384.07 gross against the 386. XML contained
    PrepaidAmount=534,384.07 (CORRECT), TaxInclusive=5,343,840.69,
    Payable=4,809,456.93. ZERO prepayment-related warnings/errors.
    → The Huta partial-recovery pattern is compliant through their flow.

V3. **CORRECTION of my earlier D1:** `_get_prepaid_amount()` in
    prepayment_invoice_factory.py IS broken as written (returns 384,384.07
    for this case when called directly) — but it is NOT what feeds the live
    XML. The production path assembles PrepaidAmount correctly. D1 is dead/
    superseded code, not a live defect. No upstream urgency.

V4. **CORRECTION of my earlier D2:** live PayableAmount DOes subtract
    prepaid. The `payable_amount = grand_total + rounding` line I flagged is
    similarly not the effective path for prepayment invoices. Not a live
    defect.

V5. **D3 STANDS (the one real issue): the prescribed PE GL is wrong** —
    Dr VAT / Cr Bank (withholding-shaped). This is accounting, not XML;
    sandbox can't bless or damn it. Our clearing-account model fixes it and
    is IMPLEMENTED + GL-verified (see below). Upstream: raise as a
    documentation/design discussion with Lavaloon, low urgency, after we
    have the full cycle running.

V6. New: ERPNext computes outstanding from **rounded_total**
    (5,343,841.00) → outstanding 4,809,456.93, a 0.31 drift vs exact.
    Task 4 must either recommend disabling rounded totals for contracting
    companies or base net_amount_due on the same figure ERPNext uses.

## Confirmed mechanics (unchanged, settle BUILD SPEC §4.2/§8.3)
- `advances.allocated_amount` is **GROSS** (VAT-inclusive); PE paid_amount
  entered GROSS; template on PE mandatory (XML rate source); Deduct taxes
  stored negative (abs() in our code).

## Adopted + implemented accounting model (Toetoe-approved)
- PE Deduct row → **VAT on Advances - {abbr}** clearing account.
- Auto JE on advance submit: Dr Bank / Cr Output VAT (purpose: Advance VAT).
- Task 4 adds per-claim: Dr Output VAT (recovery VAT) / Cr Clearing.
- GL verified: bank +1,150,000 / customer Cr 1,150,000 / Output VAT
  Cr 150,000 / Clearing Dr 150,000. Guards + cancel chain tested.

## Remaining sandbox items (roll into task-4 testing, no separate gate)
- Return SI against a contracting invoice: advances-copy behavior + XML.
- 383 referencing a PE-based 386 (advance refund SOP).
- Full Huta 3-claim cycle end-to-end once Progress Claim exists.
