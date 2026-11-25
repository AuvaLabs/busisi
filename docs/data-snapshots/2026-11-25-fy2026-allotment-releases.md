# FY2026 allotment releases, 31 October status

## Publication boundary

This snapshot records DBM's Status of Allotment Releases for FY2026 as of
31 October 2026. It is an allotment ledger. It is not an obligation,
disbursement, Notice of Cash Allocation, contractor payment, receipt,
completion, or outcome ledger. Its published rows are agency and Special
Purpose Fund totals, not project-level records.

## Source identity

- Official report page: `https://www.dbm.gov.ph/index.php?catid=307&id=4405&view=article`
- Official workbook: `https://www.dbm.gov.ph/wp-content/uploads/e-Fund_Releases/Status-of-Allotment-Releases/2026/October/FY-2026-as-of-October-Website.xlsx`
- Retrieved: `2026-11-25T05:15:29.571030+00:00`
- Workbook SHA-256: `b051d737ce26f18fd138bb48c086b882a1e762688b0ae4efcf6a04bbae0054e6`
- Workbook unit: thousand pesos
- Publication unit: integer centavos

## Reconciled controls

| Control | Program or adjusted program | Releases | Balance |
|---|---:|---:|---:|
| Current GAA | ₱4,391,044,969,000 | ₱4,136,652,049,000 | ₱254,392,920,000 |
| All sources | ₱6,793,162,000,000 | ₱6,705,889,516,000 | ₱87,272,484,000 |

Both controls satisfy `program or adjusted program - releases = balance`
exactly after normalization.

## Published hierarchy

- 96 records total
- 36 department records
- 47 attached-agency and subunit records
- 13 Special Purpose Fund records

Attached agencies and subunits retain their parent identity. Parent and child
rows must not be added together as if they were independent national totals.

## Publication artifacts

- Snapshot manifest SHA-256: `08a35b48e651b3839b4693bc38bc11d7cc151e7d0038c9c99c069372b4f6125a`
- D1 SQL SHA-256: `00d874d563cb7d6a746cbb03cec25e6ae8dbd6b5247951178fb1322fa9fcde51`
- D1 bundle manifest SHA-256: `f698665a93bb4394a1a734676bff21c819e33be364f1dd94031b279408312bcc`

The public interface is `/releases/`. Its API separates summary controls from
filtered records and links readers to the human-readable DBM report page rather
than exposing the source workbook as the primary reader action.
