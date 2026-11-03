# FY2027 appropriation-head ledger

Snapshot date: 2026-11-03

## Published scope

The ledger compares 39 national appropriation heads in the FY2027 National
Expenditure Program with the third-reading totals printed in House Bill 10858.
It also publishes five child rows under Congress so the Senate, Senate
Electoral Tribunal, Commission on Appointments, House of Representatives, and
House of Representatives Electoral Tribunal can be inspected separately.

The child rows are not added to the national total a second time.

## Reconciliation controls

- FY2027 NEP national total, including Automatic Appropriations:
  ₱7,200,186,000,000.
- NEP scope controlled by the General Appropriations Bill:
  ₱4,618,702,998,000.
- HB 10858 printed total for new appropriations:
  ₱4,606,066,495,000.
- Net movement inside the comparable bill scope:
  -₱12,636,503,000.
- Public rows: 44.
- Rows with a House comparison: 43.
- Rows where the House stage is not applicable: one, Automatic Appropriations.

The 37 department and constitutional-body totals plus six Special Purpose Fund
sections add exactly to the House control. The 39 NEP heads add exactly to the
NEP national control. All values are stored as integer centavos.

## Largest document movements

| Appropriation head | FY2027 NEP | House bill | Movement |
|---|---:|---:|---:|
| Allocations to Local Government Units | ₱6,560,912,000 | ₱113,218,176,000 | +₱106,657,264,000 |
| Department of Social Welfare and Development | ₱241,560,136,000 | ₱262,756,533,000 | +₱21,196,397,000 |
| Department of Agriculture | ₱172,165,114,000 | ₱182,473,178,000 | +₱10,308,064,000 |
| Department of Public Works and Highways | ₱643,953,276,000 | ₱654,102,015,000 | +₱10,148,739,000 |
| Department of Education | ₱975,962,852,000 | ₱910,586,984,000 | -₱65,375,868,000 |
| Department of Transportation | ₱300,960,436,000 | ₱259,075,428,000 | -₱41,885,008,000 |
| Budgetary Support to Government Corporations | ₱191,300,497,000 | ₱179,514,110,000 | -₱11,786,387,000 |
| Department of Information and Communications Technology | ₱19,491,495,000 | ₱8,357,611,000 | -₱11,133,884,000 |

These are changes between proposed appropriation documents. They do not show
release, obligation, procurement, disbursement, payment, receipt, loss, or
wrongdoing.

## Source provenance

- NEP normalized department data came from the BetterGov Budget API and was
  reconciled to its ₱7.200186 trillion national control.
- House values came from page-specific extraction of mirrored HB 10858
  third-reading Volumes I-A and I-B at source commit
  `a0caa778442cdae5583f5a006ea7401dab00e5ac`.
- Volume I-A SHA-256:
  `79f56b8d577246342b59cc996afdd707523268f0bde10378e3c1b5ef844451fd`.
- Volume I-B SHA-256:
  `4cc0f17e472d1af380ea6d3972561f6bb241137826fd85ed7e7e70bcd92986b9`.
- Generated bundle manifest SHA-256:
  `ffc94d0529058fb9f310698adbe3a3f5b4cc0503c7fa5ecb60368a49ab829d76`.

Original bytes, extracted text, API responses, manifests, and content-addressed
archive records remain under the gitignored `data/budget_watchdog/` boundary.

## Current limitations

- The House PDFs are immutable mirrors at a pinned repository commit. The
  Senate portal no longer exposes a stable direct document link for every
  volume, so the ledger says mirrored source rather than official live source.
- Attached agencies below the 39 appropriation heads are not yet individually
  compared, except for the five Congress institutions.
- Senate amendments, bicameral conference, enacted GAA, allotment, release,
  obligation, procurement, disbursement, and payment stages are unavailable.
- No movement is classified as pork, insertion, corruption, or wrongdoing.
