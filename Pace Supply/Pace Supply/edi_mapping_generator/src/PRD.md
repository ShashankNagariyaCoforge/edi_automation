# Vendor EDI Onboarding Automation – Design & Workflow

## Objective
Build an automation (packaged as a `.exe`) that **onboards a new EDI vendor** by analyzing:
- a vendor X12 sample EDI file (e.g., 850)
- a vendor implementation guide PDF
- a canonical ERP semantic JSON (prebuilt)

and produces a **fully populated ERP_Definition Excel file**, with **columns B–E and J filled**, **without altering the Excel format or layout**.

This automation runs **once per vendor onboarding**, not per transaction.

---

## Inputs

### 1. Vendor Sample EDI File (X12)
Purpose:
- Confirms which segments/elements the vendor actually uses
- Helps validate PDF-derived rules

Used for:
- Cross-checking mandatory/optional segments
- Detecting real-world usage patterns

---

### 2. Vendor Implementation Guide (PDF)
Purpose:
- Defines vendor-specific constraints

Extracted information:
- Mandatory vs optional segments
- Allowed code values (e.g., BEG01 = 00)
- Loop limits
- Vendor-specific rules

This PDF is **configuration input**, not runtime data.

---

### 3. Canonical ERP Semantic JSON (Prebuilt)
Purpose:
- Source of truth for **field meaning**, not vendor rules

Contains:
- Record definitions (0010–1400)
- Field semantic roles
- X12 segment/element mappings
- Value sources (x12 / erp_lookup / constant / derived)

This file is **vendor-agnostic** and **never modified**.

---

## Output

### ERP_Definition Excel File (Same file, updated)
The automation must:
- Populate **only** columns:
  - **B** → Record Number
  - **C** → Format
  - **D** → Start Column
  - **E** → Width
  - **J** → Field Description
- Leave all formatting, ordering, and structure unchanged
- Not add/remove rows or columns

The output must be **drop-in compatible** with existing ERP processes.

---

## High-Level Workflow

You are an EDI onboarding assistant.
Use the canonical ERP semantic JSON as the source of truth for field meaning.
Use vendor PDFs only to derive vendor-specific validation rules.
Do not change Excel formatting or structure.
Populate only columns B–E and J.
Do not infer values not explicitly supported by X12 or canonical definitions.


### Task Instruction (example)


Given:

Vendor X12 sample file

Vendor implementation guide PDF

Canonical ERP semantic JSON

Blank ERP_Definition Excel

Generate the completed ERP_Definition Excel with correct record mappings and descriptions.


---

## Key Design Rules (Non-Negotiable)

- Canonical JSON = **meaning**
- Vendor PDF = **constraints**
- Sample EDI = **confirmation**
- Excel = **output target only**
- No vendor logic inside canonical JSON
- No runtime PDF parsing after onboarding

---

## Final Result

The `.exe` acts as a **vendor onboarding intelligence tool** that:
- Eliminates manual mapping
- Works for any vendor
- Produces deterministic, auditable ERP definition files