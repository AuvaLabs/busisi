# PSA local poverty source check, 16 November 2026

## Direct answer

Busisi is ready to check the official 2023 city and municipal poverty
spreadsheet, but the publisher currently blocks the automatic download. No
poverty values are published.

## What the official page says

- Publisher: Philippine Statistics Authority
- Release date: 6 February 2026
- Reference number: 2026-43
- Expected city, municipality and Manila sub-municipality estimates: 1,611
- Published poverty classification counts: 881, 603, 119, 8 and 0 across the
  five stated incidence ranges
- Official workbook:
  `https://psa.gov.ph/sites/default/files/phdsd/2_2023%20SAE_with%20PSGC_noHUC_06Feb2026.xlsx`

## What the automatic check does

The downloader accepts only the registered PSA HTTPS origin and exact workbook
path. A successful file is saved with a SHA-256 check code. Before a reviewed
release can be prepared, the workbook must provide:

1. exactly 1,611 unique PSGC identities;
2. a city, municipality or Manila sub-municipality name for every row;
3. poverty incidence, standard error, coefficient of variation and confidence
   limits as exact decimal values;
4. confidence limits that contain the estimate; and
5. classification totals that match the five counts stated by PSA.

Any failed condition keeps the entire file out of the public estimates table.
The public API exposes only the source-check status while the source is blocked.

## CBMS boundary

This pipeline does not publish Community-Based Monitoring System household
records. CBMS will remain separate until an official publisher provides
reusable aggregate tables with clear geographic coverage and no household
identifiers.
