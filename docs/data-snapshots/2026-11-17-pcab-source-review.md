# PCAB source review, 17 November 2026

## Direct answer

The official PCAB regular-license table fell below Busisi's reviewed minimum.
A row-by-row comparison supports a lower monitoring floor without treating any
active removed license as expired or accepting a changed retained row.

## Where the information came from

Both responses came from the registered PCAB regular-license endpoint. Busisi
saved the original bytes before review and confirmed that each file matched its
SHA-256 check code.

- Last passing response: 18,657 rows, retrieved 16 November 2026
- Last passing SHA-256:
  `6e450af57d1210164c42087b1135ab799675d4341809989d365dfafdb19da348`
- Lower response: 18,604 rows, retrieved 16 November 2026
- Lower-response SHA-256:
  `220dd4e215e86377e2d61309ef81baa2459e1e789e0b4677c686bf7bef20ae71`

## What the row comparison found

- 81 removed record identifiers had validity dates on or before 16 November
  2026.
- 28 record identifiers were added.
- No record with a future validity date was removed.
- No retained record changed its contractor name, license number, authorized
  managing officer, category, validity date or government-registration value.
- All 12 valid licenses previously missing from the grid still matched their
  saved official detail-page identities and reported a valid status.

The net difference was 53 rows. The comparison passed because every removal
was expired and no active or retained identity changed.

## Decision

The reviewed minimum is 18,576 rows. It is calculated from the last passing
18,657-row response by subtracting only the 81 expired removals. The 28 newly
added records do not reduce the floor.

The observed 18,604 rows remain 28 rows above the reviewed minimum. A future
response below 18,576 must stop again for another row-level review. The monitor
continues to check the 12 known grid omissions through their official detail
pages on every run.

This review changes source monitoring only. It does not replace the public
contractor dataset or claim that a missing grid row proves a license was
cancelled, suspended or revoked.
