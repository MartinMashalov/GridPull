FOLDER: 03_insurance_eob
PURPOSE: Insurance Explanation of Benefits (EOB) and medical claim PDFs.
         Each document contains rows of individual services billed and adjudicated.

DOCUMENTS INCLUDED:
  - cms_eob_sample.pdf
      CMS (Centers for Medicare & Medicaid Services) sample EOB
      showing how Medicare processes a medical claim for a beneficiary.
      Source: https://www.cms.gov/files/document/11819-sample-explanation-benefits-508.pdf

  - cms_sbc_sample.pdf
      CMS Summary of Benefits and Coverage (SBC) completed sample form.
      Shows coverage tiers, copay/coinsurance amounts, and out-of-pocket limits.
      Source: https://www.cms.gov/cciio/resources/forms-reports-and-other-resources/downloads/sbc-sample-completed-mm-508-fixed-4-12-16.pdf

  - cms_eob_sample_spanish.pdf
      Spanish-language version of the CMS sample EOB — useful for testing
      multilingual/non-English field extraction.
      Source: https://www.cms.gov/files/document/11819-sample-explanation-benefits-508-spanish.pdf

  - cms_claims_processing_ch26.pdf  (if present)
      CMS Medicare Claims Processing Manual Chapter 26 — contains
      detailed claim form field definitions and sample claim data tables.
      Source: https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/clm104c26.pdf

EXTRACTION GOAL:
  Each EOB document may yield multiple rows — one per service line billed:

  | Field                   | Description                                          |
  |-------------------------|------------------------------------------------------|
  | patient_name            | Beneficiary/patient name                             |
  | member_id               | Insurance member or Medicare ID                      |
  | claim_number            | Unique claim reference number                        |
  | service_date            | Date of service (YYYY-MM-DD)                         |
  | provider_name           | Doctor, hospital, or facility name                   |
  | provider_npi            | NPI number if present                                |
  | service_description     | Procedure or service description                     |
  | procedure_code          | CPT / HCPCS procedure code                           |
  | diagnosis_code          | ICD-10 diagnosis code(s)                             |
  | billed_amount           | Amount provider billed (numeric, USD)                |
  | allowed_amount          | Insurance-allowed amount (numeric, USD)              |
  | plan_paid               | Amount plan paid (numeric, USD)                      |
  | patient_responsibility  | Patient copay/coinsurance/deductible (numeric, USD)  |
  | adjustment_reason       | Reason codes for adjustments (e.g. CO-45)            |
  | claim_status            | Paid / Denied / Pending                              |

TESTING NOTES:
  - EOB documents are among the most complex for extraction: they have
    dense tabular claim-line data, often spanning multiple pages.
  - The SBC form (cms_sbc_sample.pdf) uses a structured matrix of
    coverage tiers rather than line-item services — good for testing
    matrix/grid table parsing.
  - Spanish EOB tests language-agnostic field identification.
