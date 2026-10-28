# Prepare the robotics collection for LLM Wiki

`prepare_llmwiki.py` uses the Python standard library and the existing
`pdftotext` command (Poppler, also used by the summary pipeline). It reads `labs/`
and copies structured sources into `~/research`; it never writes to `labs/`,
changes the existing `wiki/`, or edits LLM Wiki's SQLite database.

## Run

From `~/Embodiment_structure`:

```bash
# Inspect the complete plan without writing anything.
python3 prepare_llmwiki.py --dry-run

# Import every collection, including papers without summaries.
python3 prepare_llmwiki.py

# Export only PDFs or only Markdown.
python3 prepare_llmwiki.py --pdf_only
python3 prepare_llmwiki.py --md_only

# Repeat after downloading papers or generating/updating summaries.
python3 prepare_llmwiki.py
```

The flags `--pdf_only` and `--md_only` are mutually exclusive; omit both to
export both types. PDF-only mode also skips the Markdown catalog and collection
pages. Both modes retain the hidden JSON import state. Existing files of the
excluded type are left untouched, and switching modes preserves importer
ownership for later updates. Source validation and deduplication still run in
either mode, including unreadable-PDF checks.

Preview a single collection in a separate destination:

```bash
python3 prepare_llmwiki.py --lab ETHZ-RSL --destination /tmp/robotics-preview
```

`--labs-root` and `--destination` override the input and output roots. Do not
run multiple importers concurrently. Text files are imported from verified
snapshots: summaries changed after being read are picked up on the next run,
with a warning in the current report. A PDF changed during import stops the run
before output writes. Unchanged input checksums are reused only when size,
modification time, and change time all match the previous import.

## Output

```text
~/research/
  sources/
    catalog.md
    collections/<collection>-<stable-hash>.md
    papers/2025-cvpr-26-physx-anything-3d/
      2025-cvpr-26-physx-anything-3d.md
      2025-cvpr-26-physx-anything-3d.pdf
      summaries/<hash>/<original-name>.md  # distinct alternate accounts
      versions/<hash>/<original-name>.pdf  # distinct PDF bytes
  .llmwiki-import/
    catalog.json
  wiki/                            # existing Codex-maintained pages, untouched
  .llmwiki/                        # existing app data, untouched
```

Paper identity uses arXiv IDs or DOI URLs, then PDF checksums. An unidentified
PDF can join an identified paper only when its bytes match unambiguously.
Titles alone never merge papers. Unknown records receive checksum-based IDs.
ArXiv versions share a paper directory; different PDF bytes are retained.
Exported PDFs and Markdown summaries retain their original filenames. Each paper
directory uses the primary PDF's original filename without its extension (or the
summary's filename when no PDF exists). Generic source stems such as
`2026-paper` or `2026-2026` use a year/title directory name instead; Chinese
characters are preserved. IDs stay in the metadata and catalog for deduplication.
When separate papers share a directory name, later papers in ID
order append `--<paper-id>` to their directory name until it is unique; the
original PDF and Markdown filenames stay unchanged. Alternate accounts use
separate checksum subdirectories, so even matching original filenames remain
unchanged. JSON-only summaries and missing-summary placeholders use the matching
original stem with `.md`.
The primary PDF/summary stays stable on later imports; new versions/accounts
are added alongside it. The initial primary prefers the highest explicit arXiv
version, then the longest summary for that version. This is a selection rule,
not a claim that a summary is correct or that an unversioned URL is current.

All original collection memberships, source paths, manifest metadata, and
checksums are retained in the hidden JSON catalog. A collection may be a video
channel rather than a lab; membership never establishes author affiliation.
Missing PDFs/summaries and conflicting identifiers are reported. Records with
identifier conflicts have `review_required: true` and a visible warning; verify
them before attributing research claims.

Unreadable PDFs are ignored: parsing failure, no extractable text, or extraction
exceeding 60 seconds skips that PDF and its associated paper account, including
its summary. OCR is not attempted. A readable alternative version is retained.
Results are cached by PDF checksum so unchanged PDFs are not parsed again.
Details are recorded under `ignored_pdfs` in the catalog and in console warnings.
If previously imported files belong to an ignored account, only unchanged,
importer-owned copies are moved into `.llmwiki-import/ignored/`; they are no
longer indexed as sources, and no original archive files are moved or deleted.

Existing Markdown summaries are preserved with metadata/provenance added.
Structured JSON supplies tags and serves as a fallback when Markdown is missing.
`topics.yaml`, profile overviews, and source links become collection context.
Download logs, HTML snapshots, caches, and duplicate JSON summary bodies are not
copied into the searchable sources. Original JSON summaries remain in `labs/`.

## Safe reruns

Copies use independent files, never hard links or symlinks. Content is checked
and each file is replaced atomically, so the watcher sees complete files.
Unchanged output files keep their timestamps. The importer updates only its own
unchanged outputs, refuses to overwrite user edits or conflicting unmanaged
files, and never deletes old files. Removed/renamed source records can therefore
leave old output behind; retained paths are listed in the catalog for review.
A partial `--lab` import cannot replace a catalog covering additional collections.

Existing generated filenames and paper directories are migrated automatically. Start the local app
before migrating an initialized workspace: indexed files are renamed through
its local API at `127.0.0.1:8000`, preserving document IDs, annotations, and
extracted content. Existing PDFs are moved rather than copied again. Collection
links and summary-to-PDF links are regenerated. Edited files or occupied rename
targets stop the import without overwriting those files. The rename history is
stored in the catalog. Normal reruns with no filename changes need no API.

Use `sources/` as imported material and edit synthesized knowledge in `wiki/`.
Resolve conflicts in the archive only through your normal curation workflow;
this importer never repairs or modifies it.

## Use with LLM Wiki and Codex

Run the existing local app against the same destination:

```bash
cd ~/llmwiki
source .venv/bin/activate
./llmwiki open ~/research
```

Keep it running during import so its recursive file watcher indexes the new
files. PDF extraction is asynchronous and a collection this size will take
time. The importer generates files; it does not perform OCR, run Codex, or
automatically create thousands of wiki pages.

Then ask Codex, using the already configured `llmwiki` MCP server:

> Call guide first, then read `/sources/catalog.md`. Start with the ETHZ-RSL
> collection. Use summaries for discovery, consult PDFs to verify detailed
> claims, and skip attribution for records marked `review_required` until the
> identity is resolved. Treat alternate summaries/PDF versions as accounts of
> one paper, not independent evidence. Build connected wiki pages for papers,
> concepts, tasks, benchmarks, robots, and verified labs. Preserve citations and
> source files. Process a bounded batch, summarize progress, and leave the rest
> for subsequent runs.

The nightly routine can maintain these sources because it already uses
`~/research`. The importer itself is manual: rerun it after the archive changes.
The hidden catalog is operational metadata; the searchable entry point is
`/sources/catalog.md`. Copies already present under other research folders are
not deduplicated or deleted by this importer.

## Tests

```bash
python3 -m unittest discover -p 'test_prepare_llmwiki.py'
```
