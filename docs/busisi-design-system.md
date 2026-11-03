# Busisi product and design system

## Working identity

**Busisi** is the working identity for the Philippine public-budget watchdog.
The Filipino word communicates close, careful examination. The public promise
is simple: inspect the record, preserve its limits and show the evidence.

The working line is:

> Suriin ang pondo. Sundan ang proyekto.

The English descriptor is **Philippine public budget records**. It explains the
product without turning the wordmark into a generic dashboard title.

The `busisi.org` domain serves the read-only public explorer. Formal trademark
clearance remains a prerequisite for promoting the brand beyond this
controlled release.

## Product voice

Busisi writes like a careful public-records desk:

- State what the source establishes.
- Separate facts, derived links and unresolved candidates.
- Use exact amounts and fiscal years.
- Call a signal a review lead, never proof of wrongdoing.
- Prefer a short limitation beside the claim over a distant disclaimer.
- Use Filipino language where it improves recognition, not as decoration.

Avoid sensational labels, corruption scores, accusation leaderboards and
machine-generated narrative filler.

## Visual identity

The Busisi mark is a compact stack of public records connected by one
evidence path and a verification point. The wider visual language resembles a
civic records desk: structured lines, archival paper, source paths and explicit
review states. The visual system uses:

- deep ledger green for navigation, actions and evidence structure;
- white reading surfaces with restrained gray-green dividers;
- vermilion for review signals and editorial section labels;
- amber only for quarantined or unresolved records;
- one sans-serif family for headings, navigation, controls and explanations;
- monospace figures for identifiers and money.

The interface uses self-hosted Source Sans 3 throughout. Local WOFF2 files
prevent a runtime dependency on an external font service. The base body size is
16 px with a 1.6 line height. Interface labels do not fall below 13 px. Headings
use a bounded responsive scale so hierarchy remains clear without pushing
supporting context outside the viewport.

The system deliberately avoids gradients, glass effects, floating rounded
cards, decorative illustrations, excessive shadows and chat-style interface
patterns. Dense information should look like a maintained register, not a
generated marketing page.

The overview uses code-native SVG and CSS motion to explain how evidence moves
from an official source to reviewed publication. Motion is supplemental,
disabled by the reduced-motion preference and never required to understand the
diagram. This keeps the public surface fast and avoids a video or client-side
animation runtime.

Primary navigation exposes the explorer, review signals, mission and
methodology directly. The methodology page adds a local table of contents for
the pipeline, source policy, release standard and corrections. Mobile
navigation retains clear targets and does not require a menu script.

## Public-budget interface reference

The visual review used the official USAspending public interface as a service
design reference, not as a brand template. The useful transferable patterns are:

- a short public-status strip above the main navigation;
- a clear, consistent sans-serif interface;
- strong page bands that separate exploration, explanation and disclosures;
- large, explicit entry panels for different ways of navigating spending;
- source and methodology links placed beside the data workflow.

Busisi translates the USAspending entry choices into Philippine budget
concepts: appropriation, implementing agency and continuity across budget
years. Official source records remain separate from candidate relationships so
the interface does not imply that an automated similarity is a reviewed fact.

## Static brand assets

- `public/assets/busisi-mark-v2.svg` is the transparent compact navigation and
  favicon mark. The production SVG removes raster edge noise at every size.
- `public/assets/busisi-masthead.webp` is the wide Philippine public-record
  illustration used in the masthead and social sharing metadata.
- Both files are local, immutable static assets with descriptive alternative
  text where the image contributes meaning.
- The masthead is 59 KB after WebP optimization and the SVG mark is under 1 KB.

## Data interaction contract

Every collection view must provide:

1. Search over names, identifiers and locations.
2. Explicit filters with a visible result count.
3. Deterministic sorting with a stated default.
4. Filter state encoded in the URL.
5. A clear reset action.
6. Export of the visible result set.
7. A useful empty state.
8. A mobile layout with no horizontal scrolling.
9. Direct links to evidence dossiers.
10. Quarantine states that cannot be mistaken for confirmed links.

Project dossiers must keep source text, calculated comparisons, confidence,
limitations and source links together. A reader should not need to trust a
summary without being able to inspect the record underneath it.

## Scale boundary

The production register does not embed the full canonical corpus into one HTML
page. Collection pages use indexed server-side search and cursor pagination.
The browser receives only the requested page plus aggregate counts. Reviewed
project dossiers are rendered from the isolated publication database.

The local implementation now materializes reviewed records into a separate
SQLite publication database with an FTS5 search index. Its read-only API uses
opaque keyset cursors and enforces the same filter and sort vocabulary as the
browser. The canonical ingestion store is never queried directly by a public
route.

The Cloudflare adapter preserves this contract in a Worker backed by D1. The
explorer loads only the requested page when the API responds. Browser code
creates result elements through DOM APIs and does not inject response HTML.
The reviewed register retains a server-generated CSV endpoint.

## Accessibility and authenticity

- Use semantic headings, landmarks, labels and native form controls.
- Maintain visible keyboard focus and reduced-motion support.
- Use white page backgrounds and text colors that meet WCAG AA contrast.
- Preserve a minimum 13 px label size and 16 px body size at all breakpoints.
- Prevent horizontal page overflow at desktop and mobile widths.
- Never communicate confidence or quarantine through color alone.
- Keep exact source terminology where paraphrase could change meaning.
- Display the dataset boundary and review status beside public records.
- Preserve an editorial correction path once the site becomes public.
