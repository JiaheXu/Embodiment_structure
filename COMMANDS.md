# Lab Paper Pipeline Commands

Run these from the repository root:

```bash
cd /home/jiahe/Embodiment_structure
```

Quote lab names that contain spaces, parentheses, or non-ASCII characters:

```bash
--lab 'airlab(basti)'
--lab 'ETHZ-RSL'
--lab '3D视觉工坊'
```

## Download Papers

Use the wrapper for normal runs. It sets the local AI endpoint/model defaults.
Normal runs skip Bilibili channels; use `--bilibili-only` to process them explicitly.

```bash
./download_paper.sh
```

Dry run:

```bash
./download_paper.sh --dry-run
```

One specific lab:

```bash
./download_paper.sh --lab 'airlab(basti)'
./download_paper.sh --lab '3D视觉工坊'
```

Only test one lab without downloading:

```bash
./download_paper.sh --lab 'airlab(basti)' --dry-run
```

Limit how many labs are scanned:

```bash
./download_paper.sh --limit 5
```

Choose extractor mode:

```bash
./download_paper.sh --extractor static
./download_paper.sh --extractor ai
./download_paper.sh --extractor hybrid
```

Year cutoff:

```bash
./download_paper.sh --min-year 2024
```

Parallel workers:

```bash
./download_paper.sh
./download_paper.sh --workers 4
DOWNLOAD_PAPER_WORKERS=4 ./download_paper.sh
```

Longer timeout:

```bash
DOWNLOAD_PAPER_TIMEOUT=3600 ./download_paper.sh
```

All labs with an attached Chrome session for Google Scholar:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="$PWD/.x_chrome_profile" --profile-directory=Default
./download_paper.sh
```

Scholar tabs are opened automatically in the attached Chrome session and closed
after reading. You do not need to open each researcher's profile manually.
If a robot check appears, solve it in Chrome; the downloader waits and resumes
automatically, with no terminal confirmation needed.

## Bilibili Downloading

Only Bilibili labs:

```bash
./download_paper.sh --bilibili-only
```

Dry run only Bilibili labs:

```bash
./download_paper.sh --bilibili-only --dry-run
```

Limit recent Bilibili videos:

```bash
BILIBILI_VIDEO_LIMIT=50 ./download_paper.sh --bilibili-only --dry-run
```

Use browser cookies when Bilibili blocks anonymous requests:

```bash
./download_paper.sh --bilibili-cookies-from-browser chrome
```

Use a cookies.txt file:

```bash
./download_paper.sh --bilibili-cookies /path/to/bilibili-cookies.txt
```

## Summarize Papers

Summarize all pending papers:

```bash
./summarize_paper.sh
```

Summarize one lab:

```bash
./summarize_paper.sh --lab 'airlab(basti)'
```

Limit papers per lab:

```bash
./summarize_paper.sh --lab 'airlab(basti)' --limit 5
```

Dry run:

```bash
./summarize_paper.sh --lab 'airlab(basti)' --dry-run
```

Regenerate existing summaries for one lab:

```bash
./summarize_paper.sh --force --lab 'airlab(basti)'
```

Regenerate all summaries:

```bash
./summarize_paper.sh --all
```

Use extracted text instead of raw PDF input:

```bash
./summarize_paper.sh --source text --lab 'airlab(basti)' --limit 1
```

Increase extracted text size:

```bash
./summarize_paper.sh --max-chars 120000
```

Longer timeout:

```bash
SUMMARIZE_PAPER_TIMEOUT=3600 ./summarize_paper.sh
```

## Rebuild Summaries From Scratch

Remove existing generated summaries:

```bash
find labs -type d -name summary -exec rm -rf {} +
find labs -type d -name summary_json -exec rm -rf {} +
```

Then re-run:

```bash
./summarize_paper.sh
```

## Build RAG Index

Build index files from `summary_json`:

```bash
python3 labs/build_rag_index.py
```

Custom output directory:

```bash
python3 labs/build_rag_index.py --output-dir /tmp/rag_index
```

Generated files:

```text
labs/rag_index/papers.jsonl
labs/rag_index/paper_embeddings.jsonl
labs/rag_index/chunks.jsonl
labs/rag_index/embeddings.jsonl
```

Important: build mode stops after writing index files. To search, use
`--search-only`.

Search by paper-provided keyword:

```bash
python3 labs/build_rag_index.py --search-only --keyword 'dexterous grasping'
```

Search by requirement text:

```bash
python3 labs/build_rag_index.py --search-only --query 'RGB-D language manipulation on a real robot'
```

Limit returned candidates:

```bash
python3 labs/build_rag_index.py --search-only --query 'mobile manipulation in open world' --top-k 20
```

## Open RAG UI

Build the RAG index first:

```bash
python3 labs/build_rag_index.py
```

Serve the `labs/` directory locally:

```bash
cd labs
python3 -m http.server 8006 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8006/rag_ui.html
```

## Backend Selection

Use local OpenAI-compatible proxy:

```bash
AI_BACKEND=local ./download_paper.sh --dry-run
AI_BACKEND=local ./summarize_paper.sh --dry-run
```

Use DeepSeek:

```bash
AI_BACKEND=deepseek DEEPSEEK_API_KEY=... ./download_paper.sh --dry-run
AI_BACKEND=deepseek DEEPSEEK_API_KEY=... ./summarize_paper.sh --dry-run
```

Optional local secrets and proxy settings:

```text
local_env.sh
```

Do not commit secrets.

## Common Workflows

Download and summarize one lab:

```bash
./download_paper.sh --lab 'airlab(basti)'
./summarize_paper.sh --lab 'airlab(basti)'
```

Re-summarize one lab and rebuild RAG:

```bash
./summarize_paper.sh --force --lab 'airlab(basti)'
python3 labs/build_rag_index.py
```

Full refresh after deleting summaries:

```bash
find labs -type d -name summary -exec rm -rf {} +
find labs -type d -name summary_json -exec rm -rf {} +
./summarize_paper.sh
python3 labs/build_rag_index.py
```

Check all tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=/home/jiahe/Embodiment_structure pytest -o cache_dir=/tmp/embodiment_pytest_cache tests
```
