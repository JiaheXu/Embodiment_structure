# Summary Audit and Revised Plan

Date: 2026-10-29. Scope: `labs/` archive, the summarization pipeline in this repository, and the LLM Wiki workspace at `~/research`. All numbers below were measured on this machine today; sampled measurements say so.

## 1. What exists

| Item | Measured |
|---|---|
| Collections (`labs/*`) | 76 (researcher Scholar profiles and Bilibili channels) |
| PDFs | 4,094 (45 GB total, median 6.6 MB, median 19 pages, p90 35 pages) |
| Distinct titles | 3,452; 491 titles appear in more than one collection (644 extra copies) |
| Distinct arXiv ids in `papers.json` | 2,986 of 3,747 entries with an arXiv URL |
| Years (`papers.json`) | 2023: 508, 2024: 763, 2025: 1,159, 2026: 1,672 (one typo "2088") |
| Schema-v1 JSON summaries (`summary_json/`) | 3,692, one key set, 23 top-level fields, median 27 KB |
| Markdown summaries | 4,072: 3,692 mirror the JSON; 378 are "category review" stubs (pages 1–3 excerpt only, 2.7 KB), not summaries |
| PDFs with no real summary | 404 |
| JSON summaries with no PDF | 2 |
| `.summary_cache` | 3,102 entries keyed by sha256(normalized title); cross-collection duplicate summaries are byte-identical (596 of 600 checked) |
| Non-robotics papers | about 7.5% (empty `index_tags.robot`); Scholar profiles pull everything an author wrote |
| PDF text extractability | 60-PDF sample: all extractable, median 4,300 chars/page, no scanned PDFs found |

The LLM Wiki side is further along than the earlier discussion assumed:

| Item | Measured |
|---|---|
| `~/llmwiki` | installed, local mode, custom `api/domain/wiki_build.py` and `workspace_sync.py` |
| `~/research/sources/papers` | 3,278 paper directories; importer catalog lists 3,281 papers, 35 ignored PDFs, 2 `review_required` |
| `~/research/.llmwiki/index.db` | 1.4 GB, last written today |
| `~/research/wiki` | 2,246 pages: 1,997 entity pages, 248 concept pages, `overview.md`; written 2026-10-27 to 10-29; Chinese; every page carries `file.pdf, p.N` footnotes; entity pages carry `source` and `source_id` frontmatter |
| Wiki builder | `llmwiki-refresh.service` (systemd user unit) running `codex -a never` on batches of 10 sources since 2026-10-27 06:40; status today: 1,995 of 3,259 readable sources done, 1,264 pending, 20 skipped |

Pipeline code in this repository: `download_paper.py` (Scholar via attached Chrome), `summarize_paper.py`, `prepare_llmwiki.py` (importer with unit tests). The `tests/` directory referenced by README and COMMANDS.md does not exist in this checkout.

## 2. Summary provenance

Facts established from `summarize_paper.py` and `summarize_paper.sh`:

- Input: `pdftotext -enc UTF-8` over the whole PDF, then truncated to the first 90,000 characters (`DEFAULT_MAX_CHARS`). PDF-file mode exists but the local proxy drops file parts, so text mode is the default and was used.
- Model: `gpt-6-astra` through the local Codex proxy by default, or `deepseek-v4-pro` with `AI_BACKEND=deepseek`. Temperature 0, up to 4 attempts. The model used is not recorded per summary, so per-file provenance is "one of these two, unknown which".
- Token usage is not recorded anywhere.
- Prompt instructs "Not clear from extracted text" for unsupported fields; this is honored consistently.
- Cache key is the normalized title, not content. Two different papers with the same normalized title would share one summary (22 duplicate titles exist in the cache; not yet checked individually).
- Summaries carry no page locators. They name figures and tables ("Table 1", "Figure 3") but never physical pages.

Truncation, measured on 300 random summary/PDF pairs:

| Measure | Value |
|---|---|
| PDFs exceeding the 90,000-character cap | 50 of 300 (17%) |
| Text dropped for those PDFs | median 20%, p90 52% |
| Summaries whose discussion notes state the appendix was missing | 563 of 3,692 |
| Summaries mentioning an appendix at all | 1,848 of 3,692 |

Because the cap is deterministic, the exact pages each summary saw can be recomputed for every paper from `pdftotext` page offsets. That belongs in the coverage ledger as `summary_saw_pages`.

## 3. Summary quality

Unknown-marker density over all 3,692 JSON summaries (share of leaf strings matching the unknown phrases):

| Field group | Unknown share |
|---|---|
| deployment_practicality | 47% |
| data_and_training_setup | 36% |
| evidence_strength | 32% |
| failure_modes | 26% |
| implementation_notes | 18% |
| embodiment_and_generalization | 14% |
| benchmark_and_evaluation | 7% |
| results | 5% |
| method | 4% |
| limitations | 2% |

Median paper: 9.5% unknown leaves; p90: 16%. The high-unknown groups are exactly the deployment-oriented fields the prompt asks for and papers rarely state, so these are honest unknowns, not extraction failures.

Numeric fidelity, 300 pairs, 12,164 numbers taken from `results`, `comparison_summary`, `data_and_training_setup`, and `task_performance`, checked verbatim against the full `pdftotext` output:

| Measure | Value |
|---|---|
| Numbers found in full PDF text | mean 93.7%, median 95.7%, p10 83.7% |
| Numbers found in the truncated 90k prefix | mean 93.6% |
| Numbers found only beyond the cut | 6 of 12,164 |
| Papers under 70% found | 2 (PRIME at 44%, MAC-VO at 65%) |

Interpretation: the summaries do not fabricate numbers at any detectable rate, and they did not use text beyond the cut. Misses concentrate in table cells that `pdftotext` scrambles and in differences the summarizer computed itself (for example "45-percentage-point improvement"). This check validates presence, not attribution: a number can be real and still attached to the wrong condition. A 30-pair attribution audit by a model is still required (spec section 9) and has not been done.

Structured facets already present in every summary: `index_tags` with `input`, `output`, `robot`, `task`, `evaluation`, `generalization`, `assets`. Vocabulary is uncontrolled (for example `multi_view_rgb` next to `rgb_multiview`), so a normalization pass is needed before SQL filtering is reliable.

## 4. What this changes in the plan

1. The premise "nothing installed, summaries not inspected" is outdated. llmwiki is installed, the importer has run, and the wiki is 61% built with page-level citations. The missing layer is the research service from the spec: structured records, coverage ledger, provenance, whole-library sweeps, and project memory.
2. The summaries are good enough to be the bootstrap record. Schema v1 maps nearly one-to-one onto the spec's research fields. Import them deterministically with origin `existing_summary`, verification `unverified`, text coverage = pages within the first 90,000 characters. Do not regenerate them.
3. The one-time full-text extraction pass over the whole collection, previously the largest cost item, is not needed. Residual model work is small: 404 missing summaries (run the existing `summarize_paper.sh`), one tag-normalization pass, appendix enrichment only when a question needs it, and the attribution audit.
4. Keep the running Codex wiki builder. Its entity pages are the per-paper wiki layer and already carry `source_id`, which links to the importer catalog. The SQLite layer should reference that id as the canonical paper identity rather than re-deriving identity from titles.
5. Trim the spec's M1 data model for the first runnable version: `paper`, `asset_version`, `summary_record`, `field_value` (paper, field, value, origin, verification, locator), `coverage` (paper, layer, status, detail), `review_run`, `review_item`, `job`. Keep `method_variant` and `evaluation_result` as validated JSON inside `summary_record` until a question needs them as tables.
6. The cross-language split matters for search: summaries are English, wiki pages are Chinese. FTS5 with the default tokenizer will not match Chinese; use the trigram tokenizer for the wiki table or index both with embeddings.

## 5. Revised minimum engineering, in order

1. Bootstrap `research.db` from existing files with no model calls: papers from `~/research/.llmwiki-import/catalog.json`, summaries from `summary_json/`, coverage from `pdftotext` page offsets against the 90k cap, wiki entity pages by `source_id`. About one day.
2. `lib` CLI callable from Codex CLI and Claude Code through the shell: `search`, `paper`, `pages`, `page-image`, `sql`, `coverage`, `save-finding`. One `AGENTS.md` with the evidence rules, symlinked as `CLAUDE.md`. About one day.
3. Run `summarize_paper.sh` for the 404 PDFs without summaries. Record the model used this time.
4. Tag normalization: one model pass over `index_tags` into a controlled vocabulary, stored as `field_value` rows with origin `existing_summary`. Roughly 3,452 papers × 300 tokens.
5. Whole-library sweep runner over compact records (tldr, normalized tags, implementation notes, about 600 tokens per paper): roughly 2M input tokens per question.
6. 30-pair attribution audit, model-judged, to close the gap the numeric check leaves.
7. Appendix enrichment on demand for the 17% truncated papers.

## 6. Open items and risks

- Per-summary model provenance is unknown; record it as unknown rather than guessing.
- Title-keyed summary cache: verify the 22 duplicate-title cache entries are the same paper.
- 35 PDFs ignored by the importer as unreadable and 20 sources skipped by the wiki builder need coverage ledger rows, not silence.
- The 378 category-review stubs must not be imported as summaries.
- Non-robotics papers (about 7.5%) should be tagged out of scope, not deleted, so collection-wide denominators stay honest.
- The wiki builder has about 1,264 sources left; at the observed rate it finishes in roughly 1.5 days. Heavy concurrent `pdftotext` jobs are fine but avoid writing into `~/research/wiki` while it runs.
