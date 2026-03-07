FOLDER: 09_contracts_agreements
PURPOSE: Diverse dataset of legal contract and agreement PDFs for document extraction and analysis testing.
         30 synthetic but realistic contracts covering various business scenarios.

SYNTHETIC DOCUMENTS (contract_001.pdf through contract_030.pdf):
  - Automatically generated realistic contract documents
  - Various contract types (see below)
  - Real company pairs as contracting parties
  - Realistic effective dates and terms
  - Proper contract structure with numbered sections
  - Realistic compensation and payment terms

CONTRACT TYPES INCLUDED:
  1. Service Agreement
  2. Software License Agreement
  3. Non-Disclosure Agreement (NDA)
  4. Purchase Agreement
  5. Employment Agreement
  6. Lease Agreement
  7. Vendor Agreement
  8. Consulting Agreement
  9. Independent Contractor Agreement
  10. Supply Agreement
  11. Maintenance Agreement
  12. Partnership Agreement

DOCUMENT STRUCTURE:
  Each synthetic contract typically includes:
  - Contract Title: Type of agreement
  - Effective Date: When agreement starts
  - PARTIES SECTION:
    * Provider/Service Provider Name
    * Client/Customer Name
  - SCOPE OF SERVICES (Section 1)
    * Description of services to be provided
  - TERM (Section 2)
    * Duration in years
    * Effective dates
  - COMPENSATION (Section 3)
    * Payment terms (annual fee, monthly retainer, or hourly rate)
    * Representative amounts: $1,000 - $500,000
  - CONFIDENTIALITY (Section 4)
    * Standard confidentiality clause
  - LIABILITY (Section 5)
    * Liability and indemnification terms
  - GOVERNING LAW (Section 6)
    * US state jurisdiction

EXTRACTION FIELDS TO TEST:
  | Field                    | Example Value                        | Type     |
  |--------------------------|--------------------------------------|----------|
  | contract_type            | Service Agreement                    | String   |
  | effective_date           | January 15, 2025                    | Date     |
  | provider_name            | Acme Corporation                     | String   |
  | client_name              | Beta Industries                      | String   |
  | service_description      | Professional services related to... | String   |
  | term_length              | 3                                    | Integer  |
  | term_unit                | years                                | String   |
  | payment_type             | annual fee / monthly retainer / hourly | String |
  | compensation_amount      | $250,000                             | Currency |
  | confidentiality_clause   | Yes/Present                          | Boolean  |
  | governing_state          | California                           | String   |
  | signature_parties        | 2 (Provider, Client)                 | Integer  |

PARTY PAIRS (Company Examples):
  Diverse fictional company combinations:
  - Acme Corporation + Beta Industries
  - TechStart LLC + Global Solutions Inc
  - FastTrack Services + Enterprise Partners
  - Innovation Labs + Digital Ventures
  - Cloud Systems Corp + Data Analytics LLC
  - BuildRight Construction + Property Developers
  - Premium Consulting + Fortune 500 Corp
  - NetCom Solutions + Telecommunications Inc
  - GreenTech Innovations + Environmental Services
  - Finance Partners + Investment Holdings

PAYMENT STRUCTURES INCLUDED:
  Each contract randomly includes one of:
  1. Fixed Annual Fee
     - Range: $10,000 - $500,000
     - Example: "Client shall pay Provider a fixed annual fee of $150,000."
  
  2. Monthly Retainer
     - Range: $1,000 - $50,000 per month
     - Example: "Client shall pay Provider a monthly retainer of $15,000."
  
  3. Hourly Rate
     - Range: $50 - $300 per hour
     - Example: "Provider shall bill Client at an hourly rate of $125/hour."

JURISDICTIONS:
  Contracts include various US state governing laws:
  - California
  - New York
  - Texas
  - Illinois
  - Florida

USAGE FOR TESTING:
  1. Party identification: Finding and extracting company names
  2. Date extraction: Effective dates in natural language format
  3. Monetary values: Different currency formats (annual, monthly, hourly)
  4. Section headers: Structured document navigation
  5. Multi-line content: Long descriptive text extraction
  6. Contract terms: Duration and unit extraction
  7. Jurisdiction: Legal location identification
  8. Signature blocks: Finding parties and signature lines
  9. Clause detection: Identifying key contract provisions
  10. Document classification: Determining contract type

DOCUMENT VARIATION:
  - Each document has unique company pairs
  - Random contract type selection
  - Variable dates ranging across recent history
  - Random service descriptions
  - Different compensation models
  - Varying term lengths (1-5 years)
  - Realistic state jurisdiction assignment

GENERATION DETAILS:
  - Generated with: generate_test_pdfs.py
  - Library: fpdf2
  - Format: Standard PDF with proper contract layout
  - Total Count: 30 documents
  - All parties, dates, and amounts are fictional and generated
