# Contracting Invoicing

Progress billing, advance recovery, retention and deductions for KSA contracting companies, built on top of ERPNext + [ksa_compliance](https://github.com/lavaloon-eg/ksa_compliance) for ZATCA e-invoicing.

**Status:** functional, hand-tested end-to-end against a ZATCA sandbox (advance invoice, progress invoice with partial recovery, credit note, retention release). No formal automated test suite yet — see "Known gaps" below. Not yet used on a production client site.

## What this app does

Saudi contracting companies bill via progress claims (payment certificates) that combine four things standard ERPNext doesn't model:

1. **Certified value of works** for the period (the actual VATable supply)
2. **Advance payment recovery** — clawback of a mobilization advance, handled as a proper ZATCA prepayment adjustment (invoice type 386), never by subtracting from the taxable value
3. **Retention** — a % withheld by the client each certificate, released later; VAT is charged on the full certified value per ZATCA's contracting-sector guidance, so retention only affects what's collected now, never the tax
4. **Deductions** — classified by type, since the correct treatment (credit note vs. payment-side vs. back-charge) differs and must not be guessed

Every number the client sees is backed by a real Journal Entry — nothing is print-format arithmetic with no accounting behind it.

## Requirements

- ERPNext (developed against v16; must also be verified on v15 before client rollout — not yet done)
- `ksa_compliance` (Lavaloon) installed and a ZATCA Business Settings configured for the company
- Company currency must be SAR

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/ArslanMalyieck/contracting-invoicing --branch main
bench --site your-site install-app contracting_invoicing
bench --site your-site migrate
```

Installing creates two roles (`Contracting Manager`, `Contracting User`), a per-company `Retention Receivable` account and a `VAT on Advances` clearing account, and adds a few read-only fields to Sales Invoice / Payment Entry / Journal Entry (all prefixed `contracting_`, all safe to ignore if you're not using this app on a given company).

## One-time setup per company

Go to **Contracting Invoicing > Contracting Settings**, create a row for the company, and fill in:

- **Retention Receivable Account** and **Deduction Expense Account** (created automatically on install, just pick them)
- **Output VAT Account** and **VAT on Advances (Clearing) Account** — this second one is created automatically too; see "Why a clearing account?" below if you're curious
- Leave **Retention Basis** / **Advance Recovery Basis** as "Net Total" unless your contracts specifically use grand-total (VAT-inclusive) percentages
- Leave **Auto Submit Generated Invoice** off — this means the app creates a *draft* invoice for your accountant to review before it goes to ZATCA. Turn it on only once you fully trust the flow.

---

## User manual — testing walkthrough (for Arsalan)

This is the exact sequence to test the whole app end to end. Use a test company with SAR currency and ksa_compliance's ZATCA sandbox mode.

### 1. Create a contract

**Contracting Invoicing > Contracting Contract > New**

- Customer, Company, Contract Value
- Set **Status = Active** (contracts start as Draft and won't accept advances or claims until Active)
- Advance %, Recovery % per Claim, Retention %, Retention Cap %, Defect Liability Period (months)
- Save

### 2. Record the mobilization advance

From the Contract, use **Record Advance** (or create a Payment Entry manually):

- Payment Entry, type **Receive**, against the contract's customer
- Tick **Prepayment Invoice** (this is ksa_compliance's flag, not ours)
- Attach a **Sales Taxes and Charges Template** (required — the ZATCA XML takes its VAT rate from here)
- The tax row's account must be the **VAT on Advances** clearing account from Settings, type **Deduct**, "Considered in Paid Amount" unchecked
- Enter the amount **gross** (VAT-inclusive) — e.g. 1,150,000 for a 1,000,000 net advance at 15%
- Link **Contracting Contract** to this contract
- Submit

**What to check:** the Contract's "Advances" table now shows this Payment Entry with the correct gross/net/tax split, and `Advance Balance (Gross)` updated. A Journal Entry titled "Advance VAT" was posted (check it — plain-language remark explains what it did).

### 3. Submit a Progress Claim

**Contracting Invoicing > Progress Claim > New**

- Contract, Period From/To, Posting Date
- **Cumulative Certified Value (Net)** — the running total certified since contract start (not just this period — the app works out the period value by subtracting the previous claim automatically)
- Taxes Template
- Leave Items empty for a single "Value of Works Executed" line, or fill the Items table for a BOQ breakdown (if filled, it must total the period value)
- Add a **Deduction** row if testing a payment-side deduction (needs a Deduction Type record first — see Deduction Type list)
- Submit

**What to check:**
- A Sales Invoice was generated at **full certified value** (not reduced by recovery) and linked back to the claim
- Claim shows computed Advance Recovery, Retention, and Net Amount Due
- Once the Sales Invoice is submitted (auto or manual, per your Settings), check: Retention Journal Entry posted, invoice's **Outstanding Amount** equals the claim's **Net Amount Due** exactly (the app throws an error if these ever disagree — that's a safety check, not a bug, if you see it)
- Submit the invoice to ZATCA (ksa_compliance's normal flow) and confirm acceptance

### 4. Print the certificate

Open the generated Sales Invoice → linked Progress Claim → **Print** → select **Progress Claim Certificate**. Bilingual EN/AR, shows the full breakdown (gross for period → advance recovery → net for period → retention → deductions → net amount due) plus amount in words. This is the internal signable document, not the ZATCA tax invoice itself.

Print the **Contracting Contract** → select **Contracting Contract Summary** for a one-page contract status handout.

### 5. Test a credit note

If the client's engineer reduces a certified value after the invoice cleared: create a **Credit Note** (Return) against that Sales Invoice via the normal ERPNext flow.

**What to check:** retention is automatically reversed proportionally (capped at what's still unreleased on that invoice) unless you tick "Skip Retention Reversal". Contract counters (certified-to-date, retention held) adjust down. **Advance recovery does NOT get restored** — this is intentional; recover less on the next claim instead. Submit to ZATCA and confirm the 383 is accepted.

### 6. Release retention

**Contracting Invoicing > Retention Release > New** → pick the Contract → **Get Unreleased Retention** button populates open retention by invoice → adjust amounts for a partial release if testing that → Submit.

**What to check:** a Payment Entry is created moving the released amount back through the invoice; the Retention Ledger report reflects it.

### 7. Check the reports

All four are in the workspace and also under Report list:

- **Retention Ledger** — per contract: held / released / balance / next claimable date (based on the earliest invoice with unreleased retention, not the latest)
- **Advance Recovery Statement** — per advance, with an indented row per claim that recovered against it
- **Contract Progress Statement** — certified-to-date vs. contract value, % complete, one row per contract
- **Contracting Invoice Summary** — every contracting Sales Invoice with retention/recovery/deduction/net-due columns

### Things that should correctly refuse to let you do them

Test these too — they're meant to fail:

- Submitting a claim that would recover more advance than remains, or withhold more retention than the cap allows
- Editing Contracting Settings' basis/account fields once claims exist for that company
- Cancelling a system-generated Journal Entry (Retention, Deduction, Recovery VAT) directly — you'll be told to cancel the Sales Invoice instead
- Cancelling a Sales Invoice that's already been accepted by ZATCA (this is ksa_compliance's own rule, correctly still in force)

---

## Why a clearing account for advance VAT?

ksa_compliance's prepayment flow forces the advance's tax row into a Deduct configuration that, taken alone, posts VAT the wrong way round (debits VAT instead of crediting it). Rather than patch their code, this app points that tax row at a dedicated **VAT on Advances** account and posts its own correcting entry so the real Output VAT account is right from day one. The clearing account then amortizes to zero as the advance is recovered across claims. Full detail in `SPIKE_FINDINGS.md` if you want the ZATCA sandbox evidence behind this.

## Known gaps (be aware before relying on this for a real client)

- **No formal automated test suite yet.** Everything above has been manually verified against live sandbox data, not covered by `bench run-tests`/CI. Treat every change as needing the walkthrough above re-run until that exists.
- **Not yet verified on ERPNext v15** (client sites run v15; development has been on v16).
- Deduction types **Contract Value Adjustment** (auto credit note) and **Back-charge** are deliberately blocked for now — only **Payment-side Deduction** is implemented.
- Retention release-time deductions (e.g. final penalties deducted from a release) are not yet supported.
- The scheduler jobs (advance-deadline alerts, nightly counter reconciliation) exist in code but depend on your bench's scheduler actually running — verify that separately.
- Advance refunds on contract termination are a **documented manual procedure**, not automated — see `docs/ADVANCE_REFUND_SOP.md`.
- No Arabic translation file (`ar.csv`) yet — print formats are bilingual, but Desk field labels/messages are English only.

## Repo layout

```
contracting_invoicing/
├── contracting_invoicing/          # doctypes, reports, print formats, workspace
├── overrides/                      # Sales Invoice / Payment Entry / Journal Entry hooks
├── setup/                          # custom fields, accounts, roles (all idempotent)
├── tasks/                          # scheduled jobs
└── public/js/                      # client scripts
```

Companion docs at the repo root of the project folder (not shipped in the app itself): `SPIKE_FINDINGS.md` (ZATCA sandbox evidence), `BUILD_STATUS.md` (development log), `docs/ADVANCE_REFUND_SOP.md`.

## License

AGPL-3.0
