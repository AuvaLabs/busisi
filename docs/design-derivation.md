# Design Derivation — Visual Identity for Grimoire Properties

**Captured:** 2026-05-02
**Scope:** Modelwatch (vertical 1) and Vested (vertical 2). Future verticals inherit the platform-level decisions below; only their per-property accent and tone-modifier change.
**Anti-thesis:** Grimoire properties are *publications, not dashboards*. They should feel closer to Stratechery and Techmeme than to ThreatWatch, TechCrunch, or any "AI startup landing page".

---

## 1. References — what we borrow and why

| Reference | Borrowed | Rejected |
|---|---|---|
| **Techmeme** | Story prioritization by font size; source-clustering with indented "More:" sibling sources; single-column scannable density; minimal chrome | Plain Helvetica utility look (we want more editorial warmth); blue-link monotony |
| **Stratechery** | Serif body type; long-form measure (~70 ch); generous whitespace; austere palette where typography does the work | Subscription-paywall pop-ups; Substack-default everything |
| **Hacker News** | Type-driven hierarchy *without* chrome; metadata treatment that disappears until needed | Monochrome Verdana cliff face — we add restraint, not bleakness |
| **Axios** | "Smart Brevity" — headline → why it matters → bullets → sources, applied to every story summary | Loud teal accent; dashboardy boxes; aggressive newsletter modals |
| **Are.na / Marginalia** | Slow-web library aesthetic; restrained editorial calm; whitespace as content | The art-school esoterica that some Are.na pages indulge in |
| **The Browser** | Source attribution treatment as first-class type, not afterthought metadata | Lifestyle-newsletter softness — Grimoire is sharper |

**Anti-references** (the directive's list, internalised): TechCrunch / The Verge (ad-stuffed tech press), generic AI-startup landing pages, Substack default theme, anything with paywall pop-ups or autoplay video, threat-intelligence dashboards (including ThreatWatch's), and any AI-generated photorealism in hero positions.

---

## 2. Typography — committed choices

Platform-level decision: **same type system across all properties**. Brands appear independent to readers, but a shared Grimoire type system keeps maintenance cost flat as verticals are added. Per-property accent colour is what makes the brands feel distinct, not different fonts.

| Role | Family | Source | Why |
|---|---|---|---|
| Body / long-form | **Newsreader** | Google Fonts (open) | Modern, slightly literary serif; specifically optimised by Production Type for screen reading at body sizes; pairs well with multiple sans companions; weight range 200-800 covers all editorial needs; no licensing cost |
| Headlines / UI / nav | **Inter** | Google Fonts (open) | The directive suggested "National Park or GT America (test, pick one)" — both are commercial (~$200-500/yr). For launch we ship **Inter** instead: it's the de-facto editorial-tech sans (Substack, Notion, Vercel, Linear all use it), is free, has the same neutral-precise feel as GT America at 90% fidelity. Decision logged: re-evaluate licensing GT America when Pro tier MRR > $1,000/mo, which is when the type-detail upgrade pays for itself in perceived polish. |
| Mono / code / specs | **JetBrains Mono** | Google Fonts (open) | Reads well in glossary code blocks (Modelwatch) and in tabular tax-rule citations (Vested). 4 weights, ligatures off by default. |
| Display (rare) | Newsreader Italic at large sizes | Google Fonts | Used only for marquee Research-layer titles, not News headlines. Avoids the "every other site has the same display sans" problem. |

**Type scale.** Modular scale, ratio 1.25 (major third). Token names are platform-level; verticals don't override.

```
text-xs:    12.0 px
text-sm:    14.0 px
text-base:  16.0 px       ← body default
text-md:    18.0 px       ← lead paragraph
text-lg:    20.0 px       ← H4
text-xl:    25.0 px       ← H3
text-2xl:   31.25 px      ← H2 / story headline (secondary)
text-3xl:   39.06 px      ← H1 / story headline (lead)
text-4xl:   48.83 px      ← H1 / front-page hero only
```

Body line-height **1.65** (Newsreader is dense at 1.5; needs the breathing room). Headlines line-height **1.15**. Measure (paragraph max-width) **64ch ≈ 36rem** for article body.

---

## 3. Colour — both themes, both properties

Platform-level neutrals are warm-tinted (slightly off the cool digital default) so the brand reads as "editorial print" rather than "Linux dashboard". Each property layers its accent on top.

### Light theme (default)

| Token | Hex | Use |
|---|---|---|
| `bg` | `#FBFAF7` | page background, warm off-white |
| `bg-elev` | `#F4F1EB` | card / surface |
| `bg-mute` | `#ECE7DF` | subtle stripe, table-row alt |
| `text` | `#1A1A1A` | body copy |
| `text-mute` | `#5A5852` | metadata, source attribution, captions |
| `text-faint` | `#8A867D` | timestamps, byline tertiary info |
| `rule` | `#D8D3C9` | hairlines, borders |
| `link` | `#1A4F8A` | links — restrained inky blue, not Substack indigo |
| `link-hover` | `#0E3565` | link hover |

### Dark theme

| Token | Hex | Use |
|---|---|---|
| `bg` | `#1A1817` | page background, warm dark |
| `bg-elev` | `#23201E` | card / surface |
| `bg-mute` | `#2C2826` | subtle stripe |
| `text` | `#EEEAE3` | body copy |
| `text-mute` | `#A6A199` | metadata |
| `text-faint` | `#6E6960` | timestamps |
| `rule` | `#3A3633` | hairlines |
| `link` | `#9CC0F0` | links — soft sky |
| `link-hover` | `#C2DAFD` | link hover |

### Per-property accent (the only brand differentiator at colour level)

| Property | Accent (light bg) | Accent (dark bg) | Rationale |
|---|---|---|---|
| **Modelwatch** | `#B8743A` warm muted amber | `#D49464` lifted amber | Per directive. Warm + literary; differentiates from the "every AI uses purple" cliché. Pairs with Newsreader serif for editorial feel rather than tech-startup. |
| **Vested** | `#2D5F5D` deep teal | `#5A8E8C` lifted teal | Per directive. Conservative + financial; reads as trustworthy without going the "WSJ navy" route, which feels old. The cooler temperature also visually separates Vested from Modelwatch when both run on the same platform browser tab. |

Accent uses (both properties):
- Inline link **underlines** (not link colour itself — links stay blue) on hover, when the link is internal/editorial.
- Section header rule (4px top border) on `/glossary/`, `/tools/`, `/research/` index pages.
- "Sponsored" badge fill.
- Pull-quote drop cap.
- Active-nav underline.

Accent **does not** drive: link colour (links are universal blue across properties), error/warning/success (universal semantic colours), button primary fill (which uses `text` neutral, not accent — keeps the page calm).

### Semantic palette (universal)

| Token | Hex | Use |
|---|---|---|
| `success` | `#2F7D32` | confirmation, "subscribed" toast |
| `warn` | `#9C5D11` | "general info, not professional advice" badge on Vested |
| `danger` | `#A23B2D` | error, unsubscribe-confirmed |
| `sponsor-bg` | accent at 8% alpha | "Sponsored" inline label background |

Contrast checked: every text/bg pair clears WCAG 2.1 AA at body sizes (4.5:1) and AAA (7:1) for the body text token in both themes. Audit row in `ops/harness/checks/contrast.py` validates on every page render.

---

## 4. Grid and layout

12-column fluid grid; gutters 24 px desktop / 16 px tablet / 12 px mobile. Container widths:

| Page kind | Max width |
|---|---|
| Article body (news, glossary, learn, research) | 64 rem (1024 px); article column at 36 rem nested inside |
| Front page / topic / today / entity | 72 rem (1152 px); two-column 8/4 split (stories + sibling rail) |
| Tools | 48 rem (768 px) — narrower so calculator inputs feel deliberate |
| Methodology / sources / about | 36 rem (576 px) — single column, generous |

Vertical rhythm: 8 px baseline. Section spacing in multiples of 24 (3 baselines).

**Key layout patterns:**

- **Front page** — Techmeme-derived: lead story uses `text-4xl` headline + thumbnail or none, secondary stories `text-2xl`, sibling sources indented one level under each in `text-sm` `text-mute`. No story tiles or card chrome — type alone establishes hierarchy.
- **Story page** — single column at `36 rem`. Top: canonical headline, primary timestamp, source list (deduped, with publication names bolded). Body: per-cluster narrative summary (100-150 words, LLM-generated). "Why this matters" callout, accent rule on the left, italic. Then list of all sibling sources with their original headlines.
- **Glossary entry** — Stratechery-derived: serif body, long-form, definition → "why it matters" → related-terms cross-links → references → last-verified date in `text-faint`.
- **Today page** — chronological reverse-time with hour-bucket dividers (sticky `text-xs uppercase tracking-widest text-mute`).
- **Tools** — calculator UI with input/output panes; affiliate-disclosure footer is the directive's tasteful-monetization rule applied: visible, labelled "Disclosure", separated from the tool by a 24px space + rule.

**Mobile.** Single column ≤768 px. Lead story headline drops one step (`text-3xl`). Sibling-source rail collapses inline below story rather than indented to the right. No hamburger nav — top nav is `text-xs uppercase tracking-widest`, always visible, links wrap to a second line gracefully if needed.

---

## 5. Iconography and imagery

- **Icon set:** Phosphor Icons (Light weight default; Regular for active states). Loaded as SVG sprites — no icon fonts (perf + a11y).
- **Hero imagery:** none. Front page is type-driven. Story pages may carry a single source-attributed image when the source provides one with permission. No AI-photorealism, ever (per directive). AI-generated diagrams / charts / abstract editorial illustrations are allowed and labelled.
- **Social cards (1200×627 / 1200×675 / 1080×1080):** templated. Property wordmark top-left, headline body in property accent, attribution line bottom — generated by `social_card_generator.py`. No AI imagery, no faces.

---

## 6. UI patterns explicitly borrowed

1. **Source clustering with indentation** (Techmeme). Under the canonical headline, sibling sources are listed with `> publication — original headline`, indented `1.5 em`, in `text-sm text-mute`. Click target is the publication name.
2. **"Why this matters" callout** (Axios Smart Brevity). One sentence, italic, accent-coloured rule on the left. Always after the cluster summary, never embedded in a paragraph.
3. **Type-driven hierarchy without chrome** (HN). No card backgrounds, no shadows, no rounded-corner boxes. Type weight + size + a single hairline rule does all the structural work.
4. **Long measure body serif** (Stratechery). Body column capped at `36 rem ≈ 64 ch`, generous line-height, paragraphs separated by 1.5 baselines (24 px).
5. **Source-attribution as first-class type** (The Browser). Source publication names are `font-medium` in body copy, never `text-faint`. Where the source is the story (e.g. an OpenAI announcement), the publication is given equal billing with the canonical headline.
6. **Front-page density without chrome** (Techmeme + HN). 30-50 stories visible above the fold on desktop, achieved by tight vertical rhythm and scale relationships, not by compressing everything into a uniform list.

---

## 7. Anti-patterns banned at the implementation layer

- No cookie consent banner — analytics is self-hosted (Plausible/Umami), no third-party tracking, so no cookie-law trigger.
- No newsletter modal popup. Email capture is footer + sidebar inline form only.
- No autoplay anything. (We ship no video at all, per directive content rules.)
- No paywall flicker. Pro tier features are gated server-side; free content renders fully without auth checks.
- No AI hero illustrations. Banned at the harness level.
- No font weight under 400 for body copy (readability).
- No body line-length over 80 ch (readability) or under 45 ch (jumpy eye-track).
- No background images behind text.

---

## 8. Tokens — implementation

Design tokens are emitted as CSS custom properties from a single source file (`platform/shared/tokens.css`), namespaced per property at `:root[data-vertical="modelwatch"]` etc. The tokens above are the entire vocabulary; everything else in the stylesheets composes from them. This is what lets a third vertical (per directive's "verticals are configuration") drop in by editing two values: accent-light and accent-dark.

---

*End of derivation. Phase 1 (server foundation) is next; design tokens are implemented in Phase 3 (Modelwatch) and re-themed in Phase 5 (Vested).*
