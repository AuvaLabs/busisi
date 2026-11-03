# Reviewed project-image evidence snapshot

## Scope

The first bounded release checks the six Busisi project dossiers against both
BetterGov DPWH project-detail and project-image endpoints. It archives the
metadata response bytes and the original JPEG bytes on the official DPWH media
origin. This is a reviewed evidence slice, not full-universe image coverage.

## Reconciliation

| Contract | Detail summary | Image endpoint | Publication state |
|---|---:|---:|---|
| 22HI0028 | 2 | 7 | Count conflict, 7 images quarantined |
| 23DB0126 | 2 | 2 | Exact, 2 images verified |
| 24HI0131 | 1 | 1 | Exact, 1 image verified |
| 24HI0148 | 2 | 2 | Exact, 2 images verified |
| 25HI0028 | 2 | 6 | Count conflict, 6 images quarantined |
| 26HI0094 | 0 | 0 | Explicit no-image state |

The release therefore archives 18 images, publishes 5, and quarantines 13.
The SQL bundle SHA-256 is
`52e612aacdac0fa30c7bde9356387a2037027c0b1aa8ce39ff37635246bd2e6c`.
The generated bundle manifest SHA-256 is
`ef2a9eb613db837e3f8c91a19b3962a4c2bc4b5fee3d252bcb44e8811898d478`.

## Evidence boundary

An image is evidence that the acquired source served those bytes with the
recorded metadata. It does not independently prove capture time, exact
location, physical completion, construction quality, payment, or public
benefit. Source timestamps do not state a timezone. Coordinates pass only a
broad Philippine-bounds validation and remain source-reported.

The other 36,742 image-positive contracts in the current 56,887-contract
delivery universe remain outside this bounded release. They require a resumable
acquisition queue and the same archive, reconciliation, inspection, quarantine,
and publication controls before public display.
