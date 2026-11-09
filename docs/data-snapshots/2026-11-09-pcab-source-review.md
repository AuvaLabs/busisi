# PCAB source review, 2026-11-09

## Why this review was required

The official PCAB regular-license grid fell below Busisi's reviewed minimum.
Scheduled checks observed 18,832 and 18,865 rows. A separate bounded review at
08:20 UTC observed 18,882 rows. All three responses passed the existing JSON,
page-count, row-count, date, category and government-registration validation.
The changing count therefore reflected the live source, not a partial response
accepted by Busisi.

The review compared the 18,925-row PCAB response with SHA-256
`b1e9a03d956ae1bd31e650f4f2b03e58c392a5813dc8f9d72bd759f86fefb908`
against the 18,882-row response with SHA-256
`67be2c7d3735a1b4ad9b8c0386aae8171295b27415d30c601d4a78ca5b5ad759`.

## What changed

- 259 record identifiers were added.
- 290 expired record identifiers were removed.
- 12 record identifiers with future validity dates disappeared from the grid.
- Five retained record identifiers changed.

The five retained changes were:

- `128050` and `129211`: firm name changed from KCKS CONSTRUCTION SERVICES to
  KCKS BUILDERS INCORPORATED. The license number and validity date did not
  change.
- `128236`: JFAP CONSTRUCTION validity changed from 2027-08-29 to 2029-08-29.
- `129204`: PAR NORTH CONSTRUCTION CORPORATION's duplicated former-name text
  was removed. The license number and validity date did not change.
- `129830`: WEL CONTRACTING CORPORATION's authorized managing officer changed.
  The license number, category and validity date did not change.

## Checks on the 12 missing grid records

The official PCAB detail page for every missing record still stated `License
Valid!`. Each page agreed with the reviewed contractor name, license number and
validity date. None of the 12 license numbers appeared in the official
25-record suspended and revoked table acquired during the review. That table
had SHA-256
`c8f146fffbef0c4ff3350d1525d52964514630748d7c5fb64ad321d7ade9eb95`.

| Record | License | Firm | Valid to | Detail SHA-256 |
|---|---|---|---|---|
| `115834` | `40114` | FAJR CONSTRUCTION PARTS & SUPPLY | 2028-02-24 | `f36daf96ab553611b48ff230fb20e4bde649761f7367ef8a0dbd85bf42c7d48c` |
| `116362` | `41868` | SUPREA PHILS. DEVELOPMENT CORP. | 2027-03-30 | `54cb00202c32f436889439fbd241e3c0c26d07b05342da9251fb677dd05fa74a` |
| `116367` | `43584` | M E DIMACULANGAN CONSTRUCTION INC. | 2027-02-01 | `9e4ffd62b7e5ad5ad1417e43e03bd8b44b00c2ca788b855436d8a809a5cb2774` |
| `117524` | `37651` | RAND CHARLIE ENTERPRISES | 2028-02-21 | `088c29c72d4cc95ac94b6b70f534abd525beb72e86680a56ceb97dcdb14bb9bb` |
| `117907` | `34727` | RHYMAC CONSTRUCTION AND SUPPLY | 2028-01-10 | `33f339b3897692badecb2a88298d64c8d3e529181ea2cd6b0863cd73f6ba0a18` |
| `118139` | `49471` | DMDD ALUMINUM GLASS AND METAL WORKS | 2027-04-06 | `4c7b4e4fc4d2b97c34bd032b5bb610e8dc9b5570a058d40703546c170c8fb2ca` |
| `118576` | `54857` | 3REX MYNO BUILDERS' CONSTRUCTION SERVICES | 2027-04-14 | `dd4d3883441c3d4bea20b465a9513d079c6eda2a8350dad91526295e092bb6c5` |
| `119535` | `46052` | HRC CONTRACTOR ELEVATOR ESCALATOR | 2027-04-24 | `54b182a0da739c8fd9f4e077f40105fed140ac56e92d2d5f79841d80ddff71ef` |
| `119578` | `49351` | NXTLVL WATER TECHNOLOGY INCORPORATED | 2027-03-09 | `ce932e2181fb8d1f3a884e3af2c177b043e1d59058c366caf29078431d465259` |
| `121047` | `45759` | TFM POWERLINE CONSTRUCTION INC. | 2027-02-27 | `90ed9e0066abdb61e511b92ec495e494e065bf58f1795fa0603333bbe96a5fb9` |
| `121536` | `35312` | ALTHAEA ENTERPRISES | 2027-09-05 | `5885a3ac529238fdcfa50ea449784533de1f4f1572b1fbccc823123e1687949b` |
| `125332` | `53424` | MEGA SPEED ICT SOLUTIONS INC. | 2027-09-20 | `6ee7336c2c5d30b7cceb38d5b0d03ea3994df2369a108a85ba7158942f62feef` |

## Decision

Busisi does not treat the 12 contractors as unlicensed. The official grid and
the official detail pages disagree, so the 12 records remain explicit source
inconsistencies. The monitor now reacquires and validates every detail page on
each run. A missing page, a non-valid status, or a change in contractor name,
license number or validity date fails the monitor.

The new count floor is 18,623. It is calculated only from the previously
reviewed 18,925 rows by subtracting 290 expired removals and the 12 records now
checked through their official detail pages. The 259 additions do not lower the
floor. Aggregate count monitoring can still miss one row disappearing while a
different row is added, so a future floor breach requires another full row
transition review. The 12 known grid omissions are checked by exact identity on
every run instead of relying on the aggregate count.

The public contractor dataset remains tied to its existing disclosed snapshot.
This source review changes monitoring behavior only. It does not silently
replace contractor identities or publish a new contractor verification set.
