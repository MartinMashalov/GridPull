FOLDER: 08_cash_flow_statements
PURPOSE: Expanded dataset of cash flow statement PDFs for comprehensive financial extraction testing.
         30 synthetic but realistic cash flow statements from fictional companies.

SYNTHETIC DOCUMENTS (cashflow_statement_001.pdf through cashflow_statement_030.pdf):
  - Automatically generated realistic cash flow statements
  - Based on corporate financial statement format
  - Real company names (TechCorp, Mayo Clinic, etc.)
  - Realistic financial figures (thousands of dollars)
  - Proper accounting structure with operating, investing, financing activities
  - Varying multi-year fiscal years (2021-2024)

DOCUMENT STRUCTURE:
  Each synthetic cash flow statement includes:
  - Company Name: Fictional corporation
  - Fiscal Year: Ending December 31, YYYY
  - Amount Unit: In thousands
  
  THREE MAIN SECTIONS:
  
  1. CASH FLOWS FROM OPERATING ACTIVITIES
     - Net Income: $50,000 - $500,000
     - Depreciation and Amortization
     - Deferred Taxes
     - Change in Accounts Receivable
     - Change in Accounts Payable
     - NET CASH FROM OPERATING ACTIVITIES (subtotal)
  
  2. CASH FLOWS FROM INVESTING ACTIVITIES
     - Capital Expenditures (negative)
     - Acquisitions (optional, when present)
     - Proceeds from Sales of Investments
     - NET CASH FROM INVESTING ACTIVITIES (subtotal)
  
  3. CASH FLOWS FROM FINANCING ACTIVITIES
     - Proceeds from Debt (optional)
     - Repayment of Debt (negative)
     - Dividends Paid (negative)
     - Share Repurchase (optional, negative)
     - NET CASH FROM FINANCING ACTIVITIES (subtotal)
  
  SUMMARY:
  - Net Increase/(Decrease) in Cash
  - Cash at Beginning of Year
  - Cash at End of Year

EXTRACTION FIELDS TO TEST:
  | Field                        | Example Value       | Type     |
  |------------------------------|---------------------|----------|
  | company_name                 | TechCorp Industries | String   |
  | fiscal_year                  | 2024                | Integer  |
  | net_income                   | $250,000            | Currency |
  | depreciation_amortization    | $45,000             | Currency |
  | operating_cash_flow          | $350,000            | Currency |
  | capital_expenditures         | $(100,000)          | Currency |
  | investing_cash_flow          | $(80,000)           | Currency |
  | debt_repayment               | $(30,000)           | Currency |
  | dividends_paid               | $(20,000)           | Currency |
  | financing_cash_flow          | $(50,000)           | Currency |
  | net_change_in_cash           | $220,000            | Currency |
  | beginning_cash               | $150,000            | Currency |
  | ending_cash                  | $370,000            | Currency |

COMPANY VARIETY:
  Diverse fictional companies across industries:
  - TechCorp Industries (technology)
  - Global Finance LLC (financial services)
  - Manufacturing Solutions Inc (manufacturing)
  - Retail Dynamics Corp (retail)
  - Healthcare Innovations Ltd (healthcare)
  - Energy Systems Corp (energy)
  - Digital Services Inc (IT services)
  - Consumer Goods Ltd (CPG)
  - Transportation Corp (logistics)
  - Real Estate Holdings (real estate)
  - Agriculture Systems Inc (agriculture)
  - Telecommunications Inc (telecom)

USAGE FOR TESTING:
  1. Table structure: Multi-section hierarchical layout
  2. Financial data extraction: Large currency amounts in thousands
  3. Positive/negative values: Parentheses for negative amounts
  4. Subtotals: Multiple levels of summation
  5. Section headers: Category-based data grouping
  6. Line-item variation: Different accounting items in each section
  7. Number formatting: Comma-separated thousands notation
  8. Context detection: Operating vs Investing vs Financing activities
  9. Calculated fields: Net changes and totals

REALISTIC FINANCIAL RANGES:
  - Operating Cash Flow: $50,000 - $500,000+
  - Capital Expenditures: $(20,000) - $(150,000)
  - Debt Activity: Variable, realistic corporate financing
  - Dividends: $(5,000) - $(50,000)
  - Share Buybacks: Optional, $(0) - $(50,000)

GENERATION DETAILS:
  - Generated with: generate_test_pdfs.py
  - Library: fpdf2
  - Format: Standard PDF with borders and proper accounting layout
  - Total Count: 30 documents
  - All values in thousands (as indicated in documents)
