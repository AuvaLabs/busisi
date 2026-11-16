# Community needs data check, 16 November 2026

## Published source

- Publisher: Philippine Statistics Authority
- Dataset: 2024 Census of Population through PSA OpenSTAT
- Census date: 1 July 2024
- Regional tables checked: 18
- National control table checked: 1
- Published place rows: 43,768
- Published regions: 18
- Published barangays: 42,011

Every response is stored with its original bytes, source URL, request-body
hash and SHA-256. Public rows keep the PSA geographic code and the source table
that supplied the value.

## National control check

| Measure | PSA national table | Sum of 18 regional tables | Difference |
|---|---:|---:|---:|
| Total population | 112,729,484 | 112,727,776 | 1,708 |
| Household population | 112,325,293 | 112,325,293 | 0 |
| Households | 29,665,206 | 29,665,206 | 0 |

Busisi publishes the national value as stated by PSA and does not distribute
the 1,708-person difference among regions.

## Source rows excluded

The PSA CAR response contains 1,148 appended Region II rows after the CAR
records. Those rows are excluded from the CAR table because their PSA codes do
not begin with the CAR region code. The correct Region II rows remain available
from the separate Region II table.

After excluding those rows, every included lower-level total matches its
published parent total. No missing amount is filled, moved or estimated.

## Public meaning

Population and household counts help readers compare project spending with the
number of people who may need services. They do not prove that a project is
necessary, unnecessary, wasteful or improper. They do not change Busisi red
flags.

The current release contains no individual CBMS information. Public poverty
and CBMS totals will remain separate until their official source files,
geographic identifiers and coverage limits have been checked.
