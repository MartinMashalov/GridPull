FOLDER: 03_insurance_eob - SYNTHETIC EOB DATASET EXPANSION
PURPOSE: Expanding EOB testing coverage with 30+ synthetic but realistic EOB documents.
         These documents are generated with realistic healthcare data, provider names, 
         procedure codes, and claim amounts to support comprehensive testing.

SYNTHETIC DOCUMENTS (eob_claim_001.pdf through eob_claim_034.pdf):
  - Automatically generated realistic EOB documents
  - Each contains 1 service claim with procedural data
  - Realistic healthcare provider names (Mayo Clinic, Johns Hopkins, etc.)
  - Real medical procedures and copay scenarios
  - Proper EOB structure and formatting
  - Varying deductible, copay, insurance payment amounts

DOCUMENT STRUCTURE:
  Each synthetic EOB includes:
  - Member ID: Format EHPxxxxxx (insurance member identifier)
  - Claim ID: Format CLMxxxxxxxx (unique claim reference)
  - Service Date: Random date within last 60 days
  - Provider Name: Real hospital/clinic names
  - Service Description: Medical procedure (office visit, X-ray, MRI, etc.)
  - Claim Summary Table:
    * Provider Charge: Amount billed
    * Allowed Amount: Insurance-approved amount
    * Your Copay: Patient copay amount
    * Applied to Deductible: Patient deductible portion
    * Plan Paid: Insurance payment
    * What You Owe: Patient responsibility total

EXTRACTION FIELDS TO TEST:
  | Field                   | Example Value                                     |
  |-------------------------|---------------------------------------------------|
  | member_id               | EHP123456                                         |
  | claim_id                | CLM98765432                                       |
  | service_date            | 03/15/2025                                        |
  | provider_name           | Northwestern Memorial Hospital                    |
  | service_description     | Chest X-Ray                                       |
  | provider_charge         | $200.00                                           |
  | allowed_amount          | $160.00                                           |
  | your_copay              | $20.00                                            |
  | deductible_applied      | $100.00                                           |
  | plan_paid               | $30.00                                            |
  | patient_responsibility  | $120.00 (copay + deductible + coinsurance)       |

PROCEDURE VARIETY:
  Documents include diverse procedures:
  - Office visits (new and established patient)
  - Diagnostic imaging (X-ray, MRI, CT Scan, Ultrasound)
  - Laboratory tests (blood panels)
  - Physical therapy
  - Dental services
  - Emergency room visits
  - Specialty consultations (cardiology, orthopedics)
  - Prescription medications (generic and brand)

USAGE FOR TESTING:
  1. Table/grid extraction: EOB tables with multiple columns
  2. Financial data extraction: Currency amounts, percentages
  3. Medical code extraction: Provider names, procedure names
  4. Multi-row processing: Each PDF has one claim row to extract
  5. Deductible/copay logic: Test calculation of patient responsibility
  6. Date parsing: Service dates in MM/DD/YYYY format
  7. Line item variation: Different procedure types and copay amounts

GENERATION DETAILS:
  - Generated with: generate_test_pdfs.py
  - Library: fpdf2
  - Data: Realistic provider names, procedure types, pricing ranges
  - Format: Proper PDF with borders, headers, and structured layout
  - Total Count: 30-34 documents in this folder
