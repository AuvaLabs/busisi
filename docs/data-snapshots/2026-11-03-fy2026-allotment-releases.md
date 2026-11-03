# FY2026 allotment releases, 30 September status

## Publication boundary

This snapshot records DBM's Status of Allotment Releases for FY2026 as of
30 September 2026. It is an allotment ledger. It is not an obligation,
disbursement, Notice of Cash Allocation, contractor payment, receipt,
completion, or outcome ledger. Its published rows are agency and Special
Purpose Fund totals, not project-level records.

## Source identity

- Official report page: `https://www.dbm.gov.ph/index.php?catid=307&highlight=WzIwMjZd&id=4331:status-of-allotment-releases-as-of-september-30-2026&view=article`
- Official workbook: `https://www.dbm.gov.ph/wp-content/uploads/e-Fund_Releases/Status-of-Allotment-Releases/2026/September/FY-2026-as-of-September-30-Website.xlsx`
- Retrieved: `2026-11-03T16:07:22.152611+00:00`
- Workbook SHA-256: `05a902418e0a78339b82d71def04447eab44897b752d001343121bcbe6226aae`
- Workbook unit: thousand pesos
- Publication unit: integer centavos

## Reconciled controls

| Control | Program or adjusted program | Releases | Balance |
|---|---:|---:|---:|
| Current GAA | ₱4,391,044,969,000 | ₱4,072,227,740,000 | ₱318,817,229,000 |
| All sources | ₱6,793,162,000,000 | ₱6,532,951,466,000 | ₱260,210,534,000 |

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

- Snapshot manifest SHA-256: `f1bc8e28755d991b0db3095d71e53e4578d42a4291d14b4f1554035aa1dfbdd4`
- D1 SQL SHA-256: `13103918b649c4f9c748738f90a6b6fca14cb123743681f66cbd9b2b5821c5a6`
- D1 bundle manifest SHA-256: `aa1c67fce949793a95b8c1eea724248bfb4fe666c8808121cf1c7e9bfd5d7738`

The public interface is `/releases/`. Its API separates summary controls from
filtered records and links readers to the human-readable DBM report page rather
than exposing the source workbook as the primary reader action.
