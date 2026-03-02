FOLDER: 01_invoices
PURPOSE: Individual vendor/customer invoice PDFs for testing single-row extraction.

DOCUMENTS INCLUDED:
  - invoice_Aaron Bergman_36258.pdf     (sample retail invoice #36258)
  - invoice_Aaron Hawkins_36651.pdf     (sample retail invoice #36651)
  - invoice_Aaron Smayling_15978.pdf    (sample retail invoice #15978)
  - invoice_Adam Bellavance_21617.pdf   (sample retail invoice #21617)
  - invoice_Adam Hart_36279.pdf         (sample retail invoice #36279)
  - sample_invoice_azure.pdf            (Microsoft Azure/Contoso invoice sample)

SOURCES:
  - 5 invoices extracted from: https://github.com/femstac/Sample-Pdf-invoices
    (1000+ PDF Invoice Folder dataset)
  - sample_invoice_azure.pdf from:
    https://github.com/ssukhpinder/AzureOpenAI/raw/main/samples/Azure.OpenAI.DocumentIntelligence/sample-document/sample-invoice.pdf

EXTRACTION GOAL:
  Each invoice PDF should yield ONE row in a spreadsheet with these columns:

  | Field               | Description                                        |
  |---------------------|----------------------------------------------------|
  | invoice_number      | Unique invoice ID / order number                   |
  | invoice_date        | Date the invoice was issued (YYYY-MM-DD)           |
  | due_date            | Payment due date (YYYY-MM-DD)                      |
  | vendor_name         | Company or individual issuing the invoice          |
  | vendor_address      | Vendor street address, city, state, zip            |
  | customer_name       | Bill-to party name                                 |
  | customer_address    | Bill-to address                                    |
  | line_items          | Comma-separated list of items/services billed      |
  | subtotal            | Pre-tax total (numeric, USD)                       |
  | tax_amount          | Tax applied (numeric, USD)                         |
  | shipping            | Shipping/freight charge if any (numeric, USD)      |
  | total_amount_due    | Final total including tax/shipping (numeric, USD)  |
  | payment_terms       | e.g. "Net 30", "Due on receipt"                    |
  | currency            | Currency code (e.g. USD, EUR)                      |

TESTING NOTES:
  - These invoices vary in format and number of line items.
  - The azure sample (sample_invoice_azure.pdf) has a more complex multi-line
    itemized format typical of enterprise software invoices.
  - Expected output: 6 rows, one per PDF file.
