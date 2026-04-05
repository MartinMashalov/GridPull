TEST SCENARIO: Insurance SOV Email Workflow
==========================================

This folder simulates the real-world workflow where insurance brokers email
Statement of Values (SOV) / Property Schedule documents to underwriters for
policy quoting and renewal.

SCENARIO OVERVIEW
-----------------
Three commercial insurance clients are up for renewal. Their respective brokers
have emailed property schedules (SOVs) and vehicle schedules to underwriters at
fictitious carrier "Pinnacle Commercial Insurance."

CLIENTS & DOCUMENTS
-------------------

1. Acme Manufacturing Group (15 locations)
   File: sov_acme_manufacturing_15_locations.pdf
   Broker: Sarah Chen at Meridian Risk Partners
   Underwriter: David Kowalski at Pinnacle Commercial Insurance
   Email: acme_manufacturing_renewal_sov.eml
   Lines of Business: Commercial Property, Inland Marine

2. Westfield Retail Properties LLC (8 retail locations)
   File: sov_westfield_retail_8_locations.pdf
   Broker: James Harrington at Summit Insurance Group
   Underwriter: Rachel Torres at Pinnacle Commercial Insurance
   Email: westfield_retail_property_schedule.eml

3. ABC Logistics & Transport Inc (22 vehicles)
   File: vehicle_schedule_abc_logistics_22_vehicles.pdf
   Broker: Marcus Webb at Coastal Insurance Advisors
   Underwriter: Lisa Nakamura at Pinnacle Commercial Insurance
   Email: abc_logistics_vehicle_schedule.eml

4. Follow-up / additional emails:
   acme_followup_corrected_sov.eml    -- broker sends corrected file
   westfield_coverage_inquiry.msg      -- Outlook-format follow-up
   abc_logistics_endorsement.msg       -- Outlook-format policy change request

FILE TYPES
----------
.eml  -- Standard RFC-2822 email format (viewable in any text editor or email client)
.msg  -- Microsoft Outlook email format (plain-text representation for testing)
.pdf  -- PDF property/vehicle schedule documents generated with ReportLab

GENERATE SCRIPT
---------------
generate_sov_samples.py -- Python script that generates all three PDF files.
Run with: python3 generate_sov_samples.py

DATA NOTES
----------
- All company names, addresses, and personnel are fictional
- Property values are in the $500K-$5M range typical for commercial accounts
- Construction types: Frame, Masonry, Joisted Masonry, Steel Frame, Fire Resistive
- Vehicle values reflect commercial fleet (tractors, trailers, vans, pickups)
- Locations span multiple states (Midwest/Southeast focus)
