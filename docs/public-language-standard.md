# Busisi public language standard

Busisi should be understandable to a reader who has never worked with a public
budget, audit report, procurement record, or database. Accuracy is not a reason
to make the first explanation difficult. The plain explanation comes first and
the exact technical detail remains available for readers who need it.

## Page order

When the information is available, answer in this order:

1. What we know
2. What needs checking
3. What this does not prove
4. What to check next
5. Where this information came from

Use short sentences and concrete subjects. Say who published a record, what it
says, when it was published or checked, and what Busisi did with it.

## Question-led research articles

Research articles do not repeat the general page order as a fixed set of
headings. They use this bounded structure:

1. A plain-language question as the headline.
2. `The short answer` in two to four sentences.
3. One to four sections whose headings state the actual findings.
4. A comparison only when the year, definition, unit, and denominator match.
5. `What this does not show`, written specifically for that article.
6. Next checks that name the responsible office and the exact record needed.
7. Expandable method and source details.

Remove sections that have nothing useful to say. Do not add `Why it matters`,
`Findings`, `Analysis`, or `Comparison` as generic body headings. Do not repeat
the same limitation paragraph in every article. Put a figure-specific limit in
the chart caption or beside the sentence it qualifies.

Before publication, confirm that the short answer works by itself, every money
figure names its stage, the definition of need is visible, and no missing value
was estimated. Body headings should differ from the preceding article. Every
next check must name both an office and a record. Remove any sentence that could
be pasted unchanged into an unrelated article.

## Preferred public wording

| Internal term | Public wording |
| --- | --- |
| acquisition | download, document search, or source copy |
| artifact | source file or saved file |
| fingerprint | saved-file check code |
| provenance | where this information came from |
| reconciliation | totals check or records agree |
| quarantine | held back for checking |
| gated release | published only after the checks pass |
| lifecycle | document stages or project stages |
| ledger | list, comparison, or record history |
| snapshot | dated copy or dated records |
| dossier | project evidence page |
| normalized name | cleaned-up name used for comparison |
| deterministic rule | the same written rule for every record |

Official terms may remain when they are the correct legal or source term. Define
them immediately. For example, describe an appropriation as legal authority to
spend, and explain that it is not a release or payment.

## Flags and uncertainty

Every red flag must state:

- what Busisi noticed;
- why a reader may want to check it;
- what the flag does not prove; and
- the next document or source to check.

Use `held back for checking` when records conflict. Never turn a missing record,
unmatched name, unusual amount, or date conflict into a claim of corruption,
waste, a ghost project, or wrongdoing.

## Sources and technical details

Name the original publisher separately from the service used to access the
record. Keep full source-file check codes, rule codes, and internal status names
in a details section, downloadable data, or the API when they do not help an
ordinary reader understand the page.

## Review checklist

Before publishing or changing a page, check:

- headings, navigation, buttons, forms, empty states, errors, and footnotes;
- title, description, social preview, and structured data;
- desktop and mobile rendering with real data;
- every number against its source and nearby explanation;
- whether the page distinguishes a record, a project, a building, and a payment;
- whether any sentence claims more than the cited records support; and
- whether a child or first-time reader could explain the page after one reading.

Run these focused checks while editing:

```bash
node --test cloudflare/busisi/test/prelaunch.test.js
node --test cloudflare/busisi/test/worker.test.js
```

The full release check remains `npm test` from `cloudflare/busisi`.
