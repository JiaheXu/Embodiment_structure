# Lab Paper Collection

This directory stores lab publication sources and the downloader used to collect
recent papers.

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
python3 labs/download_paper.py
```

Safer preview mode:

```bash
python3 labs/download_paper.py --dry-run
```

The downloader scans lab folders in parallel with 2 workers by default. Inside
each lab folder, it still processes papers sequentially so that `papers.json`,
`pdfs/`, and `failed.txt` stay simple and predictable. For each folder, it
reads `link.txt`, extracts papers from 2023 onward, skips papers already
present in `papers.json` or `pdfs/`, and downloads only new PDFs.

Useful options:

```bash
python3 labs/download_paper.py --dry-run --limit 1
python3 labs/download_paper.py --lab goldberg --dry-run
python3 labs/download_paper.py --min-year 2024
python3 labs/download_paper.py --timeout 1800
python3 labs/download_paper.py --workers 4
python3 labs/download_paper.py --extractor static
python3 labs/download_paper.py --extractor ai
python3 labs/download_paper.py --extractor hybrid
python3 labs/download_paper.py --bilibili-only --dry-run
python3 labs/download_paper.py --bilibili-only --dry-run --bilibili-cookies-from-browser chrome
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
are handled separately. The downloader uses `yt-dlp` to read recent video
metadata, then asks the AI extractor to identify arXiv papers mentioned by the
videos. If an arXiv link or ID appears directly in the metadata, the static
fallback can also pick it up. When a video still has no matched paper, the
downloader searches arXiv with the video metadata before giving up; unresolved
video URLs are appended to that lab's `failed.txt` for manual checking.
`--bilibili-only` defaults to Chrome browser cookies because Bilibili often
blocks anonymous requests. By default, it only reads the latest first page of
uploads, currently 30 videos. Control that first-page cap with:

```bash
BILIBILI_VIDEO_LIMIT=30 ./labs/download_paper.sh --dry-run
BILIBILI_VIDEO_LIMIT=30 ./labs/download_paper.sh --bilibili-only --dry-run
```

If Bilibili returns `412 Request is blocked by server`, provide cookies for
`yt-dlp`:

```bash
BILIBILI_COOKIES=/path/to/bilibili-cookies.txt ./labs/download_paper.sh --dry-run
BILIBILI_COOKIES_FROM_BROWSER=chrome ./labs/download_paper.sh --dry-run
python3 labs/download_paper.py --bilibili-only --dry-run --bilibili-cookies-from-browser chrome
python3 labs/download_paper.py --bilibili-only --dry-run --bilibili-cookies /path/to/bilibili-cookies.txt
```

## AI Launch Script

Use the launch wrapper when extraction should go through the local proxy:

```bash
./labs/download_paper.sh --dry-run --limit 1
./labs/download_paper.sh --workers 4
```

The wrapper runs `--extractor hybrid`: it asks the AI model for paper links,
then merges that result with the local static parser. This is intentional. Some
large pages, such as AIRLab, can cause the AI model to return only newer papers;
the static parser catches older BibTeX-backed entries from 2023 and 2024.

The wrapper passes `--timeout "${DOWNLOAD_PAPER_TIMEOUT:-1800}"`. To override:

```bash
DOWNLOAD_PAPER_TIMEOUT=3600 ./labs/download_paper.sh --dry-run
```

## Paper Summaries

After PDFs are downloaded, generate one Markdown summary per paper:

```bash
./labs/summarize_paper.sh --dry-run --lab 'airlab(basti)' --limit 1
./labs/summarize_paper.sh --lab 'airlab(basti)' --limit 1
```

Main script:

```bash
python3 labs/summarize_paper.py
```

Summary files are written to:

```text
labs/<lab_name(founder_name)>/summary/<year>-<paper-title>.md
```

The summarizer reads `papers.json`, finds each paper's local `pdf_path`, then
sends the raw PDF to the configured AI model so figures, charts, tables, and
architecture diagrams can inform the summary. If the AI endpoint does not
support raw PDF file parts, it falls back to `pdftotext` and sends extracted
text. The summary follows the paper-share style: presentation-ready,
problem-first, and organized around:

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
./labs/summarize_paper.sh --lab 'airlab(basti)' --limit 5
./labs/summarize_paper.sh --force --lab 'airlab(basti)'
./labs/summarize_paper.sh --all --lab 'airlab(basti)'
./labs/summarize_paper.sh --source text --lab 'airlab(basti)' --limit 1
./labs/summarize_paper.sh --max-chars 120000
SUMMARIZE_PAPER_TIMEOUT=3600 ./labs/summarize_paper.sh
```

By default, existing summary files are skipped. Use `--force` or `--all` to
regenerate summaries for papers that already have summary files.

By default it uses the local OpenAI-compatible proxy:

```text
http://127.0.0.1:8787/v1/chat/completions
```

The wrapper exports:

- `AI_BASE_URL`
- `AI_API_KEY`
- `AI_MODEL`

It supports two backends:

```bash
AI_BACKEND=local ./labs/download_paper.sh --dry-run
AI_BACKEND=deepseek DEEPSEEK_API_KEY=... ./labs/download_paper.sh --dry-run
```

Optional local secrets and proxy settings can be put in:

```text
labs/local_env.sh
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

- Keep downloader code in `labs/`, not a separate `lab/` directory.
- Prefer `./labs/download_paper.sh` for AI extraction because it sets the local
  proxy and model environment consistently, while still using hybrid fallback.
- Keep `python3 labs/download_paper.py --dry-run ...` working for local static
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
