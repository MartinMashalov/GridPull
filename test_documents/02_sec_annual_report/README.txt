FOLDER: 02_sec_annual_report
PURPOSE: Large multi-page annual report with many financial tables; tests
         multi-row extraction from a single dense document.

DOCUMENTS INCLUDED:
  - berkshire_hathaway_2023_annual_report.pdf   (Berkshire Hathaway 2023 Annual Report)

SOURCE:
  https://www.berkshirehathaway.com/2023ar/2023ar.pdf
  (Publicly available on berkshirehathaway.com — Warren Buffett's annual letter
   plus audited financial statements for all major subsidiaries)

EXTRACTION GOAL:
  This document contains MANY tables. The primary extraction targets are:

  1. CONSOLIDATED BALANCE SHEET
     Expected columns per row:
     | line_item            | year_2023     | year_2022     |
     | (e.g. "Cash", "Debt")| (USD million) | (USD million) |

  2. CONSOLIDATED INCOME STATEMENT
     Expected columns per row:
     | line_item            | year_2023     | year_2022     | year_2021     |

  3. CONSOLIDATED STATEMENTS OF CASH FLOWS
     Expected columns per row:
     | line_item            | year_2023     | year_2022     | year_2021     |

  4. INSURANCE SUBSIDIARIES TABLE (GEICO, General Re, BHRG, etc.)
     Expected columns:
     | subsidiary_name | premiums_written | premiums_earned | underwriting_gain_loss |
     | investment_income | pretax_earnings |

  5. RAILROAD / UTILITIES / ENERGY TABLE (BNSF, BHE)
     | segment | revenues | operating_expenses | operating_earnings | capex |

TESTING NOTES:
  - This is a stress-test document: 100+ pages, multiple table formats,
    tables that span page breaks, and tables with merged/nested headers.
  - Berkshire has dozens of subsidiaries listed in schedule-of-investments tables.
  - Expected output: hundreds of rows across multiple sheets.
  - Use this to test: page-break table stitching, multi-level header parsing,
    and large-document throughput.
