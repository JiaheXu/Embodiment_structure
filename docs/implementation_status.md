# Robot literature implementation status

Contract: `docs/robot_literature_system_codex_spec.md`, version 1.1. This is a runnable initial local implementation, not a claim that every production requirement or quality gate has been completed.

## Working implementation

- Package, locked dependencies, CLI, FastAPI API and browser UI; localhost defaults and host/origin write protection.
- Immutable SHA-256 PDF snapshots, duplicate aliases, page-based native parsing in a bounded subprocess, retained generations and checksummed citations.
- SQLite FTS5 retrieval, PostgreSQL lexical/pgvector index adapters, pinned BGE model adapters, reciprocal rank fusion and reranking metadata.
- Durable job uniqueness, leases, heartbeats, fenced publication, bounded retries, terminal run recovery and progress events.
- Closed facet/record/filter schemas; configuration-scoped four-state evaluation; same-record filter conjunctions; unknowns under negation; separate result buckets.
- Validated original evidence, atomic fact publication, conflicting fact retention, append-only corrections and snapshot watermarks.
- Explicit cloud enrichment with separate semantic review, durable call/token reservations across worker retries, source-span allowlists and uncertain-billing logs.
- Scoped protocol comparison with version/metric checks, selected configuration/result IDs, units and unknown context; no cross-protocol leaderboard.
- Versioned projects, separate observed/interpreted/hypothesized experiment records, relevant allowlisted advice context, reviewed published claims and untested proposals.
- Portable relational-plus-artifact backup and restore; restored pending indexing resolves rebased blobs by document ID.
- Evaluation CLI with judged relevance denominators and 25 bilingual unlabeled question templates.

## Execution decisions

- Worked in the supplied checkout and preserved the user's moved specification, source PDFs, summaries and lab scripts. No merge, push or unrelated modifications.
- Tasks 1–7 share immutable document/generation IDs and source references; tasks 4–6 share typed registries; task 8 uses the same evidence resolver. Public API payloads are JSON dictionaries; modules are kept compact rather than adding empty package layers.
- SQLite/native parsing is the verified default because Docker access is unavailable and production models were not downloaded. Its search is lexical, not BGE semantic retrieval; it has no OCR or verified table-cell extraction. Cost if this profile is mistaken for production: weaker retrieval and unresolved scanned/table facts.
- Summaries are unverified navigation objects, never evidence. All 438 summary files are indexed, while PDF ingestion is limited to the required initial pilot.
- Cloud calls are explicit and disabled by default. Downloader credentials are not imported. Conservative byte reservations may stop early; this avoids overspending rather than estimating unknown tokenizer behavior optimistically.
- The pilot selected the first 100 sorted PDF paths. It verifies ingestion and source access, not representative OCR/layout quality. Human annotations, manual scientific review and empirical model results are not fabricated.

## Verification evidence

- Baseline: all 16 existing robotlit tests failed because the package did not exist. These tests subsequently passed.
- Final full repository suite: **73 passed, 1 PostgreSQL integration test explicitly skipped**; one third-party Starlette TestClient deprecation warning. API tests run outside the sandbox because its in-process event loop hangs under sandbox restrictions.
- Fresh independent review identified spending, fencing, terminal-state, privacy, comparison, restore and host-validation bugs. All Important findings were fixed with dedicated regression coverage. No identified Critical findings.
- Additional checks: source/record boundary tests, Docling table/section adapter test against the locked core API, PostgreSQL DDL compilation for all tables, installed CLI, built wheel including the browser UI, Python compilation, and whitespace checks.
- Browser smoke: search request completed, result buckets remained distinct, PDF evidence links rendered, no horizontal overflow in the inspected desktop viewport. Screenshot capture timed out; no screenshot-based visual claim is made.
- Corpus inventory: **3,986 PDF paths**, **45,839,582,726 bytes**. Summary indexing: **438 files**, zero errors.
- Native pilot: **100 source paths → 76 unique documents**, **9,667 blocks**, **10,137 chunks**, **zero failed jobs**. Managed pilot store approximately **1.2 GB**. Original files remain unchanged.
- Evaluation runner processed 25 unlabeled question templates with **zero cloud calls**. No precision/recall/support accuracy score is claimed. See `docs/pilot_report.json` for measured counts/timings.

## Specification task coverage

1. Identity/database/jobs: implemented for the local profile; PostgreSQL DDL and opt-in integration test provided, live server verification pending.
2. Inventory/snapshots/parsing: native profile verified; Docling adapter provided, real OCR/layout/table pilot pending.
3. Retrieval: SQLite and PostgreSQL lexical/index code, BGE adapters and revision guards implemented; live BGE/approximate-vs-exact evaluation pending. Native chunks use words rather than the embedding tokenizer.
4. Facts/gateway/corrections: core facets, scoped record fields, support review and budgets implemented. Full standalone protocol/dataset identities, table-cell locators and persisted per-field review coverage remain incomplete.
5. Planning/coverage: Q1–Q5 local templates, explicit typed plans and resumable snapshot reviews implemented. General cloud query planning and iterative targeted follow-up remain incomplete.
6. Verification/comparison: four-state/configuration/record semantics, support checks and scoped comparison implemented. Full detailed comparison matrices and causal baseline control accounting remain incomplete.
7. CLI/API/UI: local discovery, ingestion, evidence, progress, exports, corrections and memory implemented. Result details expose records as JSON; dedicated rich detail columns are not complete.
8. Projects/experiments/advice: implemented with deferred cloud state and protected context. Saved queries and reading-state/tag workflows are not implemented.
9. Evaluation/pilot/rollout: functional pilot, question templates, judged relevance metrics and local restore tests implemented. Human gold labels, extraction/support metrics, representative 20-page/table review, live provider/model tests and production-quality gates are pending. Corpus-wide production ingestion/enrichment has deliberately not started before those gates.

## Remaining external inputs

- A reachable PostgreSQL 17/pgvector service for opt-in integration and production restore verification.
- Installed production model/parser assets and an empirical representative pilot.
- Configured compatible cloud endpoint/model for optional bounded live smoke calls.
- Human gold labels and expert evidence judgments before scientific accuracy or exhaustive-review claims.

See `docs/runbook.md` for operation and explicit limitations.

## Knowledge Sphere UI addition

User reference implemented as a dark canvas sphere with topic clusters, drag/keyboard rotation, scroll zoom, optional motion, topic filters and shared paper/search results beneath the question input. Includes the full inventory (3,962 visible navigation nodes in the current corpus), summary previews and available immutable PDF links. The separate workspace UI has been removed; `/workspace` redirects to the home page.

Verified: 79 repository tests passed, 1 PostgreSQL test skipped; JavaScript syntax and package asset checks passed. Browser checks covered rendered desktop UI, mobile overflow, topic visibility/reset, rotation, paper/topic selection and live search results. Desktop screenshot inspected at `/tmp/robotlit-sphere-desktop.png`. Fresh review findings for unavailable roots, changed source versions, responsive paper navigation, same-title highlights and early-search races were addressed. Topic clusters remain explicitly unverified local term groupings.

## Collection categories and main-page indexing

Expanded the local topic vocabulary to 31 categories plus Other papers. On the
same 3,962-node inventory snapshot, Other dropped from 1,835 to 378; title matches
take priority over summary boilerplate. These remain unverified navigation hints.
The main-page Rebuild RAG button loads every configured source root with no limit,
shows worker progress and reconnects to saved runs after refresh. Successful
indexes are reused; failed indexes are retried. Status polling reads index jobs
in one batch. Missing roots and runs remain visible as failures. No full corpus
rebuild was started while testing the button; UI requests were mocked and backend
regressions used temporary PDFs and databases.

Validation for this update: 122 tests passed, 1 PostgreSQL test skipped. Browser
mocks verified unlimited ingestion requests, all-root submission despite a missing
root, preserved monitoring after a missing saved run, reconnection without duplicate
submission, and the legacy workspace redirect. The live inventory contains 32
navigation groups and 378 Other papers.

## Canonical paper titles and refreshed RAG state

Paper keys now use only the normalized paper title. Video captions are replaced
with matching academic manifest titles or PDF page-one title text; filename
fallbacks omit the leading year. Title provenance prevents duplicate filename
aliases from replacing trusted titles. Re-ingestion also corrects existing chunk
titles and search vectors while retaining PDF/document/evidence identities.
Completed ingestion refreshes the saved title catalog; queries use live database
indexes and the GUI refreshes selected results or reruns the visible query.
Catalog publication failures are reported and retried without stopping workers.

Validation: 129 tests passed, 1 PostgreSQL test skipped. Title extraction was
checked against real RT-2, Risk-Aware Locomotion, and Affordance Diffusion PDFs.
All 3,986 source paths were inventoried without corpus ingestion; the Affordance
Diffusion aliases share the requested title-only key. Full ingestion remains a
user-triggered main-page operation.
