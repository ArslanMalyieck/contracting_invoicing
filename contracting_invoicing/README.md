# Contracting Invoicing (ERPNext KSA) - Complete Field Guide & Audit

**App:** `contracting_invoicing` (Arslan)  
**Depends on:** erpnext, ksa_compliance  
**Company:** SAR companies only  

Progress billing (IPC), advance recovery, retention & deductions for Saudi contracting companies, with ZATCA prepayment invoices and auto VAT handling.

---
## 1) Quick Start (workflow)

1. **Contracting Settings** (per company) - sirf aik dafa: select retention/recovery basis, accounts (Retention Receivable, Output VAT, VAT-on-Advances clearing, deduction expense). Jaisay hi koi Progress Claim submit ho jaye, kuch settings lock ho jati hain.
2. **Contracting Contract** - new: Customer, Project, Contract Value, Advance %, Recovery % per claim, Retention %, cap, model. Status = **Active**.
3. **Advance** - do tareeqe:
   - **Create Advance Payment** (auto): Mode of Payment + VAT template + (blank = auto amount) select karo -> button dabao -> Payment Entry khud ban+submit hoti hai (VAT Deduct row clearing account par), contract ke Advances table + counters + Advance VAT JE sab auto.
   - **Record Advance** (manual): mapped Payment Entry form khulta hai, aap values check kar ke submit karte ho (Prepayment Invoice tick hona zaroori).
4. **Progress Claim (IPC)** - new: Contract select, Period From/To, Invoice Date, **Cumulative Certified Value (Net)** (aaj tak ka total - ahem manual input). Baqi auto: Previously Certified, This Period, Retention, Advance Recovery, Net Amount Due. Items optional (total = This Period). Submit -> **Sales Invoice khud ban kar submit** hoti hai (agar Settings me Auto Submit ON ho) + Retention JE, Deduction JEs, Recovery-VAT JE sab post ho jate hain.
5. **Payment receive** - normal Payment Entry (Receive) se invoice ke against.
6. **Retention Release** - DLP ke baad: contract select -> **Get Unreleased Retention** -> entries auto -> submit (Dr Debtors / Cr Retention Receivable).

---
## 2) Accounting Model (kya post hota hai)

| Event | Posting |
|---|---|
| Advance received (PE) | Dr Bank (gross) / Cr Customer (net) / Cr VAT-on-Advances clearing (Deduct row), phir auto **Advance VAT JE**: Dr Bank / Cr Output VAT |
| Progress Claim -> Sales Invoice submit | Normal SI: Dr Customer / Cr Revenue / Cr Output VAT. Phir **Retention JE**: Dr Retention Receivable / Cr Customer. **Recovery VAT JE**: Dr Output VAT / Cr Clearing (advance ki VAT ratio ke hisaab se). **Deduction JEs** payment-side deductions ke liye. Advance allocation SI par Customer Dr / Clearing Dr ... (ERPNext PE allocation). |
| Credit note (return) against contracting invoice | Certified value reduce; retention proportional reverse (agar skip na ho); advance recovery wapas nahi hoti - agle claim me kam recover karo |
| Retention Release submit | Dr Debtors / Cr Retention Receivable (party-wise) |
| Cancel (SI/PE/Claim/Release) | Tamam linked JEs auto cancel + counters reverse |

---
## 3) Selection / Dropdown Guide (kya choose karna hai)

| Dropdown | Options | Kab kya choose karo |
|---|---|---|
| Contract `status` | Active / others (Select) | Claims/advances sirf **Active** par |
| `retention_invoicing_model` | Invoiced (withheld from payment) / ... | Default: Invoiced (see Settings retention_posting) |
| Settings `retention_basis` | Net Total / Grand Total | Net Total = VAT ke baghair par 5/10%; Grand = VAT ke sath |
| Settings `advance_recovery_basis` | Grand Total / Net Total | Recommended Grand Total (claim #1 example isi par tha) |
| Settings `advance_recovery_order` | FIFO / ... | FIFO = purana advance pehle recover |
| Settings `retention_posting` | On Invoice Submit | On Payment abhi supported nahi (error deta hai) |
| Deduction Type `treatment` | Payment-side Deduction / Back-charge / Contract Value Adjustment | Payment-side = usi invoice me katti; baqi next release (abhi error) |
| PE `mode_of_payment` | Company ke enabled modes | Account Mode of Payment Account (company-wise) se aata hai |
| `taxes_template` / `advance_taxes_template` | Company ke templates (e.g. VAT 15%) | KSA me default VAT template |

---
## Contracting Settings
Per-company configuration (accounts, basis, posting switches).

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Company | Link | Company | Yes |  |  |

**– Calculation Basis –**

| Retention Basis | Select | Net Total / Grand Total | Yes | Net Total | Retention is calculated as a % of this figure on each invoice. Net Total = before VAT. Grand Total = including VAT. Locked once claims exist. |
| Advance Recovery Basis | Select | Net Total / Grand Total | Yes | Net Total | Advance recovery per claim is a % of this figure. Locked once claims exist. |
| Advance Recovery Order | Select | FIFO / Pro-rata | Yes | FIFO | With multiple advances on one contract: FIFO recovers the oldest advance first; Pro-rata spreads recovery across all open advances. |

**– Accounts –**

| Retention Receivable Account | Link | Account | Yes |  | Retention is moved from Debtors into this account when each invoice is submitted, so AR aging shows only what the client will actually pay now. Must be a Receivable-type account. |
| Default Deduction Expense Account | Link | Account | Yes |  | Fallback expense account for payment-side deductions when the Deduction Type has no account of its own. |
| Output VAT Account | Link | Account | Yes |  | The real VAT output (payable) account. Credited by the auto Journal Entry when an advance is received, so VAT on advances is declared correctly per KSA rules (VAT is due when the advance is received). |
| VAT on Advances (Clearing) Account | Link | Account | Yes |  | Absorbs the prepayment Payment Entry's tax deduction and amortizes to zero as the advance is recovered on progress invoices. Keeps the ZATCA XML flow intact while the real Output VAT account stays correct. |
| Damages Adjustment Item | Link | Item |  |  | Service item used on auto-generated credit notes for deductions of type Contract Value Adjustment (e.g. liquidated damages adjusted from the contract). |

**– Behavior –**

| Auto Submit Generated Invoice | Check |  |  | 0 | Off (recommended): claims create a Draft invoice for your accountant to review; ZATCA submission happens when they submit it. On: invoice submits and goes to ZATCA immediately. |
| Retention Posting | Select | On Invoice Submit / On Payment | Yes | On Invoice Submit | When the retention Journal Entry posts. On Invoice Submit (recommended) moves retention out of Debtors immediately. On Payment is planned for a later release. |
| Advance Invoice Deadline Alerts | Check |  |  | 1 | ZATCA requires the advance (prepayment) invoice within 15 days after the end of the month the advance was received. Sends warnings to Contracting Managers at day 8 and day 13 after month end. |

---
## Contracting Contract
The anchor document: one per customer/project contract. Holds managed counters (advances, retention, certified) plus the new auto-advance fields.

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Contract Title | Data |  | Yes |  |  |
| Customer | Link | Customer | Yes |  |  |
| Company | Link | Company | Yes |  |  |
| Project | Link | Project |  |  |  |
| Status | Select | Draft / Active / Defect Liability / Closed | Yes | Draft | Only Active contracts accept advances and Progress Claims. Move to Defect Liability after final handover; retention releases remain possible until Closed. |
| Contract Value | Currency |  | Yes |  | Total contract value excluding VAT. Used for the retention cap and advance percentage checks. |

**– Advance Payment –**

| Advance % | Percent |  |  |  | Mobilization advance as % of contract value. A warning is raised if recorded advances exceed this. |
| Recovery % per Claim | Percent |  |  |  | Portion of each claim used to pay back the advance. Example: 10% means every certificate repays 10% of its value until the advance is fully recovered. The app stops automatically at the remaining balance. |
| Advance Received (Net) (read-only) | Currency |  |  |  |  |
| Advance Recovered (Gross) (read-only) | Currency |  |  |  |  |
| Advance Balance (Gross) (read-only) | Currency |  |  |  |  |

**– Advance Payment (auto Payment Entry) –**

| Advance Mode of Payment | Link | Mode of Payment |  |  |  |
| Advance Taxes Template (VAT) | Link | Sales Taxes and Charges Template |  |  |  |
| Advance Amount (Gross) - blank = auto | Currency |  |  |  |  |
| Advance Posting Date | Date |  |  | Today |  |
| Advance Reference No | Data |  |  |  |  |
| Advance Reference Date | Date |  |  |  |  |
| Advances (read-only) | Table |  |  |  | System-managed. Rows appear when advance Payment Entries linked to this contract are submitted. |

**– Retention –**

| Retention % | Percent |  |  |  | Withheld by the client from each certificate. VAT is still charged on the full certified value per the ZATCA contracting guideline; retention only affects what is collected now. |
| Retention Cap % of Contract Value | Percent |  |  |  | Maximum total retention as % of contract value (many Saudi contracts cap at 5%). The app stops withholding once the cap is reached. 0 = no cap. |
| Defect Liability Period (Months) | Int |  |  |  | Used to compute the expected retention release date shown in the Retention Ledger report. |
| Retention Model (read-only) | Select | Invoiced (withheld from payment) |  | Invoiced (withheld from payment) | Retention is part of the invoiced amount (VAT charged in full) and withheld from payment. The alternative model - invoicing retention separately at release - is planned for a later version. |
| Retention Held (read-only) | Currency |  |  |  |  |
| Retention Released (read-only) | Currency |  |  |  |  |
| Retention Balance (read-only) | Currency |  |  |  |  |

**– Progress –**

| Certified To Date (Net) (read-only) | Currency |  |  |  |  |

---
## Contract Advance (child)
One row per advance Payment Entry registered on the contract.

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Payment Entry (read-only) | Link | Payment Entry | Yes |  |  |
| Date (read-only) | Date |  |  |  |  |
| Advance (Net) (read-only) | Currency |  |  |  | Advance amount excluding VAT, as received on the Payment Entry. |
| VAT (read-only) | Currency |  |  |  |  |
| Advance (Gross) (read-only) | Currency |  |  |  |  |
| Recovered (Gross) (read-only) | Currency |  |  |  | Total recovered against this advance across all progress invoices, VAT-inclusive. |
| Balance (Gross) (read-only) | Currency |  |  |  |  |

---
## Progress Claim
IPCs - fill period + cumulative certified value; the Sales Invoice is generated automatically on submit.

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Title (read-only) | Data |  |  |  |  |
| Contract | Link | Contracting Contract | Yes |  |  |
| Customer (read-only) | Link | Customer |  |  |  |
| Company (read-only) | Link | Company |  |  |  |
| Claim No (read-only) | Int |  |  |  | Sequential certificate number within the contract, assigned on submit. |
| Period From | Date |  | Yes |  |  |
| Period To | Date |  | Yes |  |  |
| Invoice Date | Date |  | Yes |  | Posting date of the generated Sales Invoice. |

**– Certified Value –**

| Cumulative Certified Value (Net) | Currency |  | Yes |  | Total certified since contract start, from the client's payment certificate. The app computes this period's value by subtracting the previous claim. |
| Previously Certified (Net) (read-only) | Currency |  |  |  |  |
| This Period (Net) (read-only) | Currency |  |  |  |  |
| Taxes Template | Link | Sales Taxes and Charges Template | Yes |  |  |
| Items (optional BOQ breakdown) | Table |  |  |  | Leave empty to invoice a single 'Value of Works Executed' line. If filled, the total must equal This Period (Net). |

**– Recovery, Retention and Deductions –**

| Advance Recovery (Gross) (read-only) | Currency |  |  |  | Computed: Recovery % x basis, capped at the remaining advance balance. Applied as ZATCA prepayment adjustment lines - never subtracted from the invoice's taxable value. |
| Retention (read-only) | Currency |  |  |  | Computed: Retention % x basis, capped at the contract's retention cap. VAT is charged on the full certified value; retention only reduces what is collected now. |
| Deductions | Table |  |  |  |  |
| Net Amount Due (read-only) | Currency |  |  |  | What the client is expected to pay for this claim: invoice total minus advance recovery, retention and deductions. Matches the invoice's outstanding amount after submission. |

**– Generated Documents –**

| Sales Invoice (read-only) | Link | Sales Invoice |  |  |  |
| Amended From (read-only) | Link | Progress Claim |  |  |  |

---
## Progress Claim Item (child)
Optional BOQ breakdown rows; their total MUST equal 'This Period (Net)'.

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Item | Link | Item | Yes |  |  |
| Description | Small Text |  |  |  |  |
| Qty | Float |  |  | 1 |  |
| Rate | Currency |  |  |  |  |
| Amount (read-only) | Currency |  |  |  |  |

---
## Progress Claim Deduction (child)
Extra katti rows (payment-side deductions etc).

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Deduction Type | Link | Deduction Type | Yes |  |  |
| Treatment (read-only) | Data |  |  |  |  |
| Amount | Currency |  | Yes |  | Positive amount to deduct. How it posts depends on the Deduction Type's treatment. |
| Remarks | Small Text |  |  |  |  |

---
## Deduction Type
Master of deduction kinds with their treatment.

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Treatment | Select | Contract Value Adjustment / Payment-side Deduction / Back-charge | Yes |  | Contract Value Adjustment issues a ZATCA credit note (reduces VAT). Payment-side Deduction only reduces the receivable (no VAT effect). Choose per the ZATCA contracting guideline - this cannot be changed per-claim. |
| Default Account | Link | Account |  |  | Expense account debited when this deduction is applied. Leave empty to use the company default from Contracting Settings. |
| Reverses Retention Proportionally | Check |  |  | 0 | If checked, the auto credit note also reverses retention on the credited amount. Usually OFF for damages (damages do not reduce works executed, so retention already withheld stays withheld). |

**– Printed Descriptions –**

| Description (English) | Small Text |  |  |  | Shown on the invoice print format next to this deduction. |
| Description (Arabic) | Small Text |  |  |  |  |

---
## Retention Release
Release withheld retention after the DLP; posts Dr Debtors / Cr Retention Receivable.

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Title (read-only) | Data |  |  |  |  |
| Contract | Link | Contracting Contract | Yes |  | The contract whose retention is being released. |
| Customer (read-only) | Link | Customer |  |  |  |
| Company (read-only) | Link | Company |  |  |  |
| Posting Date | Date |  | Yes | Today | Posting date of the reversal Journal Entries. |

**– Invoices Being Released –**

| Entries | Table |  | Yes |  | One row per Sales Invoice whose retention is being released. Use 'Get Unreleased Retention' to populate. |

**– Totals –**

| Total Release (read-only) | Currency |  |  |  |  |
| Retention Balance (Before) (read-only) | Currency |  |  |  |  |
| Retention Balance (After) (read-only) | Currency |  |  |  | Retention still held after this release. Computed on submit. |
| Remarks | Small Text |  |  |  |  |

---
## Retention Release Entry (child)
One row per invoice whose retention is being released.

| Field | Type | Options/Link | Reqd | Default | Description |
|---|---|---|---|---|---|
| Sales Invoice (read-only) | Link | Sales Invoice | Yes |  |  |
| Retention JE (read-only) | Link | Journal Entry |  |  | The original Retention JE on that invoice. Reversed by this release. |
| Retained (read-only) | Currency |  |  |  | Retention originally withheld on this invoice. |
| Release Amount | Currency |  | Yes |  | Portion of this invoice's retention being released now. Cannot exceed Retained minus already-released. |
| Balance (read-only) | Currency |  |  |  | Remaining retention on this invoice after this release. |

---
## 4) Auto Advance Payment (naya feature)

**Button:** *Create Advance Payment* (Contracting Contract, jab Status=Active aur Advance% > 0)

**Naye fields:**
| Field | Kaam |
|---|---|
| Advance Mode of Payment | Bank/Cash mode - default account auto (Mode of Payment Account se) |
| Advance Taxes Template (VAT) | VAT 15% template |
| Advance Amount (Gross) | blank = auto (Advance % limit - received) |
| Advance Amount Basis | **Net (VAT added on top)** = Advance % x Contract Value net entitlement hai, VAT upar se add hota hai. **Gross (VAT inclusive)** = wohi figure gross ceiling hai, net = gross / 1.15. Dono soorton me PE same: paid_amount = gross, tax row **Actual + Deduct**. |
| Advance Posting Date | default today |
| Advance Reference No | auto `ADV-<contract>` |
| Advance Reference Date | auto posting date |

**Kya hota hai:** Payment Entry (Receive) create+submit; VAT **Deduct** row clearing account par; ZATCA Prepayment flags ON; contract Advances table + counters update; Advance VAT JE post. Cancel PE = sab reverse.

**Add vs Deduct (ZATCA):** prepayment invoice (no Sales Order) ke liye tax row hamesha **Actual + Deduct** honi chahiye. `Add` karne se XML ka taxable amount = paid + VAT ban jata hai, phir `tax ÷ taxable ≠ rate` (BR-CO-17 / BR-KSA-84) aur sandbox reject kar deta hai. Is liye "VAT upar se" aur "VAT inclusive" dono scenarios ko **Advance Amount Basis** field se handle karo - tax row kabhi `Add` mat karo.

---
## 5) Audit Findings (22-Sep-2026)

### Fixed
1. **Duplicate/copy data leak (HIGH):** Same customer ka dosra contract banate waqt (Desk Duplicate ya kisi bhi copy se) **advances table + counters (advance_received_net, advance_balance_gross, retention_held, certified_to_date...) copy ho kar aate the** - chahe fields par no_copy=1 ho, kyunke ERPNext ka `frappe.copy_doc` no_copy ignore karta hai. **Fix:** Contract & Progress Claim ke `validate` me `_reset_managed_on_new()` - naya document hamesha 0/khali managed fields se start hota hai (test verified: duplicate ab 0 aur advances 0 rows).
2. **Manual advance VAT bug (MED-HIGH):** `api.make_advance_payment_entry` (Record Advance button) tax row `charge_type` galat tha. **Real fix (25-Sep-2026):** `Actual` + `Deduct` rakha, `included_in_paid_amount=0`, clearing account force ki, aur gross/`tax_amount` prefill + Net/Gross basis honor ki. **Note:** pehle jo `On Paid Amount` kiya gaya tha woh ghalat tha - ksa_compliance ka XML factory (no Sales Order) `Actual` ke ilawa charge type par "You cannot set Charge Type to anything other than Actual for Prepayment Invoice..." throw karta hai. Manual form par `Actual` row ka `tax_amount` client script (public/js/zatca_now.js) paid_amount/rate change par auto `paid - paid/(1+rate)` set karta hai.
3. **Stray duplicate JS file** `doctype/contracting_contract/contracting_contract.js` **hata diya (25-Sep-2026)** - pehle sirf merge claim tha magar file maujood thi, jis se "Create Advance Payment" button aur onload/refresh/setup do dafa register ho rahe the. Ab sirf hooks-mapped `public/js/contracting_contract.js`.
4. **Amend link fix:** `progress_claim._reset_managed_on_new` `amended_from` ko har new doc par clear kar deta tha, jis se genuine Amend ka link toot jata tha. Ab sirf tab clear hota hai jab source cancelled (docstatus 2) na ho (Duplicate leak ke liye).

### Recommended (pending)
- **Nested module duplication:** app me `contracting_invoicing/contracting_invoicing/` (hooks/overrides) aur uske andar `contracting_invoicing/doctype` (doctypes) - kaam karta hai magar confusing hai. Clean flattening recommend (future release).
- Retention Cap % = 0 ka matlab "no cap" hai - UI par helper text add karna behtar.
- Contract dashboard me **Certified** indicator bhi add kar sakte hain.
- Duplicate karne par bhi items/deductions copy hote hain (by design) - us par message dena behtar: "BOQ rows copy hui hain, amounts verify karo".

---
## 6) Errors - jo message aata hai aur matlab

| Message | Matlab / Hal |
|---|---|
| Contract is Draft/Cancelled, not Active | Contract Active karo |
| Cumulative certified value must exceed previously certified | Naya total purane se zyada do |
| Items total must equal This Period (Net) | BOQ rows ka total exact This Period karo (ya items khali chhoro) |
| Deduction amounts must be positive | Deduction positive rakho |
| Advance X has not been accepted by ZATCA | PE ko pehle ZATCA submit karo (kaam ke vaqt zatca_now button) |
| Gross exceeds remaining advance limit | Advance Amount (Gross) kam karo |
| Net Amount Due X does not equal invoice outstanding Y | Safety check - post kuch nahi hua; report karo |
| Retention release exceeds balance | Releasable se zyada mat karo |

---
## 7) Version
Audit build: 2026-09-07 (auto-advance + duplicate fix).
