# Robot literature system

The runnable local profile ingests native PDF text, indexes summaries for discovery, and searches SQLite FTS5. It preserves PDF snapshots, physical page references, scoped facts, correction history, and resumable jobs. The optional production profile selects PostgreSQL/pgvector, Docling, and pinned BGE embedding/reranking models. Production-model execution and human evidence evaluation have not been validated in this session.

## Start the local application

Run these commands from the repository root:

```bash
UV_PROJECT_ENVIRONMENT=.venv-robotlit uv sync --locked --extra test
source .venv-robotlit/bin/activate
robotlit serve --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Start the worker in a second terminal:

```bash
source .venv-robotlit/bin/activate
robotlit worker
```

The API queues search and ingestion jobs. The worker must remain running for browser requests to finish. CLI search runs directly and does not need the worker. Cloud calls are disabled by default. The service is personal and binds only to localhost; remote authentication is not implemented.

## Inspect and ingest

```bash
robotlit inventory --source-root papers --dry-run > /tmp/inventory.json
robotlit index-summaries --source-root papers
robotlit ingest --source-root papers --limit 100 --wait
robotlit status --run-id RUN_ID
robotlit status --job-id JOB_ID
```

`inventory` never changes source files. `ingest` copies PDF content into `data/robotlit/blobs`, keyed by SHA-256, and checks the immutable copy before parsing. Exact duplicates share one snapshot. A changed file produces a separate document; previous citations and generations remain available. Titles alone never merge different PDFs. Lab manifests supply titles and years when available. The existing lab downloader and summarizer remain usable independently.

The main page's **Rebuild RAG** button submits every configured source root without
a file limit; the default `papers` root covers all PDFs recursively under `labs/`.
Progress survives page refresh in the same browser. Unchanged successful indexes
are reused, and failed indexes are retried. Submission and parsing failures remain
visible. CLI `--limit` remains available for pilots. The worker must remain running
to finish indexing. Opening the GUI alone does not start full ingestion.

The native parser requires `pdftotext` (Poppler). Its output has physical page numbers and source offsets but no OCR, layout bounding boxes, or structured table guarantees. Sparse/empty pages require review. Parser subprocesses have a timeout and address-space limit. Failed documents remain visible and do not stop other papers. Published generations remain searchable when later processing fails.

Do not delete blobs or cited generations to reclaim space. Back up before explicit retention work. Copying a full collection can require approximately its original byte size again; the pilot store is about 1.2 GB.

## Search and inspect evidence

```bash
robotlit search "Find bimanual dexterous VLA papers"
robotlit search "Find multi-view camera policy inputs" --format markdown
robotlit search --plan config/q5.json
robotlit review-collection --plan config/q5.json --max-documents 50 \
  --max-cloud-calls 0 --max-input-tokens 0 --max-output-tokens 0
robotlit search --resume-token RUN_ID
```

Local templates visibly interpret the five specified query families, including basic Chinese formulations. Other wording uses unverified discovery; use an explicit plan for technical filters outside those templates. The JSON plan schema rejects unregistered facets/record paths and invalid operators. Numeric filters require compatible evidence units.

All hard predicates must be satisfied by one method configuration. All filters in a record group must be satisfied by one record. Missing information stays unknown, including desired `false` values. A summary hit is unresolved and cannot create a confirmed result. Similarity and reranker scores express relevance, never factual confidence.

Collection review fixes the document/generation set and fact-revision watermark. Resuming uses its original budgets and snapshot; newly added papers and later corrections belong to a new run. A fully paged local review still does not mean every configuration received semantic review. Coverage and extraction readiness are separate.

In the browser, expand source evidence to see the exact quote and open its immutable PDF at the physical page. JSON and Markdown exports retain source IDs, configuration judgments, scientific records, missingness, comparison conditions, and coverage.

## Optional cloud enrichment

Copy `config/example.yaml` to the ignored `config/robotlit.yaml`. Set `cloud_enabled: true`, `llm_base_url` to your compatible provider/proxy endpoint and `llm_model` to its model ID. If authentication is required, export `ROBOTLIT_LLM_API_KEY`; never put the key in YAML or browser code. The existing lab script's credentials are not automatically imported.

```bash
robotlit enrich --document-id DOCUMENT_ID --max-cloud-calls 2 \
  --max-input-tokens 60000 --max-output-tokens 8000
robotlit worker --once
robotlit status --job-id JOB_ID
```

Enrichment selects at most 16 PDF source blocks and 12,000 UTF-8 bytes, performs extraction and independent support review, validates every locator against the uploaded span, then publishes transactionally under the job lease. This initial selection is deliberately bounded; it does not guarantee the method, setup, and appendix have all been inspected. Unreviewed fields remain unknown. Native table text is not a verified structured numeric table.

The gateway reserves calls and conservative byte-based token bounds before provider requests. Worker reservations and uncertain billed attempts are durable across retries. Actual provider token counts are retained when returned. A lease loss prevents further cloud calls and fact publication. Prompt evidence carries no tools, SQL, filesystem permissions, or authority to alter query filters. Web search is absent.

The compatible HTTP adapter uses `/chat/completions` with JSON output. Provider compatibility, context limits, and live semantic quality require a configured smoke test; no paid calls were made during implementation. The specification's broad P0/P1/P2 extraction routing and targeted follow-up strategy are not yet fully implemented. Enable cloud only after checking this bounded workflow against representative papers.

Manual grounded facts can be published through `robotlit publish-facts --batch batch.json` or `POST /v1/facts`. A supported assertion requires a method identity and source evidence. The caller is responsible for semantic review; valid source IDs alone do not establish support. Browser corrections require a reason and retain prior revisions. Structured fields have the equivalent append-only correction endpoint.

## Projects and experiments

Create a project through the browser or `robotlit project --profile profile.json`. Update using `--project-id ID --expected-version N`; conflicting versions are rejected. Record experiments through the browser or `robotlit experiment --record experiment.json`. Keep `observations`, `interpretation`, and `hypothesis` separate, and include `project_id` and `project_version`.

```bash
robotlit advise --project PROJECT_ID "How should I address camera occlusion?"
```

Advice is deferred without cloud configuration. Enabled advice selects relevant experiment text from the same project, excludes local attachments and paths, and supplies bounded PDF evidence. Published claims require source validation and semantic review. Proposed experiments remain explicitly untested. No training, repository cloning, or robot actions are executed.

## Production adapters

```bash
export ROBOTLIT_DB_PASSWORD='YOUR_LOCAL_PASSWORD'
docker compose up -d db
export ROBOTLIT_DATABASE_URL='postgresql+psycopg://robotlit:YOUR_LOCAL_PASSWORD@127.0.0.1:5433/robotlit'
UV_PROJECT_ENVIRONMENT=.venv-robotlit uv sync --locked --extra test --extra models
export ROBOTLIT_CONFIG=config/production.example.yaml
alembic upgrade head
robotlit ingest --source-root papers --limit 100 --wait
```

Use your own password and keep it out of shell history/configuration committed to Git. `compose.yaml` pins PostgreSQL 17/pgvector 0.8.1 and binds its port to loopback. Database initialization and Alembic create lexical GIN and vector HNSW indexes. Resolve PostgreSQL access before using this profile; Docker was inaccessible during implementation.

`config/model_revisions.json` records immutable public model revisions. The production example uses these revisions. A query cannot silently search vectors produced by another revision; re-ingest into a new generation when changing models. CPU is the default; set `device` to an available accelerator explicitly. Model weights and parser assets are downloaded on first production use and are not committed.

Docling exports its full document artifact, structured table data, captions, section paths, and normalized top-left bounding boxes. Its adapter was checked against the locked core API and a synthetic adapter test; actual Docling/OCR conversion still needs validation. BGE adapters and PostgreSQL vector queries are present, but no live model throughput, exact-vs-HNSW recall, or semantic retrieval quality was measured here.

The structured-record registry supports scoped input/output, dataset, result, method-detail and artifact fields. It is narrower than the complete detailed schemas in specification 1.1: standalone protocol and dataset identities, table-cell locator verification, full review coverage, source supplements, personal saved queries/reading state and richer comparison matrices remain follow-up work. Unknown scientific fields must not be guessed to fill these gaps.

## Backup and restore

```bash
robotlit backup --directory /absolute/path/to/new-backup
# Use a new data_dir and empty database in restore.yaml.
robotlit --config restore.yaml restore --directory /absolute/path/to/new-backup
```

Backups contain the relational rows and referenced blobs/parse artifacts with checksums. Restore rejects unsafe paths, checksums and nonempty targets, retains source IDs, and rebases managed paths. Restored pending jobs resolve their blob by document ID. Backups hold database write locks while copying; stop ordinary work for a large backup. The SQLite citation and pending-ingestion restore paths are tested. PostgreSQL restore remains unverified.

## Validation and measured pilot

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-robotlit/bin/python -m pytest tests -q
robotlit evaluate --dataset evals/questions.jsonl --output evals/native-pilot.report.json
```

The PostgreSQL integration test is opt-in: set `ROBOTLIT_TEST_DATABASE_URL` to a dedicated local test database and run `pytest tests/robotlit/test_postgres.py`. It checks the specified server/extension versions and creates/removes an isolated test schema. Without that setting it is explicitly skipped, not counted as production verification.

The 25 bilingual questions in `evals/questions.jsonl` are **unlabeled templates**, with tuning/held-out assignments. They are not human gold data. Add `relevance` judgments keyed by immutable document IDs to create a genuine gold dataset. Recall@50 and Precision@10 include only judged documents and show denominators. Citation support, predicate violations and numeric extraction metrics remain unavailable until their human labels exist; null is not a passing score.

Pilot: the first 100 sorted PDF paths produced 76 byte-distinct documents, 9,667 source blocks, and 10,137 chunks with zero failed jobs. All 438 available summary files were indexed separately. The inventory contained 3,986 PDF paths totaling 45,839,582,726 bytes. This was a native parsing/functional pilot, not a representative OCR/table or retrieval-quality benchmark. No claims were promoted from summaries and no cloud calls were made.

Before corpus-wide production ingestion, label representative papers, inspect at least 20 difficult pages/tables, run the specified model baselines, measure retrieval/support/extraction accuracy, and test PostgreSQL backup recovery. The specification's quality gates have not been passed. Do not interpret the functional test count or zero parser failures as scientific accuracy.

## Knowledge Sphere UI

The home page and `/sphere` provide a dark, rotating paper sphere. Drag or use arrow keys to rotate, scroll or press +/− to zoom, and click a paper or topic to populate the results below the question input. Topic checkboxes control graph visibility. Search uses the existing research API and highlights candidate nodes while retaining confirmed/partial/unresolved distinctions in the result cards.

The collection browser is a sidebar on wide screens and a collapsible panel on narrower screens; it provides keyboard-accessible paper selection and title filtering. Indexing runs from the main page. The former `/workspace` URL redirects to `/`; project and experiment operations remain available through the API and CLI.

The graph includes indexed snapshots, summary records and local PDF inventory metadata, including papers not yet ingested. Known exact aliases share a node. Changed sources appear as pending ingestion alongside the retained snapshot. Unindexed nodes cannot supply PDF evidence until ingested. Unavailable source roots produce a warning while retained papers remain accessible.

Clusters use deterministic local title/summary topic terms. They are navigation hints, not semantic capability judgments or learned embedding clusters. No frontend framework, CDN, external graph service or cloud call is needed to draw the sphere.

## Paper names and index refresh

Paper keys are normalized from the paper title alone, for example
`affordance-diffusion-synthesizing-hand-object-interactions`. They exclude the
year, lab, video caption and URL. Academic manifest titles are preferred; video
records use a matching academic PDF URL or title text extracted from PDF page
one. If that extraction fails, the filename without its year prefix is the
fallback. Duplicate filename aliases cannot replace trusted paper titles.

Re-ingestion corrects existing paper and chunk titles without replacing PDF
identities or evidence blocks. Content checksums still protect PDF versions;
papers with identical titles do not merge their source evidence. Completed
ingestion refreshes `data/robotlit/catalog.json`, including title keys and active
generations. Search reads the current database for every new query, so no server
restart is needed after indexing. The main page reloads its graph and reruns the
visible query or refreshes selected papers. Catalog write errors are reported
without stopping the worker; later status polling retries publication.
