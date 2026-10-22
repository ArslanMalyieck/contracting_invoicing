# BUILD STATUS — contracting_invoicing (living doc)

## Environment
- Dev: Mac Mini (user talhakafeel), frappe_docker, backend container
  `frappe_docker-backend-1`, site `frontend` @ localhost:8080
- Stack: Frappe 16.20.0 / ERPNext 16.22.0 / ksa_compliance 0.61.4 (master)
  → we develop on v16; v15 compatibility verified via CI later (clients run 15)
- App source of truth: this folder's `app/` (git, branch main).
  Container copy at /home/frappe/frappe-bench/apps/contracting_invoicing —
  sync via docker cp both ways.
- KNOWN ISSUES:
  - scheduler container crash-looping (Restarting) — scheduler_events will
    NOT fire locally until fixed. Not blocking schema/logic work. Tasks
    verified by manual `bench execute` invocation.
  - Site had never run setup wizard; Warehouse Type 'Transit' was missing
    (created manually). Watch for other missing seed records.
  - ksa_compliance 0.61.4: _get_prepaid_amount() defect confirmed as DEAD
    code (not the live path) — see SPIKE_FINDINGS V3. No upstream urgency.
    PB-SPIKE COMPLETE (no longer pending).

## Site test data
- Company: Demo Contracting Co (DCC), SAR, Standard CoA
- Accounts: Retention Receivable - DCC (Receivable, under Accounts
  Receivable - DCC), VAT 15% - DCC + 'KSA VAT 15%' sales tax template
- Customer: Modern Building Demo Client
- Contracting Settings for DCC created (deduction acct: Miscellaneous
  Expenses - DCC)

## Done
- [x] Task 1: scaffold; Contracting Settings (validations: SAR-only,
  receivable-type account, locked-fields-after-claims, On Payment blocked);
  Deduction Type; custom fields on SI/PE/JE (in code, idempotent);
  roles; per-company retention account creation; hooks.py full surface;
  JE manual-cancel/delete guards (active); SI on_cancel JE chain (active);
  SI return advances-clearing guard (active). Install + double-run
  idempotency verified. Negative test on account type passed.

## Done (continued)
- [x] Task 2: Contracting Contract + Contract Advance child + PE hooks
  (validate: company/customer/active/limit-with-manager-override; on_submit
  registers advance gross/net; on_cancel restores, blocks if recovered).
  Live test green incl. negatives. Committed advance on CC-2026-0002
  (1,150,000 gross) left on site for task 4.
- [x] Task 3 (code half): SPIKE_FINDINGS.md — allocated=GROSS confirmed;
  PE needs sales_taxes_and_charges_template; THREE upstream defects found
  (BT-113 formula, PayableAmount ignores prepaid, withholding-shaped GL);
  clearing-account model designed (pending Toetoe sign-off).
- Site seeded (was never bootstrapped): System Settings language, Fiscal
  Year 2026, UOM Nos, Price List Standard Selling (SAR), Global Defaults
  SAR, Item Group Services, Item 'Works Executed'. Seed script:
  manual_tests/seed_site.py (base for demo-data task).

## Done (continued 2)
- [x] Clearing-account VAT model APPROVED + implemented + GL-verified
  (VAT on Advances account, settings fields output_vat_account /
  advance_vat_clearing_account, Advance VAT JE, ZATCA validations).
- [x] **SANDBOX SPIKE COMPLETE — run by Claude, no human gate needed.**
  ZATCA sandbox onboarded from this bench (CSID + PCSID). 386 ACCEPTED.
  388 with PARTIAL recovery (Huta numbers) ACCEPTED, PrepaidAmount correct
  in live XML. My earlier D1/D2 code-level defect claims were WRONG for the
  live path (corrected in SPIKE_FINDINGS). D3 (GL) stands - solved by our
  model. Evidence: manual_tests/evidence/spike_388.xml.
- Site now ZATCA-enabled: ZBS Demo Contracting Co-Saudi Arabia-SAR-03,
  Sandbox, CLI at sites/frontend/zatca-tools (aarch64 JRE at jdk-arm).
  Customer has VAT no + address; Tax Category 'Standard 15' mapped.
- NOTE: prepayment PEs can no longer be cancelled (ksa_compliance block,
  correct behavior). Contract CC-2026-0002 carries test advances
  ACC-PAY-2026-00006/7 (pre-ZATCA) + 00008 (ZATCA-accepted, use for task 4).
- NOTE: ERPNext rounded_total drives outstanding (0.31 drift) - task 4
  must handle (see SPIKE_FINDINGS V6).

## Done (continued 3)
- [x] Task 4: Progress Claim pipeline — DocTypes (Progress Claim, Progress
  Claim Item, Progress Claim Deduction); cumulative-certified-value model
  (client certificate: this period = cumulative - previous); on_submit generates
  Sales Invoice with items + VAT + GROSS advance recovery allocation (FIFO,
  ksa_compliance 0.61.4 verified semantics, advance_amount=PE unallocated);
  SI on_submit posts retention JE (Dr Retention Receivable / Cr Debtors, with
  party_type/party), payment-side deduction JEs, recovery VAT JE (Dr Output VAT
  / Cr Clearing, proportional per-advance tax ratio); updates contract counters
  (advance_recovered_gross, retention_held, certified_to_date); asserts
  net_amount_due == SI outstanding; on_cancel reverses counters + cancels
  linked JEs + extends ignore_linked_doctypes for Progress Claim. Retention
  cap enforced. ZATCA clearance check on advances before recovery.
- [x] **LIVE TESTED (2026-07-06):** Progress Claim submit → SI generation →
  SI submit → retention JE + recovery VAT JE + counters (manual_tests/
  test_progress_claim.py). Deduction JE path (test_deduction.py). SI cancel
  → counter restore + JE cancel. All green, net_amount_due == outstanding.
- [x] Scheduled tasks implemented + tested: advance_deadline_alerts (ZATCA
  15-day deadline warnings at day 8/13/0, per-company setting, checks SIAF
  acceptance), reconcile_counters (nightly GL-vs-counter drift check,
  contract-scoped, logs errors, never auto-corrects). Both ran clean;
  reconcile shows ZERO drift on CC-2026-0001 + CC-2026-0002.
- [x] Contract client script: "Record Advance" + "New Progress Claim" buttons
  (Active contracts), dashboard indicators (advances/claims/balances).
  Progress Claim: "View Invoice" button. Registered via doctype_js in hooks.py.
- FIXES applied this session: reconcile_counters SQL aggregate bug (Frappe 16
  rejects string SQL in get_value → switched to frappe.db.sql), double-count
  from cancelled claims (now scoped to docstatus=1 claims), retention/certified
  queries now per-contract (were per-company). RUF005 lint fix in sales_invoice.
- NOTE: Contract Value Adjustment deductions (auto credit note) blocked at
  claim submit — use Payment-side Deduction. Back-charge still deferred.

## Done (continued 4)
- [x] Retention Release pipeline — DocTypes (Retention Release, Retention
  Release Entry); on_submit posts Retention Reversal JEs (Dr Debtors / Cr
  Retention Receivable, with party + SI reference) per entry; updates contract
  counters (retention_released, retention_balance); on_cancel reverses +
  cancels JEs. "Get Unreleased Retention" server method + client button
  auto-populates entries from the contract's submitted SIs with unreleased
  retention. SI on_cancel guard blocks cancelling an invoice whose retention
  has been released (or ERPNext's native linked-JE check does). Partial
  releases supported. Validated + GL-verified.
- [x] **LIVE TESTED (2026-07-06):** partial release (232,340.9 of 464,681.8)
  → reversal JE posted, GL matched counters, cancel restored counters +
  cancelled JE, SI cancel guard blocked. (test_retention_release.py)

## Done (continued 5)
- [x] **HUTA 3-CLAIM E2E ON ZATCA SANDBOX — PASSED (2026-07-06).** Three
  Progress Claims on CC-2026-0002 (cumulative 6M/8M/10M), each generating a
  388 Sales Invoice with GROSS advance recovery allocation. ALL THREE
  ACCEPTED by ZATCA sandbox ("Accepted with warnings" — cosmetic warnings
  only, same as spike). PrepaidAmount in XML matched allocation exactly:
  98,115.93 / 230,000.00 / 230,000.00. Clearing account amortized correctly:
  300,000 → 227,202.27 (VAT portions: 12,797.73 + 30,000 + 30,000 = 72,797.73).
  Retention cap enforced (capped at 500,000 = 5% of 10M). Advance balance:
  615,615.93 → 57,500.00 (recovery correctly stopped at remaining balance).
  Evidence: SI ACC-SINV-2026-00008/9/10, SIAFs all "Accepted with warnings".

## Done (continued 3)
- [x] Task 4: Progress Claim pipeline - full-value SI generation, gross
  recovery allocation (Net Total basis grossed up per-advance), retention
  JE (cap enforced), payment-side deduction JEs, recovery-VAT JE, counter
  updates, outstanding==net_due assertion. Golden Huta scenario GL-verified
  AND ZATCA-accepted. Cancel chain via ignore_linked_doctypes EXTENSION in
  on_cancel (ERPNext's own on_cancel overwrites it - do not set it in
  before_cancel). Negative tests green.
- [x] Task 5 (other agent, reviewed & fixed): Retention Release with
  reversal-JE model (Dr Debtors ref-SI / Cr Retention Rcv - retention flows
  back into invoice outstanding; DESIGN CHANGE vs spec's direct-PE model,
  accepted as better). Client scripts (3 doctypes), deadline alerts task,
  counter reconcile task.
  FIXED by review: (1) double-release enabler - get_unreleased_retention's
  GL query matched nothing (reference on Debtors row, account filter on
  retention row); released-per-invoice now sourced from submitted Retention
  Release Entry rows; (2) per-invoice release limits enforced server-side
  from DB figures, not client rows; (3) permission check on whitelisted
  method; (4) amend-guard on Progress Claim (clear stale SI link).
- [x] Counter corruption from agent testing repaired from GL truth
  (manual_tests/repair_counters.py); reconcile task validated live - it
  caught the drift. Site state note: several submitted claims point at
  cancelled SIs (agent toggled ZATCA off to cancel cleared invoices - never
  do on client sites); spike SI ACC-SINV-2026-00001 still consumes 534,384.07
  of PE-00008 unallocated outside contract tracking (dev artifact).
- Site serving fixed: gunicorn workers predated app install (stale process
  image -> 500/ModuleNotFoundError). After installing a new app, RESTART
  backend/frontend/websocket containers. Scheduler container still crash-
  loops on 'No module named botflow' (pre-existing, unrelated).
- Admin password set: ContractingDev2026 (localhost:8080).

## Done (continued 4)
- [x] Credit note / return handling (live-tested, 383 ZATCA-ACCEPTED):
  proportional retention reversal on returns (capped at unreleased balance,
  opt-out via contracting_skip_retention_reversal field), certified/retention
  counter reduction + cancel-restore, advances-copied-onto-return guard MOVED
  to before_validate (core validation fires before hooked validate -
  make_sales_return really does copy advances, spike item S3 confirmed),
  released_for_invoice now counts return reversals so Release/Ledger cannot
  double-dip. Advance recovery deliberately NOT restored by credit notes.
- [x] docs/ADVANCE_REFUND_SOP.md - manual 386-refund procedure (termination),
  incl. the clearing-account adjustment JE and the one untested sandbox
  question (383 referencing a PE-based 386).

## Done (continued 5) - all 4 reports, both print formats, workspace: LIVE-VERIFIED
- [x] All 4 reports built/fixed and confirmed returning real data live:
  Retention Ledger (redesigned per-contract per your explicit spec restate,
  next-claimable-date now correctly derived from the EARLIEST unreleased
  invoice's own DLP clock, not the contract's last invoice - the agent's
  version used last-invoice which understates urgency), Advance Recovery
  Statement (per-advance + indented per-claim recovery detail restored -
  the agent's rewrite had dropped the ZATCA audit-trail rows), Contract
  Progress Statement, Contracting Invoice Summary.
- [x] BUG PATTERN CAUGHT: 3 of 4 reports (contract_progress_statement,
  retention_ledger, advance_recovery_statement) independently written/
  rewritten with the identical `cc.docstatus = 1` condition -
  Contracting Contract is NOT submittable (status-driven), so this
  silently returned ZERO rows always, on every one. Root cause was the
  same copy-paste pattern across all three. Fixed by filtering on
  `cc.status != 'Draft'` instead.
- [x] Print formats built + LIVE-RENDERED (frappe.get_print, not just
  saved): Progress Claim Certificate (bilingual EN/AR, added Gross/Net-
  for-Period rows, retention, deductions, amount-in-words via
  frappe.utils.money_in_words) and Contracting Contract Summary (new -
  did not exist before). BUG FOUND AND FIXED (mine originally, mirrored
  from the agent's pattern): `fmt_money(value, {"currency":"SAR"})` -
  fmt_money's real signature is (amount, precision:int, currency:str) -
  passing a dict as the 2nd positional arg crashed with "'dict' object
  cannot be interpreted as an integer" on first real render. Fixed to
  `fmt_money(value, currency="SAR")` - 21 occurrences across both files.
- [x] Workspace "Contracting Invoicing" confirmed present (masters/
  transactions/reports/settings cards, all 4 reports linked) - correct
  location is single-nested `contracting_invoicing/workspace/...`, not
  double-nested; my own earlier assumption of double-nesting for
  Workspace (unlike doctype/report which ARE double-nested) was wrong -
  corrected via this session's sync.
- [x] INFRA BUG (mine) found and fixed: `sync_from_container.sh` used
  `rsync --delete` container->repo. Running it BEFORE pushing new local
  work to the container silently deleted that local work twice this
  session (once wiped the print_format dir entirely, once reverted a
  local bugfix back to the container's stale buggy version). Script
  now never deletes; use `git status` + manual `git rm` for real removals.
- [x] Cleanup: other agent had also generated a duplicate, WRONGLY-NESTED
  copy of report/, print_format/, and tests/ one level too shallow
  (Frappe never scans these paths - dead but cluttered the repo and
  confused every diff/sync this session). Removed after confirming byte-
  identical/no-unique-content vs the canonical nested copies. One real
  file recovered from the mess: `tests/reports_smoke.py` - a manual
  bench-execute smoke script (not a real FrappeTestCase suite; formal
  automated tests remain NOT done).

## In progress
- [ ] nothing - between tasks

## Next
1. Formal tests/ suite: convert all live-verified scenarios (golden claim,
   negatives, release, credit note, all 4 reports, both print formats)
   into real FrappeTestCase classes for `bench run-tests`; CI (v15 + v16)
2. Help system: guide page, module onboarding, form tours (field
   descriptions already exist)
3. ar.csv translations, demo-data command, README
4. Phase 2: Contract Value Adjustment deductions (auto credit note),
   back-charges, release-time deductions
5. Recommend: agree with the other agent on a lane split (e.g. it does
   NOT touch report/print_format/workspace files without pulling latest
   first) - three separate silent overwrites of already-fixed code
   happened this session alone.

## Next (task order)
1. Reports (4): Contract Status Summary, Retention Ledger (DLP-based aging),
   Advance Recovery Schedule, Progress Billing Register
2. Print format (bilingual Huta layout, ksa_compliance QR blocks)
3. Workspace + guide page + onboarding + Form Tours (help system)
4. Formal tests/ suite for bench run-tests + CI (v15 + v16 legs)
5. ar.csv, demo-data command, README
6. Phase 2: Contract Value Adjustment deductions (auto credit note),
   back-charges, release-time deductions (child table exists in spec,
   agent's RR has no deductions table - add then)

## Next
- **Reports (NONE exist yet — gap found 2026-07-06):**
  - Retention Ledger (referenced in contracting_contract.json defect_liability_months
    description but never built): per-contract held/released/balance + expected
    release dates.
  - Advance Recovery Statement: per contract/advance — gross, recovered, balance,
    which claims recovered what.
  - Contract Progress Statement: certified-to-date vs contract value, claim history.
  - Contracting Invoice Summary: SIs with retention/recovery/deductions/net-due.
  - Workspace (desk landing page grouping contracting doctypes) — none exists.
  - Print formats: Progress Claim (payment certificate), Contract.
- Contract Value Adjustment auto credit note.
- Return SI against a contracting invoice: advances-copy behavior + XML.
- 383 referencing a PE-based 386 (advance refund SOP).
- Demo-data task + v15 CI compatibility.
