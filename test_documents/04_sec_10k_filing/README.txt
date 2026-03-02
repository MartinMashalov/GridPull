FOLDER: 04_sec_10k_filing
PURPOSE: SEC 10-K annual filing PDFs with formal financial statements (balance sheet,
         income statement, cash flows, notes). Tests extraction of standardized
         GAAP financial statement tables.

DOCUMENTS INCLUDED:
  - alexander_baldwin_2024_10k.pdf
      Alexander & Baldwin, Inc. (NYSE: ALEX) — 2024 Annual Report on Form 10-K
      A Hawaii-based commercial real estate company (S&P SmallCap 600).
      Contains: audited balance sheet, income statement, cash flow statement,
      segment data tables, lease schedules, and debt maturity tables.
      Source: https://www.sec.gov/Archives/edgar/data/1545654/000154565425000013/alexanderbaldwin10-k.pdf
      Filed: 2025 (for fiscal year 2024)

  - berkshire_hathaway_2024_10k.pdf
      Berkshire Hathaway 2024 Annual Report (includes 10-K financial disclosures)
      Contains: consolidated financials for all Berkshire subsidiaries,
      insurance float tables, investment portfolio schedules.
      Source: https://www.berkshirehathaway.com/2024ar/2024ar.pdf

EXTRACTION GOAL:
  Target the following standard GAAP financial statement tables:

  1. CONSOLIDATED BALANCE SHEET (as of fiscal year end)
     | line_item | current_year_usd | prior_year_usd | section |
     (section = "Assets" / "Liabilities" / "Equity")

  2. CONSOLIDATED STATEMENTS OF OPERATIONS (Income Statement)
     | line_item | current_year_usd | prior_year_usd | prior_prior_year_usd |

  3. CONSOLIDATED STATEMENTS OF CASH FLOWS
     | line_item | current_year_usd | prior_year_usd |
     (section = "Operating" / "Investing" / "Financing")

  4. SEGMENT INFORMATION TABLE
     | segment_name | revenues | operating_income | total_assets | capex |

  5. DEBT SCHEDULE / NOTES PAYABLE TABLE
     | debt_instrument | maturity_date | interest_rate | principal_balance |

  6. SELECTED FINANCIAL DATA (5-year summary if present)
     | metric | year_1 | year_2 | year_3 | year_4 | year_5 |

TESTING NOTES:
  - 10-K filings use formal GAAP labeling — consistent column headers across companies.
  - Alexander & Baldwin (39MB) is a thorough real-estate 10-K with many footnote tables.
  - Berkshire 2024 (1.8MB) tests a large conglomerate with insurance/railroad segments.
  - Both documents include footnotes with sub-tables that should be identified separately.
  - Expected output: 50-200+ rows across 4-6 financial statement sheets.
