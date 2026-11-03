# FY2027 budget publication trail

Date: 2026-11-03

## Published scope

Busisi records five items observed in the Senate Budget Transparency Portal's
FY2027 catalogue:

- four volumes of House Bill 10858 as approved on third reading by the House
  of Representatives;
- one SEPO note assessing the proposed FY2027 budget's macroeconomic and fiscal
  assumptions.

The portal publisher does not determine the legislative stage. The four House
bill volumes remain classified as `house_gab`. The SEPO note is classified as
`supporting`. No FY2027 Senate committee report, Senate amendment, bicameral
report, or enacted General Appropriations Act was present in the acquired
catalogue evidence.

## Acquisition boundary

The Senate portal returned a Cloudflare challenge to the ordinary server-side
acquisition worker. A disclosed secondary renderer was used only to discover
catalogue titles and record identifiers. Its rendered response is not treated
as an official document artifact.

Two BetterGov mirror copies already retained by the FY2027 House comparison
pipeline identify the Senate portal as their source. Their local bytes were
rechecked against these fingerprints:

- Volume I-B: `4cc0f17e472d1af380ea6d3972561f6bb241137826fd85ed7e7e70bcd92986b9`
- Volume I-C: `48cb7a11e391bd4da89d4f47cf39a2eba8fe9bfe636dba101c8284b224ac1b1b`

Volumes I-A and II, and the SEPO note, remain catalogue records only because
their document bytes were not acquired. The public interface does not link a
reader to raw API JSON. It opens the human-readable Senate publication index
and offers an archived document copy only when one has passed its fingerprint
check.

## Reconciliation controls

- Catalogue records: 5
- House-stage document records: 4
- Supporting records: 1
- Archived copies verified: 2
- Catalogue-only records: 3
- Unavailable legislative stages: Senate committee, Senate amendment,
  bicameral, and enacted GAA
- Catalogue SHA-256:
  `7fb461156cba8bd04b48315b298fb2b908506b6a2bb6e3df656d179ad59608ff`

Missing evidence is represented as unavailable, never as a zero amount and
never as an inferred stage.
