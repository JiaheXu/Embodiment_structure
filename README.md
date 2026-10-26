# Lab Paper Collection

The repository root contains the downloader and summarizer. The `labs/`
directory stores publication sources, PDFs, summaries, and metadata.

## Directory Rules

- Each lab has one folder directly under `labs/`.
- Lab folders are named as `lab_name(founder_name)`, for example
  `iamlab(oliver)` or `GRAIL(lerrel)`.
- Each lab folder must contain a `link.txt` file.
- `link.txt` contains the publication page or profile page for that lab.
- Downloaded PDFs go in `labs/<lab_name(founder_name)>/pdfs/`.
- The downloader records seen papers in
  `labs/<lab_name(founder_name)>/papers.json`.
- Failed PDF downloads are recorded by paper title in
  `labs/<lab_name(founder_name)>/failed.txt`.

## Downloader

Main script:

```bash
python3 download_paper.py
```

Safer preview mode:

```bash
python3 download_paper.py --dry-run
```

The downloader scans lab folders in parallel with 2 workers by default. Inside
each lab folder, it still processes papers sequentially so that `papers.json`,
`pdfs/`, and `failed.txt` stay simple and predictable. For each folder, it
reads `link.txt`, extracts papers from 2023 onward, skips papers already
present in `papers.json` or `pdfs/`, and downloads only new PDFs.
For NVIDIA GEAR, the static extractor reads the publication page's JavaScript
bundle because its initial HTML contains empty publication lists.
Default runs skip Bilibili channel folders. Use `--bilibili-only` or explicitly
select a channel with `--lab` to process those folders.
For fresh and cached Google Scholar pages, each paper's PDF link is resolved and
downloaded immediately. The downloader waits one second after a successful
download before resolving the next paper.
Failed PDF requests wait 0.5 seconds before retrying, with at most four attempts.

When normal Google Scholar resolution finds no PDF, or a PDF download exhausts
its retries, the local AI proxy searches for an alternative public PDF. The
request includes the paper title, year, source URL, failure reason, and the
Scholar profile author (or lab folder name when unavailable). This uses the
same `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL` exported by `download_paper.sh`,
with `/chat/completions` replaced by `/responses` to enable web search.
The fallback runs only for the local backend when an AI endpoint is configured,
and never during `--dry-run`. A recovered file must have a PDF header before it
is saved and added to `papers.json`; unrecovered titles go to `failed.txt`.

Useful options:

```bash
python3 download_paper.py --dry-run --limit 1
python3 download_paper.py --lab goldberg --dry-run
python3 download_paper.py --min-year 2024
python3 download_paper.py --timeout 1800
python3 download_paper.py --workers 4
python3 download_paper.py --extractor static
python3 download_paper.py --extractor ai
python3 download_paper.py --extractor hybrid
python3 download_paper.py --bilibili-only --dry-run
python3 download_paper.py --bilibili-only --dry-run --bilibili-cookies-from-browser chrome
```

The default timeout is 1800 seconds, or 30 minutes. This timeout applies to
page fetches, AI extraction requests, and PDF downloads.

Use `--workers 1` when you want the old fully sequential lab-by-lab behavior.

Extractor modes:

- `static`: Parse static HTML locally. Fast, but misses dynamic or unusual pages.
- `ai`: Send the page HTML to an OpenAI-compatible model and ask it to extract
  paper metadata.
- `hybrid`: Try AI extraction first, then fall back to static parsing if AI
  returns no papers.

Bilibili channel links such as `https://space.bilibili.com/.../upload/video`
use the same local Chrome connection as Scholar when configured. The wrapper
uses Chrome at `http://127.0.0.1:9222` by default. It waits for video cards to
render and reads only the videos shown at the supplied link, up to the video
limit, retaining the full card titles. It does not advance to another page.
Sign in to Bilibili in that Chrome profile. If uploads are
hidden by login or verification, the tab stays open and the scanner waits for
you to sign in, solve the check, and refresh, just as it does for Scholar.
Full descriptions come from the public metadata API, with browser video pages
as fallback. Without a Chrome connection, the Python CLI uses `yt-dlp`.
The AI extractor then identifies arXiv papers mentioned by the
videos. If an arXiv link or ID appears directly in the metadata, the static
fallback can also pick it up. When a video still has no matched paper, the
downloader searches arXiv with the video metadata before giving up; unresolved
video URLs are appended to that lab's `failed.txt` for manual checking.
The downloader reads each video's full title and description from Bilibili's
public view API first, avoiding unnecessary playback-format requests and their
412 retries. Per-video progress is printed as metadata arrives. If the view API
fails, the Chrome workflow reads the video page; the workflow without Chrome
falls back to yt-dlp. Metadata failures
are logged instead of silently discarding descriptions. arXiv searches use
English title phrases and check result titles before accepting a match.
Short names before a colon in video titles (such as `Steerable Policies`,
`ECoT`, or `ThinkAct`) are searched as exact phrases in arXiv titles and
abstracts. The resolver prefers a matching named title or an abstract that
introduces the method; ambiguous matches remain unresolved.
Hybrid extraction continues with explicit arXiv links and title searches if
the AI endpoint fails. Successful downloads clear their saved failure entries.
For the local AI backend, a batch with no identified papers or explicit arXiv
links gets a web-search lookup through `/responses`. The request uses full video
context to disambiguate short names and excludes announcements without papers.
Proxy errors and empty responses are reported as extraction failures.
Papers with identified links download before optional title searches. Videos
already represented in `papers.json` do not trigger another title search.
All worker threads share a single arXiv API connection with at least three
seconds between requests. Successful queries are reused within the run.
HTTP 429 responses respect `Retry-After` (seconds or an HTTP date); without
that header, retries wait 30 then 60 seconds. If retries still exhaust with
HTTP 429, new API searches are deferred for the rest of the run; cached results
and downloads with known links remain available. Individual Bilibili arXiv
requests have a maximum 30-second timeout, and resolving-video progress is logged.
Videos about general news or discussions may have no identifiable paper;
a video URL in `failed.txt` means paper identification failed, while a paper
title means the PDF could not be downloaded.
`--bilibili-only` defaults to Chrome browser cookies because Bilibili often
blocks anonymous requests. HTTP 412 errors automatically retry once with
`yt-dlp --impersonate chrome --sleep-requests 1`, retaining the configured
cookies. This requires yt-dlp's optional `curl-cffi` support; install it with
`python3 -m pip install -U "yt-dlp[default,curl-cffi]"` if the impersonation
target is unavailable.
If upload listing remains blocked, channels with saved Bilibili URLs in
`failed.txt` retry those videos through the public metadata API, up to the
video limit. The log marks this as a partial scan: new uploads cannot be checked.
Channels without saved video URLs still report a listing failure.
By default, the cap is 100 uploads; Chrome scans only the visible page even
when it contains fewer videos. Without Chrome, `yt-dlp` handles
pagination across channel API pages. The downloader processes only entries returned by `yt-dlp`
and does not independently verify the channel's total upload count. Override the cap with:

```bash
BILIBILI_VIDEO_LIMIT=50 ./download_paper.sh --bilibili-only --dry-run
```

If Bilibili returns `412 Request is blocked by server`, provide cookies for
`yt-dlp`:

```bash
BILIBILI_COOKIES=/path/to/bilibili-cookies.txt ./download_paper.sh --dry-run
BILIBILI_COOKIES_FROM_BROWSER=chrome ./download_paper.sh --dry-run
python3 download_paper.py --bilibili-only --dry-run --bilibili-cookies-from-browser chrome
python3 download_paper.py --bilibili-only --dry-run --bilibili-cookies /path/to/bilibili-cookies.txt
```

## AI Launch Script

Use the launch wrapper when extraction should go through the local proxy:

```bash
./download_paper.sh --dry-run --limit 1
./download_paper.sh
```

The wrapper runs `--extractor hybrid`: it asks the AI model for paper links,
then merges that result with the local static parser. If an AI request fails
after retries, hybrid mode continues with static extraction. Explicit
`--extractor ai` runs still report AI failures. Some large pages, such as AIRLab,
can cause the AI model to return only newer papers;
the static parser catches older BibTeX-backed entries from 2023 and 2024.
It defaults to `--workers 1` to avoid rate limits when scanning all labs. Use
`--workers N` or `DOWNLOAD_PAPER_WORKERS=N` to override it.
For Google Scholar and Bilibili pages, the wrapper attaches to Chrome at
`http://127.0.0.1:9222` by default, so open Chrome first:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="$PWD/.x_chrome_profile" --profile-directory=Default &
./download_paper.sh
# Scan Bilibili channels using the same Chrome profile:
./download_paper.sh --bilibili-only
```

Use `GOOGLE_SCHOLAR_CDP_URL=http://127.0.0.1:9223` if your Chrome DevTools port
is different.
The downloader opens each requested Scholar profile or pagination URL automatically
and closes tabs it creates after reading them. Existing tabs are reused only when
their URL matches exactly and are left open. If Scholar shows a CAPTCHA or consent
page, the downloader keeps the tab open and waits for you to complete it in Chrome,
then resumes automatically. Manual checks allow at least 30 minutes, even for
citation requests with shorter fetch timeouts. Unresolved checks leave the tab open.

The wrapper passes `--timeout "${DOWNLOAD_PAPER_TIMEOUT:-1800}"`. To override:

```bash
DOWNLOAD_PAPER_TIMEOUT=3600 ./download_paper.sh --dry-run
```

## Paper Summaries

After PDFs are downloaded, generate one Markdown summary per paper:

The summarizer requests four concurrent workers shared across all selected labs.
Use `--workers 1` for sequential processing or `--workers N` to adjust concurrency.
For a local proxy, it reads `/health` at startup and caps workers to the reported
available request slots. For example, three total slots with one occupied allow
two summarizer workers. If capacity changes and the proxy returns HTTP 503,
the request waits 30 seconds between retries, for up to the configured timeout
(30 minutes by default), rather than exhausting four retries within seconds.
Duplicate titles are coordinated so only one worker sends an AI request; other
workers reuse its saved summary. Updates to the processed-paper list are serialized
and written atomically. Actual speedup depends on the local proxy's capacity.

```bash
./summarize_paper.sh --dry-run --lab 'airlab(basti)' --limit 1
./summarize_paper.sh --lab 'airlab(basti)' --limit 1
```

Main script:

```bash
python3 summarize_paper.py
```

Summary files are written to:

```text
labs/<lab_name(founder_name)>/summary/<year>-<paper-title>.md
```

The summarizer reads `papers.json`, finds each paper's local `pdf_path`, then
uses `pdftotext` to send extracted paper text to the configured AI model by
default. The local proxy at `http://127.0.0.1:8787/v1/chat/completions` silently
drops PDF file parts, so raw PDF requests can produce summaries without source
content. Text mode includes readable captions and tables but does not send figure
images. Use `--source pdf` only with an endpoint that supports PDF file parts;
request errors can trigger a fallback to extracted text. Use `--force` to
regenerate existing summaries made without source content.
Text mode cuts off at the first recognized references, bibliography, appendix,
or supplementary-material heading before whitespace normalization and the
`--max-chars` limit. Extraction uses reading order to separate main-body columns
from reference columns and recognizes spaced headings such as “R EFERENCES.”
Inline mentions such as “see Appendix A” and table-of-contents
entries do not trigger a cutoff. Papers without a recognized heading retain the
existing character limit; there is no fixed nine-page cap. The prompt marks
omitted sections as unavailable evidence. Raw `--source pdf` requests still send
the full PDF. Existing summaries and cached summaries continue to be reused.

Newly generated summaries are also saved in `labs/.summary_cache/<title-hash>.json`.
The shared processed-paper list is `labs/summarized_papers.json`, mapping title
hashes to normalized titles. It is loaded once at startup and saved atomically
after each successful paper, so completed work survives interruption. Already
summarized papers reuse their saved summaries without a local proxy request.
If the list is missing or damaged, saved cache entries can restore it as papers
are encountered. A missing or damaged summary is regenerated rather than skipped.
The key is a SHA-256 hash of the title after Unicode, case, and whitespace
normalization. Duplicate titles across labs and later runs reuse this local cache,
while each lab receives its own Markdown and JSON files with its paper metadata.
`--force` and `--all` refresh each unique title once per run, then reuse the fresh
summary for duplicates. Existing summaries are not automatically imported into
the cache; regenerate them to populate it. Identical titles share a summary even
if the year or PDF differs. Delete a cache file or use `--force` to refresh it.
The summary follows the paper-share style: presentation-ready,
problem-first, and organized around:

- Paper Summary (a fuller overview based primarily on the introduction)
- TL;DR
- Problem
- Motivation
- Method
- Results
- Robot System Taxonomy
- Benchmark And Evaluation
- Embodiment And Generalization
- Implementation Notes For VLA / Robot Systems
- Contributions
- Limitations
- Discussion Notes
- Keywords And Features

Useful options:

```bash
./summarize_paper.sh --lab 'airlab(basti)' --limit 5
./summarize_paper.sh --workers 4
./summarize_paper.sh --force --lab 'airlab(basti)'
./summarize_paper.sh --all --lab 'airlab(basti)'
./summarize_paper.sh --source text --lab 'airlab(basti)' --limit 1
./summarize_paper.sh --max-chars 120000
SUMMARIZE_PAPER_TIMEOUT=3600 ./summarize_paper.sh
```

By default, existing summary files are skipped. Use `--force` or `--all` to
regenerate summaries for papers that already have summary files.

Each text-summary start log includes `chars: original -> sent`, where `sent`
accounts for both back-matter removal and `--max-chars`. The completion log
includes `elapsed: Ns` for extraction, AI processing, and saving the summary.
Cache reuse is labeled `source: cache` and does not extract the PDF for counts.

## RAG Index

After summaries exist, build the retrieval index:

```bash
python3 labs/build_rag_index.py
```

This reads `labs/<lab_name>/summary_json/*.json` and writes:

```text
labs/rag_index/papers.jsonl
labs/rag_index/paper_embeddings.jsonl
labs/rag_index/chunks.jsonl
labs/rag_index/embeddings.jsonl
```

Search with paper-provided keywords or requirement text:

```bash
python3 labs/build_rag_index.py --search-only --keyword "dexterous grasping"
python3 labs/build_rag_index.py --search-only --query "RGB-D language manipulation on a real robot"
```

Search returns candidate paper JSON objects with title, abstract,
paper-provided keywords, index tags, and supporting chunks. Send that candidate
list to an LLM agent for the final related-work decision.

The first version uses dependency-free local hash embeddings plus keyword and
lexical boosting, so it is easy to inspect and replace with API embeddings
later.

Open the browser UI after building the index:

```bash
cd labs
python3 -m http.server 8006
```

Then open `http://127.0.0.1:8006/rag_ui.html`.

By default it uses the local OpenAI-compatible proxy:

```text
http://127.0.0.1:8787/v1/chat/completions
```

The wrapper exports:

- `AI_BASE_URL`
- `AI_API_KEY`
- `AI_MODEL`

The wrapper uses the local proxy with `gpt-6-astra`:

```bash
./download_paper.sh --dry-run
```

`CODEX_PROXY_URL` or `CODEX_PROXY_BASE_URL` can change the proxy address, and
`CODEX_PROXY_API_KEY` supplies a custom proxy credential. The wrapper always
selects `gpt-6-astra` and overwrites stale AI backend/model environment settings.
Optional local secrets and proxy settings can be put in:

```text
local_env.sh
```

Do not commit secrets.

## Progress Logs

The downloader should keep progress logs because scanning many labs can take a
while, especially with AI extraction. Expected log shape:

```text
[progress] queued 18 labs for scanning
[lab 1/18] start: GRAIL(lerrel) | waiting: 17
[extract:ai] requesting paper links | model=gpt-5.5 | endpoint=http://127.0.0.1:8787/v1/chat/completions | html_chars=123456 | min_year=2023
[extract:ai] extracted 23 papers | by_year: 2023=7, 2024=10, 2025=6
[scan] GRAIL(lerrel): 23 recent PDFs, 23 new | found_by_year: 2023=7, 2024=10, 2025=6 | new_by_year: 2023=7, 2024=10, 2025=6
[lab 1/18] done: GRAIL(lerrel) | waiting: 17 | found: 23, new: 23
[progress] finished 18/18 labs; failed: 0
```

On failure, the script should log which lab failed and continue with the next
lab.

Do not ask an AI model to reveal hidden chain-of-thought. Log observable
extraction evidence instead: extractor mode, model, endpoint, HTML length,
paper count, and per-year counts since the minimum year.

## Agent Notes

- Keep pipeline code in the repository root; keep lab data under `labs/`.
- Prefer `./download_paper.sh` for AI extraction because it sets the local
  proxy and model environment consistently, while still using hybrid fallback.
- Keep `python3 download_paper.py --dry-run ...` working for local static
  testing.
- Lab folders are scanned in parallel by default with 2 workers. Keep each
  individual lab's paper downloads and manifest writes sequential unless there
  is a strong reason to add finer-grained locking.
- Do not overwrite existing PDFs or manifest entries unnecessarily.
- When a PDF download fails, append the paper title to that lab's `failed.txt`
  without duplicating existing entries.
- If changing behavior, update `tests/test_download_paper.py` and run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```
