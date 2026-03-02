FOLDER: 05_purchase_orders
PURPOSE: US Government procurement / purchase order forms. Tests extraction of
         structured government contracting fields from standardized forms.

DOCUMENTS INCLUDED:
  - gsa_sf1449_solicitation_order.pdf
      GSA Standard Form 1449 (Rev. Nov 2021)
      "Solicitation/Contract/Order for Commercial Products and Commercial Services"
      The primary form used for commercial item acquisitions under FAR Part 12.
      Contains: contract number, solicitation number, vendor info, line items,
      quantities, unit prices, delivery schedule, payment terms, clauses.
      Source: https://www.gsa.gov/system/files/SF1449-21.pdf

  - gsa_sf26_contract_award.pdf
      GSA Standard Form 26 (Rev. 2022)
      "Award/Contract"
      Used for awarding sealed-bid contracts. Contains contract award data,
      contractor information, contract line items, period of performance.
      Source: https://www.gsa.gov/system/files/SF26-22.pdf

  - gsa_sf1442_construction_solicitation.pdf
      GSA Standard Form 1442 (Rev. Dec 2022)
      "Solicitation, Offer, and Award (Construction, Alteration, or Repair)"
      Construction-specific solicitation form with project description,
      bid schedule, and award information.
      Source: https://www.gsa.gov/system/files/SF1442-22.pdf

  - gsa_sf24_bid_bond.pdf
      GSA Standard Form 24 (Rev. Feb 2024)
      "Bid Bond"
      Accompanies sealed bids. Contains principal/surety info, penal sum,
      contract amount, and bonding details.
      Source: https://www.gsa.gov/system/files/2024-02/SF24-23a.pdf

EXTRACTION GOAL:
  Each purchase order / procurement form should yield rows of the following fields:

  | Field                  | Description                                            |
  |------------------------|--------------------------------------------------------|
  | solicitation_number    | Solicitation / RFP / IFB reference number              |
  | contract_number        | Award / contract number (PIID)                         |
  | requisition_number     | Internal requisition or PR number                      |
  | award_date             | Date contract was awarded (YYYY-MM-DD)                 |
  | effective_date         | Contract effective date (YYYY-MM-DD)                   |
  | contracting_office     | Agency and contracting office name                     |
  | vendor_name            | Contractor / offeror name                              |
  | vendor_address         | Contractor street address, city, state, zip            |
  | vendor_cage_code       | Commercial and Government Entity code                  |
  | vendor_duns            | DUNS / UEI number                                      |
  | line_item_number       | Contract line item number (CLIN)                       |
  | line_item_description  | Description of supplies/services                       |
  | quantity               | Quantity ordered                                       |
  | unit_of_measure        | Unit (EA, LO, HR, etc.)                                |
  | unit_price             | Unit price (numeric, USD)                              |
  | total_price            | Extended price for line item (numeric, USD)            |
  | period_of_performance  | Start and end dates for delivery/performance           |
  | delivery_address       | Ship-to or delivery location                           |
  | payment_terms          | Net days / discount terms                             |
  | obligated_amount       | Total obligated contract value (numeric, USD)          |
  | naics_code             | NAICS code for the procurement                         |
  | set_aside_type         | Small business set-aside type if applicable            |

TESTING NOTES:
  - These are blank/template forms — many fields will be empty.
    The test verifies that the extractor correctly identifies field labels
    and their corresponding (empty or filled) values.
  - SF 1449 and SF 1442 have multiple-page line item schedules.
  - The bid bond (SF 24) tests extraction of a single-page dense form.
  - Government forms use standardized block-field layouts — useful for
    testing box/field detection vs. pure table extraction.
