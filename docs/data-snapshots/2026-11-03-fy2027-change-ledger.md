# FY2027 NEP-to-House change ledger snapshot

Retrieved and verified on 2026-11-03.

## Scope

This release compares project rows in the FY2027 National Expenditure Program
with House Bill 10858 project lists. BetterGov is the structured secondary
source. The archive retains its source links, mirrored evidence PDFs and source
commit `a0caa778442cdae5583f5a006ea7401dab00e5ac`.

| Dataset | Rows | NEP total | House total | Quarantined |
|---|---:|---:|---:|---:|
| DPWH | 17,613 | PHP 572,924,074,000 | PHP 587,075,661,000 | 426 |
| Farm-to-market roads | 1,059 | PHP 16,000,000,000 | PHP 19,628,100,000 | 0 |
| Health facilities | 746 | PHP 14,472,519,000 | PHP 10,021,659,000 | 0 |
| Irrigation | 1,013 | PHP 17,598,181,000 | PHP 17,999,305,000 | 0 |

The acquisition contains 105 paginated JSON artifacts, 20,431 rows and eight
PDF artifacts. The overview artifact SHA-256 is
`f47cc042ae08efb6883854b23b230dda25cba073765edfe7aeb84ce509b32177`.
Every PDF was downloaded and checked against its advertised SHA-256 digest.

## Verification

The release gate requires all of the following:

1. Page and document hashes match the archived manifest.
2. Every page passes fiscal-year, currency, unit, URL and row-schema checks.
3. Peso values convert to integer centavos without floating-point arithmetic.
4. Record counts and NEP and House totals reconcile exactly for every dataset.
5. Held and scope-review records publish as quarantined.
6. The generated SQL bundle loads into SQLite and passes `integrity_check`.

The generated bundle contains one metadata file and 21 data chunks. Its
manifest SHA-256 is
`329b970f8b80daf8fb95e775bfe231e454b480f827e00ba8d0fa4d839eeb09bb`.

## Limitations

- A changed amount or a House-only row is not evidence of corruption or an
  unlawful insertion. It is a lead for documentary review.
- BetterGov performed the row extraction and comparison. Busisi independently
  validates the published schema, hashes, arithmetic and control totals, but
  does not claim to have reproduced every PDF extraction independently.
- The DPWH comparison uses the third-reading House project list. The other
  three lists use the source's documented House stage.
- Three NEP annex extracts have no original-source URL in the source manifest.
  Their archived mirror bytes and hashes are disclosed, and this limitation is
  not hidden.
- The ledger does not yet trace Senate, bicameral, final GAA, release,
  procurement or physical implementation stages.
