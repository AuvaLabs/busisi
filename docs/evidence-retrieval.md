# Private evidence retrieval

Busisi uses document retrieval to find passages in archived budget documents. It does not use retrieval as a source of truth. Structured totals, rankings, comparisons, and review signals still come from validated SQL datasets.

The public Worker does not call a model, does not expose the retrieval database, and does not accept generated SQL. The retrieval index is disposable and can be rebuilt from the verified document catalogue.

## Architecture

```text
Archived source bytes and SHA-256 catalogue
                 |
                 v
      page extraction and page hashes
                 |
                 v
       SQLite FTS5 and BM25 index
                 |
          +------+------+
          |             |
          v             v
  evaluation set   optional vectors
          |             |
          +------+------+
                 |
                 v
       immutable evidence packet
          +------+------+
          |             |
          v             v
 private council   private research editor
          |
          v
 public Q&A readiness report only
```

## What each phase does

1. The tracked document catalogue names each archived file, publisher, source URL, fiscal year, stage, and expected SHA-256. A changed byte fails the build. PDF pages are extracted with `pdftotext`, hashed separately, and split into stable content-addressed passages.
2. SQLite FTS5 ranks passages with BM25. User text is tokenized and quoted before it reaches FTS, and metadata filters use parameterized SQL.
3. The tracked evaluation set contains answerable, synthetic no-match and
   ordinary unsupported questions. It measures top-five document recall,
   empty-result behavior, and citation integrity. Ordinary unsupported
   questions deliberately reuse words found in the budget archive. This
   prevents meaningless strings from making the rejection score look better
   than it is.
4. Precomputed vectors may be imported from a private or local embedding process. Busisi stores the model identifier, dimension, passage hash, and vector. A stale passage hash or dimension mismatch fails closed. No embedding provider or credential is part of this repository. Hybrid ranking uses reciprocal-rank fusion.
5. A council run can receive passages by passing `--retrieval-database`. The harness builds one packet per case before any seat runs. All seats receive the same packet hash and cannot search independently.
6. The research command writes a private editor packet. Every retrieved passage is marked `review_candidate`; retrieval alone cannot make a claim publishable.
7. The readiness command writes a private report. Passing the current checks permits a private pilot only. It does not enable or create a public evidence Q&A endpoint.

## Build and evaluate

The default catalogue uses the nine archived FY2027 documents currently held on the data host.

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_evidence_retrieval.py build
PYTHONPATH=. python3 ops/harness/budget_watchdog_evidence_retrieval.py evaluate
```

The generated database and evaluation report remain under the ignored `data/budget_watchdog/evidence-retrieval/` directory. The weekly scheduled audit rebuilds this database and reruns the evaluation.

The 2026-11-07 evaluation contains 40 cases. All 28 answerable cases retrieve
the expected document, and every returned passage passes its file and passage
hash checks. Six synthetic no-match questions return no passages. All six
ordinary unsupported questions still retrieve related passages because BM25
finds matching words but cannot decide whether those passages answer the
question. The measured unsupported-question rejection score is therefore 50
percent, and the private pilot remains on hold. This is the intended
fail-closed result. An answer-checking layer and a separately reviewed answer
evaluation set are required before any public question-answering release.

Query the private index:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_evidence_retrieval.py query \
  "Health Facilities Enhancement Program" --agency DOH --fiscal-year 2027
```

Prepare a private research packet:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_evidence_retrieval.py research \
  "Where are health facilities funded?" \
  --story-id health-facilities \
  --agency DOH \
  --output data/budget_watchdog/research-editor/evidence/health-facilities.json
```

Run the private council with one fixed retrieval snapshot:

```bash
PYTHONPATH=. python3 ops/harness/budget_watchdog_review_council.py \
  --retrieval-database data/budget_watchdog/evidence-retrieval/evidence-retrieval.sqlite3
```

## Release boundaries

- A passage must carry its document ID, publisher, direct source URL, page number, original file hash, passage hash, and index manifest hash.
- A retrieved passage is supporting context. It does not prove payment, delivery, completion, value, identity, or wrongdoing.
- Missing results mean only that the indexed documents did not return a match.
- Vectors can improve recall but cannot change a source record or structured total.
- Public evidence Q&A remains disabled until a separate public safety and answer-quality release is approved and tested. The current implementation has no public endpoint.
