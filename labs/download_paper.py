from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from http.client import IncompleteRead, InvalidURL
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


DEFAULT_MIN_YEAR = 2023
DEFAULT_TIMEOUT_SECONDS = 30 * 60
DEFAULT_WORKERS = 2
DEFAULT_HTTP_ATTEMPTS = 3
BILIBILI_VIDEO_LIMIT = 30
GOOGLE_SCHOLAR_PAGE_SIZE = 100
GOOGLE_SCHOLAR_MAX_PAGES = 20
RAI_LOAD_MORE_PAGE_SIZE = 12
RAI_LOAD_MORE_MAX_PAGES = 10
RAI_ARXIV_SEARCH_TIMEOUT_SECONDS = 10
MANIFEST_NAME = "papers.json"
PDF_DIR_NAME = "pdfs"
FAILED_NAME = "failed.txt"
USER_AGENT = "Mozilla/5.0 (compatible; lab-paper-collector/0.1)"
AI_HTML_CHAR_LIMIT = 120_000
AI_VIDEO_TEXT_CHAR_LIMIT = 120_000


@dataclass(frozen=True)
class PaperCandidate:
    title: str
    year: int
    page_url: str
    pdf_url: str


class _PublicationParser(HTMLParser):
    _BLOCK_TAGS = {"article", "li", "tr", "section", "p", "div"}
    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "strong", "b"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict[str, object]] = []
        self._stack: list[dict[str, object]] = []
        self._current_anchor: str | None = None
        self._current_heading_depth = 0
        self._title_tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in self._BLOCK_TAGS:
            self._stack.append({"text": [], "titles": [], "headings": [], "links": []})
        if tag == "a":
            self._current_anchor = attrs_dict.get("href")
        if tag in self._HEADING_TAGS:
            self._current_heading_depth += 1
        class_names = set((attrs_dict.get("class") or "").split())
        if "article-title" in class_names or "publication-title" in class_names or "gsc_a_at" in class_names:
            self._title_tag_stack.append(tag)

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if not self._stack:
            self._stack.append({"text": [], "titles": [], "headings": [], "links": []})
        block = self._stack[-1]
        block["text"].append(text)
        if self._title_tag_stack:
            block["titles"].append(text)
        if self._current_heading_depth:
            block["headings"].append(text)
        if self._current_anchor:
            block["links"].append((self._current_anchor, text))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._current_anchor = None
        if tag in self._HEADING_TAGS and self._current_heading_depth:
            self._current_heading_depth -= 1
        if self._title_tag_stack and tag == self._title_tag_stack[-1]:
            self._title_tag_stack.pop()
        if tag in self._BLOCK_TAGS and self._stack:
            block = self._stack.pop()
            if block["text"] or block["links"]:
                self.blocks.append(block)
            if self._stack:
                parent = self._stack[-1]
                parent["text"].extend(block["text"])
                parent["titles"].extend(block["titles"])
                parent["headings"].extend(block["headings"])
                parent["links"].extend(block["links"])

    def close(self) -> None:
        super().close()
        while self._stack:
            block = self._stack.pop(0)
            if block["text"] or block["links"]:
                self.blocks.append(block)


def discover_lab_dirs(labs_root: Path) -> list[Path]:
    if not labs_root.exists():
        return []
    return sorted(
        (path for path in labs_root.iterdir() if (path / "link.txt").is_file()),
        key=lambda path: path.name.casefold(),
    )


def filter_bilibili_lab_dirs(lab_dirs: Iterable[Path]) -> list[Path]:
    return [lab_dir for lab_dir in lab_dirs if is_bilibili_url(read_lab_link(lab_dir) or "")]


def format_lab_progress(lab_dir: Path, current: int, total: int, phase: str) -> str:
    waiting = max(total - current, 0)
    return f"[lab {current}/{total}] {phase}: {lab_dir.name} | waiting: {waiting}"


def format_year_counts(papers: Iterable[PaperCandidate], min_year: int) -> str:
    counts = Counter(paper.year for paper in papers)
    max_year = max(counts.keys(), default=min_year)
    return ", ".join(f"{year}={counts.get(year, 0)}" for year in range(min_year, max_year + 1))


def safe_filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:120] or "paper"


def is_bilibili_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "bilibili.com" or host.endswith(".bilibili.com") or host == "b23.tv"


def is_probable_publication_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title).strip().lower()
    generic_titles = {
        "industry",
        "publications",
        "research",
        "selected publications",
        "selected research and publications",
    }
    if normalized in generic_titles:
        return False
    words = re.findall(r"[a-z0-9]+", normalized)
    return len(words) >= 4


def parse_publication_page(html: str, base_url: str, min_year: int = DEFAULT_MIN_YEAR) -> list[PaperCandidate]:
    candidates = _parse_bibtex_publications(html, base_url, min_year)
    parser = _PublicationParser()
    parser.feed(html)
    parser.close()

    seen: set[tuple[str, str]] = set()
    for paper in candidates:
        seen.add((safe_filename(paper.title), paper.pdf_url))
    for block in parser.blocks:
        text = " ".join(block["text"])
        year = _find_recent_year(text, min_year)
        if year is None:
            continue
        pdf_url = _find_pdf_url(block["links"], base_url)
        if not pdf_url and (block["titles"] or block["headings"]):
            pdf_url = _find_arxiv_pdf_url(text)
        if not pdf_url:
            continue
        title = _extract_title(block, pdf_url)
        if not is_probable_publication_title(title):
            continue
        key = (safe_filename(title), pdf_url)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(PaperCandidate(title=title, year=year, page_url=base_url, pdf_url=pdf_url))
    return candidates


def extract_rai_papers(html: str, base_url: str, min_year: int, timeout: int) -> list[PaperCandidate]:
    if "rai-inst.com" not in urlparse(base_url).netloc.lower():
        return []

    candidates: list[PaperCandidate] = []
    seen: set[tuple[str, str]] = set()
    for title, year, page_url in _iter_rai_resource_cards(html, base_url, min_year, timeout):
        paper = search_arxiv_for_title(
            title,
            page_url,
            min_year=min_year,
            timeout=min(timeout, RAI_ARXIV_SEARCH_TIMEOUT_SECONDS),
        )
        if paper is None or not _titles_match(title, paper.title):
            continue
        paper = PaperCandidate(title=title, year=year, page_url=page_url, pdf_url=paper.pdf_url)
        key = (safe_filename(paper.title), paper.pdf_url)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(paper)
    return candidates


def fetch_rai_wpgb_posts(base_url: str, offset: int, timeout: int) -> str:
    endpoint = f"https://rai-inst.com/?wpgb-ajax=refresh&_type=papers&_load_more={offset}"
    settings = {
        "is_main_query": False,
        "main_query": [],
        "permalink": "https://rai-inst.com/resources/",
        "facets": [1, 2, 6, 5, 4],
        "lang": "",
        "id": 1,
    }
    body = urlencode({"wpgb": json.dumps(settings, separators=(",", ":"))}).encode()
    request = Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": base_url,
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        data, response = read_url_with_retries(request, timeout=timeout)
    except (HTTPError, URLError, TimeoutError, IncompleteRead, ssl.SSLError):
        return ""
    charset = response.headers.get_content_charset() or "utf-8"
    try:
        payload = json.loads(data.decode(charset, errors="replace"))
    except json.JSONDecodeError:
        return ""
    posts = payload.get("posts", "")
    return posts if isinstance(posts, str) else ""


def search_arxiv_for_title(title: str, page_url: str, min_year: int, timeout: int) -> PaperCandidate | None:
    if not title:
        return None
    url = (
        "https://export.arxiv.org/api/query"
        f"?search_query=all:{quote_plus(title)}"
        "&start=0&max_results=3&sortBy=relevance&sortOrder=descending"
    )
    try:
        atom = fetch_text(url, timeout=timeout)
    except (HTTPError, URLError, TimeoutError, IncompleteRead, ssl.SSLError):
        return None
    papers = _parse_arxiv_atom_candidates(atom, page_url, min_year=min_year)
    for paper in papers:
        if _titles_match(title, paper.title):
            return paper
    return None


def _parse_bibtex_publications(html: str, base_url: str, min_year: int) -> list[PaperCandidate]:
    papers: list[PaperCandidate] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"<pre>\s*(@.*?})\s*</pre>", html, flags=re.DOTALL | re.IGNORECASE):
        entry = unescape(match.group(1))
        title = _extract_bibtex_field(entry, "title")
        year = _coerce_year(_extract_bibtex_field(entry, "year"))
        paper_url = _extract_bibtex_field(entry, "url")
        pdf_url = _normalize_pdf_url(paper_url, base_url) if paper_url else None
        if not title or year is None or year < min_year or not pdf_url:
            continue
        title = clean_title(title)
        key = (safe_filename(title), pdf_url)
        if key in seen:
            continue
        seen.add(key)
        papers.append(PaperCandidate(title=title, year=year, page_url=base_url, pdf_url=pdf_url))
    return papers


def extract_papers_from_ai_response(response_text: str, base_url: str, min_year: int = DEFAULT_MIN_YEAR) -> list[PaperCandidate]:
    data = _parse_json_from_text(response_text)
    if isinstance(data, dict):
        data = data.get("papers", [])
    if not isinstance(data, list):
        return []

    candidates: list[PaperCandidate] = []
    seen: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        title = clean_title(str(item.get("title", "")).strip())
        year = _coerce_year(item.get("year"))
        if not title or year is None or year < min_year:
            continue
        pdf_url = str(item.get("pdf_url") or item.get("pdf") or item.get("paper_url") or "").strip()
        page_url = str(item.get("url") or item.get("page_url") or base_url).strip()
        pdf_url = _normalize_pdf_url(pdf_url, base_url)
        if not pdf_url:
            continue
        page_url = urljoin(base_url, page_url) if page_url else base_url
        key = (safe_filename(title), pdf_url)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(PaperCandidate(title=title, year=year, page_url=page_url, pdf_url=pdf_url))
    return candidates


def extract_papers_from_video_text_response(
    response_text: str,
    base_url: str,
    min_year: int = DEFAULT_MIN_YEAR,
) -> list[PaperCandidate]:
    data = _parse_json_from_text(response_text)
    if isinstance(data, dict):
        data = data.get("papers", [])
    if not isinstance(data, list):
        return []

    candidates: list[PaperCandidate] = []
    seen: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        title = clean_title(str(item.get("title", "")).strip())
        year = _coerce_year(item.get("year"))
        if not title or year is None or year < min_year:
            continue
        paper_url = str(item.get("arxiv_url") or item.get("pdf_url") or item.get("paper_url") or "").strip()
        pdf_url = _normalize_pdf_url(paper_url, base_url)
        if not pdf_url:
            continue
        page_url = str(item.get("video_url") or item.get("url") or item.get("page_url") or base_url).strip()
        page_url = urljoin(base_url, page_url) if page_url else base_url
        key = (safe_filename(title), pdf_url)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(PaperCandidate(title=title, year=year, page_url=page_url, pdf_url=pdf_url))
    return candidates


def extract_papers_with_ai(html: str, base_url: str, min_year: int, timeout: int) -> list[PaperCandidate]:
    ai_url = os.environ.get("AI_BASE_URL") or os.environ.get("OPENAI_URL")
    ai_key = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    ai_model = os.environ.get("AI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5.5"
    if not ai_url:
        raise RuntimeError("AI_BASE_URL or OPENAI_URL is required for --extractor ai")

    print(
        f"[extract:ai] requesting paper links | model={ai_model} | endpoint={ai_url} | "
        f"html_chars={len(html)} | min_year={min_year}"
    )
    prompt = _build_ai_prompt(html, base_url, min_year)
    payload = {
        "model": ai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract publication metadata from lab publication pages. "
                    "Return JSON only. Do not include commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if ai_key:
        headers["Authorization"] = f"Bearer {ai_key}"
    request = Request(ai_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with open_url_with_retries(request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8", errors="replace"))
    content = _extract_chat_content(raw)
    papers = extract_papers_from_ai_response(content, base_url, min_year=min_year)
    print(f"[extract:ai] extracted {len(papers)} papers | by_year: {format_year_counts(papers, min_year)}")
    return papers


def extract_papers_from_bilibili_videos(
    video_text: str,
    base_url: str,
    min_year: int,
    timeout: int,
) -> list[PaperCandidate]:
    ai_url = os.environ.get("AI_BASE_URL") or os.environ.get("OPENAI_URL")
    ai_key = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    ai_model = os.environ.get("AI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5.5"
    if not ai_url:
        raise RuntimeError("AI_BASE_URL or OPENAI_URL is required for Bilibili AI extraction")

    print(
        f"[extract:bilibili-ai] requesting paper links | model={ai_model} | endpoint={ai_url} | "
        f"text_chars={len(video_text)} | min_year={min_year}"
    )
    payload = {
        "model": ai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract arXiv paper metadata from Bilibili video titles, descriptions, and metadata. "
                    "Return JSON only. Do not include commentary."
                ),
            },
            {"role": "user", "content": _build_bilibili_ai_prompt(video_text, base_url, min_year)},
        ],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if ai_key:
        headers["Authorization"] = f"Bearer {ai_key}"
    request = Request(ai_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with open_url_with_retries(request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8", errors="replace"))
    content = _extract_chat_content(raw)
    papers = extract_papers_from_video_text_response(content, base_url, min_year=min_year)
    print(f"[extract:bilibili-ai] extracted {len(papers)} papers | by_year: {format_year_counts(papers, min_year)}")
    return papers


def choose_candidates(
    html: str,
    base_url: str,
    min_year: int,
    timeout: int,
    extractor: str,
) -> list[PaperCandidate]:
    if extractor == "static":
        papers = extract_static_candidates(html, base_url, min_year=min_year, timeout=timeout)
        print(f"[extract:static] extracted {len(papers)} papers | by_year: {format_year_counts(papers, min_year)}")
        return papers
    if extractor == "ai":
        return extract_papers_with_ai(html, base_url, min_year=min_year, timeout=timeout)
    ai_candidates = extract_papers_with_ai(html, base_url, min_year=min_year, timeout=timeout)
    static_candidates = extract_static_candidates(html, base_url, min_year=min_year, timeout=timeout)
    print(
        f"[extract:static] extracted {len(static_candidates)} papers | "
        f"by_year: {format_year_counts(static_candidates, min_year)}"
    )
    merged = merge_candidates(ai_candidates, static_candidates)
    print(
        f"[extract:hybrid] merged {len(merged)} papers | "
        f"ai={len(ai_candidates)}, static={len(static_candidates)} | "
        f"by_year: {format_year_counts(merged, min_year)}"
    )
    return merged


def extract_static_candidates(html: str, base_url: str, min_year: int, timeout: int) -> list[PaperCandidate]:
    return merge_candidates(
        parse_publication_page(html, base_url, min_year=min_year),
        extract_rai_papers(html, base_url, min_year=min_year, timeout=timeout),
    )


def choose_bilibili_candidates(
    video_text: str,
    base_url: str,
    min_year: int,
    timeout: int,
    extractor: str,
) -> list[PaperCandidate]:
    static_candidates = parse_bilibili_video_text(video_text, base_url, min_year=min_year)
    if extractor == "static":
        print(
            f"[extract:bilibili-static] extracted {len(static_candidates)} papers | "
            f"by_year: {format_year_counts(static_candidates, min_year)}"
        )
        return static_candidates
    ai_candidates = extract_papers_from_bilibili_videos(video_text, base_url, min_year=min_year, timeout=timeout)
    if extractor == "ai":
        return ai_candidates
    print(
        f"[extract:bilibili-static] extracted {len(static_candidates)} papers | "
        f"by_year: {format_year_counts(static_candidates, min_year)}"
    )
    merged = merge_candidates(ai_candidates, static_candidates)
    print(
        f"[extract:bilibili-hybrid] merged {len(merged)} papers | "
        f"ai={len(ai_candidates)}, static={len(static_candidates)} | "
        f"by_year: {format_year_counts(merged, min_year)}"
    )
    return merged


def merge_candidates(*candidate_groups: Iterable[PaperCandidate]) -> list[PaperCandidate]:
    merged: list[PaperCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidates in candidate_groups:
        for paper in candidates:
            key = (safe_filename(paper.title), paper.pdf_url)
            if key in seen:
                continue
            seen.add(key)
            merged.append(paper)
    return merged


def filter_new_papers(lab_dir: Path, candidates: Iterable[PaperCandidate]) -> list[PaperCandidate]:
    manifest = load_manifest(lab_dir)
    known_urls = {item.get("pdf_url", "") for item in manifest}
    known_titles = {safe_filename(str(item.get("title", ""))) for item in manifest}
    existing_pdf_names = {path.name.lower() for path in (lab_dir / PDF_DIR_NAME).glob("*.pdf")}

    new_papers: list[PaperCandidate] = []
    for paper in candidates:
        pdf_name = Path(urlparse(paper.pdf_url).path).name.lower()
        if paper.pdf_url in known_urls:
            continue
        if safe_filename(paper.title) in known_titles:
            continue
        if pdf_name and pdf_name in existing_pdf_names:
            continue
        new_papers.append(paper)
    return sorted(new_papers, key=paper_output_sort_key)


def paper_output_sort_key(paper: PaperCandidate) -> tuple[str, str]:
    return (f"{paper.year}-{safe_filename(paper.title)}.pdf".casefold(), paper.pdf_url)


def load_manifest(lab_dir: Path) -> list[dict[str, object]]:
    path = lab_dir / MANIFEST_NAME
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def save_manifest(lab_dir: Path, papers: list[dict[str, object]]) -> None:
    path = lab_dir / MANIFEST_NAME
    path.write_text(json.dumps(papers, indent=2, sort_keys=True) + "\n")


def record_failed_paper(lab_dir: Path, paper: PaperCandidate) -> None:
    path = lab_dir / FAILED_NAME
    existing = path.read_text().splitlines() if path.exists() else []
    if paper.title in existing:
        return
    existing.append(paper.title)
    path.write_text("\n".join(existing) + "\n")


def record_failed_video(lab_dir: Path, video_url: str) -> None:
    path = lab_dir / FAILED_NAME
    existing = path.read_text().splitlines() if path.exists() else []
    if video_url in existing:
        return
    existing.append(video_url)
    path.write_text("\n".join(existing) + "\n")


def read_lab_link(lab_dir: Path) -> str | None:
    for line in (lab_dir / "link.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def fetch_text(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    data, response = read_url_with_retries(request, timeout=timeout)
    charset_getter = getattr(response.headers, "get_content_charset", None)
    charset = charset_getter() if charset_getter else None
    charset = charset or "utf-8"
    return data.decode(charset, errors="replace")


def fetch_publication_html(url: str, min_year: int, timeout: int) -> str:
    if not is_google_scholar_url(url):
        return fetch_text(url, timeout=timeout)

    pages: list[str] = []
    for page_index in range(GOOGLE_SCHOLAR_MAX_PAGES):
        page_url = google_scholar_page_url(url, cstart=page_index * GOOGLE_SCHOLAR_PAGE_SIZE)
        html = fetch_text(page_url, timeout=timeout)
        pages.append(html)
        years = _find_years(html)
        if not years or min(years) < min_year:
            break
    return "\n".join(pages)


def is_google_scholar_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == "scholar.google.com" and parsed.path == "/citations"


def google_scholar_page_url(url: str, cstart: int) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["pagesize"] = str(GOOGLE_SCHOLAR_PAGE_SIZE)
    params["cstart"] = str(cstart)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(params), parsed.fragment))


def download_pdf(url: str, destination: Path, timeout: int) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    data, _response = read_url_with_retries(request, timeout=timeout)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def read_url_with_retries(request: Request, timeout: int, attempts: int = DEFAULT_HTTP_ATTEMPTS):
    last_exc: Exception | None = None
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read(), response
        except (ssl.SSLError, URLError, TimeoutError, IncompleteRead) as exc:
            last_exc = exc
            if attempt >= attempts or not is_retryable_network_error(exc):
                raise
            print(f"[retry] HTTP request attempt {attempt}/{attempts} failed ({exc}); retrying", file=sys.stderr)
            time.sleep(min(2 ** (attempt - 1), 5))
    if last_exc:
        raise last_exc
    raise RuntimeError("HTTP retry loop did not run")


def open_url_with_retries(request: Request, timeout: int, attempts: int = DEFAULT_HTTP_ATTEMPTS):
    last_exc: Exception | None = None
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            return urlopen(request, timeout=timeout)
        except (ssl.SSLError, URLError, TimeoutError, IncompleteRead) as exc:
            last_exc = exc
            if attempt >= attempts or not is_retryable_network_error(exc):
                raise
            print(f"[retry] HTTP request attempt {attempt}/{attempts} failed ({exc}); retrying", file=sys.stderr)
            time.sleep(min(2 ** (attempt - 1), 5))
    if last_exc:
        raise last_exc
    raise RuntimeError("HTTP retry loop did not run")


def is_retryable_network_error(exc: BaseException) -> bool:
    if isinstance(exc, HTTPError):
        return 500 <= exc.code < 600
    if isinstance(exc, (ssl.SSLError, TimeoutError, IncompleteRead)):
        return True
    if isinstance(exc, URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLError):
            return True
        text = str(reason or exc).lower()
        return any(token in text for token in ("timed out", "timeout", "temporarily", "reset", "bad record mac"))
    return False


def fetch_bilibili_video_metadata(url: str, timeout: int, limit: int = BILIBILI_VIDEO_LIMIT) -> list[dict[str, object]]:
    playlist = _run_yt_dlp_json(
        ["--flat-playlist", "--dump-single-json", "--playlist-end", str(limit), "--no-warnings", url],
        timeout=timeout,
    )
    entries = playlist.get("entries", []) if isinstance(playlist, dict) else []
    videos: list[dict[str, object]] = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        video_url = _bilibili_entry_url(entry)
        if not video_url:
            videos.append(entry)
            continue
        try:
            full_entry = _run_yt_dlp_json(["--dump-single-json", "--skip-download", "--no-warnings", video_url], timeout=timeout)
        except (RuntimeError, subprocess.TimeoutExpired):
            full_entry = entry
        videos.append(full_entry if isinstance(full_entry, dict) else entry)
    return videos


def build_bilibili_video_text(metadata: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for index, item in enumerate(metadata, start=1):
        title = str(item.get("title") or "").strip()
        video_url = str(item.get("webpage_url") or item.get("url") or "").strip()
        upload_date = str(item.get("upload_date") or item.get("timestamp") or "").strip()
        description = str(item.get("description") or "").strip()
        tags = item.get("tags")
        if isinstance(tags, list):
            tags_text = ", ".join(str(tag) for tag in tags if tag)
        else:
            tags_text = ""
        parts = [f"Video {index}:"]
        if title:
            parts.append(f"Title: {title}")
        if video_url:
            parts.append(f"URL: {video_url}")
        if upload_date:
            parts.append(f"Upload date: {upload_date}")
        if tags_text:
            parts.append(f"Tags: {tags_text}")
        if description:
            parts.append(f"Description: {description}")
        chunks.append("\n".join(parts))
    return "\n\n".join(chunks)[:AI_VIDEO_TEXT_CHAR_LIMIT]


def parse_bilibili_video_text(video_text: str, base_url: str, min_year: int = DEFAULT_MIN_YEAR) -> list[PaperCandidate]:
    candidates: list[PaperCandidate] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5}(?:v\d+)?)", video_text):
        arxiv_id = match.group(1)
        year = 2000 + int(arxiv_id[:2])
        if year < min_year:
            continue
        pdf_url = _normalize_pdf_url(f"https://arxiv.org/abs/{arxiv_id}", base_url)
        if not pdf_url or pdf_url in seen:
            continue
        seen.add(pdf_url)
        title = _nearest_bilibili_title(video_text, match.start()) or f"arXiv {arxiv_id}"
        page_url = _nearest_bilibili_video_url(video_text, match.start()) or base_url
        candidates.append(PaperCandidate(title=clean_title(title), year=year, page_url=page_url, pdf_url=pdf_url))
    return candidates


def search_arxiv_for_bilibili_video(
    item: dict[str, object],
    min_year: int,
    timeout: int,
) -> PaperCandidate | None:
    query = _build_arxiv_query_from_bilibili_metadata(item)
    video_url = _bilibili_entry_url(item)
    if not query or not video_url:
        return None
    url = (
        "https://export.arxiv.org/api/query"
        f"?search_query=all:{quote_plus(query)}"
        "&start=0&max_results=3&sortBy=submittedDate&sortOrder=descending"
    )
    try:
        atom = fetch_text(url, timeout=timeout)
    except (HTTPError, URLError, TimeoutError, IncompleteRead, ssl.SSLError):
        return None
    papers = _parse_arxiv_atom_candidates(atom, video_url, min_year=min_year)
    return papers[0] if papers else None


def collect_lab(
    lab_dir: Path,
    min_year: int,
    timeout: int,
    dry_run: bool = False,
    extractor: str = "static",
) -> tuple[int, int]:
    link = read_lab_link(lab_dir)
    if not link:
        print(f"[skip] {lab_dir}: empty link.txt")
        return (0, 0)

    if is_bilibili_url(link):
        limit = int(os.environ.get("BILIBILI_VIDEO_LIMIT", BILIBILI_VIDEO_LIMIT))
        metadata = fetch_bilibili_video_metadata(link, timeout=timeout, limit=limit)
        video_text = build_bilibili_video_text(metadata)
        candidates = choose_bilibili_candidates(video_text, link, min_year=min_year, timeout=timeout, extractor=extractor)
        matched_video_keys = {
            video_key
            for paper in candidates
            if (video_key := _bilibili_video_key(paper.page_url)) is not None
        }
        searched_candidates: list[PaperCandidate] = []
        for item in metadata:
            video_url = _bilibili_entry_url(item)
            if not video_url:
                continue
            video_key = _bilibili_video_key(video_url)
            if video_key and video_key in matched_video_keys:
                continue
            paper = search_arxiv_for_bilibili_video(item, min_year=min_year, timeout=timeout)
            if paper:
                searched_candidates.append(paper)
                if video_key:
                    matched_video_keys.add(video_key)
        if searched_candidates:
            print(
                f"[extract:bilibili-arxiv-search] extracted {len(searched_candidates)} papers | "
                f"by_year: {format_year_counts(searched_candidates, min_year)}"
            )
            candidates = merge_candidates(candidates, searched_candidates)
        if not dry_run:
            matched_video_keys = {
                video_key
                for paper in candidates
                if (video_key := _bilibili_video_key(paper.page_url)) is not None
            }
            matched_video_urls = {paper.page_url.rstrip("/") for paper in candidates}
            for item in metadata:
                video_url = _bilibili_entry_url(item)
                if not video_url:
                    continue
                video_key = _bilibili_video_key(video_url)
                if video_url.rstrip("/") in matched_video_urls or (video_key and video_key in matched_video_keys):
                    continue
                record_failed_video(lab_dir, video_url)
    else:
        html = fetch_publication_html(link, min_year=min_year, timeout=timeout)
        candidates = choose_candidates(html, link, min_year=min_year, timeout=timeout, extractor=extractor)
    new_papers = filter_new_papers(lab_dir, candidates)
    print(
        f"[scan] {lab_dir.name}: {len(candidates)} recent PDFs, {len(new_papers)} new | "
        f"found_by_year: {format_year_counts(candidates, min_year)} | "
        f"new_by_year: {format_year_counts(new_papers, min_year)}"
    )

    manifest = load_manifest(lab_dir)
    for paper in new_papers:
        filename = f"{paper.year}-{safe_filename(paper.title)}.pdf"
        pdf_path = lab_dir / PDF_DIR_NAME / filename
        record = asdict(paper)
        record["pdf_path"] = str(pdf_path.relative_to(lab_dir))
        if dry_run:
            print(f"[dry-run] {paper.title} -> {pdf_path}")
        else:
            try:
                download_pdf(paper.pdf_url, pdf_path, timeout=timeout)
            except (HTTPError, URLError, TimeoutError, IncompleteRead, InvalidURL, ssl.SSLError) as exc:
                record_failed_paper(lab_dir, paper)
                print(f"[error] {paper.title}: {exc}", file=sys.stderr)
                continue
            manifest.append(record)
            save_manifest(lab_dir, manifest)
            print(f"[download] {paper.title} -> {pdf_path}")
            time.sleep(0.5)
    return (len(candidates), len(new_papers))


def _process_lab(
    lab_dir: Path,
    index: int,
    total_labs: int,
    min_year: int,
    timeout: int,
    dry_run: bool,
    extractor: str,
) -> bool:
    print(format_lab_progress(lab_dir, index, total_labs, "start"))
    try:
        candidates_count, new_count = collect_lab(
            lab_dir,
            min_year=min_year,
            timeout=timeout,
            dry_run=dry_run,
            extractor=extractor,
        )
        print(
            f"{format_lab_progress(lab_dir, index, total_labs, 'done')} | "
            f"found: {candidates_count}, new: {new_count}"
        )
        return True
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, IncompleteRead, InvalidURL, ssl.SSLError) as exc:
        print(format_lab_progress(lab_dir, index, total_labs, "failed"), file=sys.stderr)
        print(f"[error] {lab_dir.name}: {exc}", file=sys.stderr)
        return False


def run_labs(
    lab_dirs: list[Path],
    min_year: int,
    timeout: int,
    dry_run: bool,
    extractor: str,
    workers: int = DEFAULT_WORKERS,
) -> int:
    total_labs = len(lab_dirs)
    workers = max(1, workers)
    print(f"[progress] queued {total_labs} labs for scanning")

    if workers == 1 or total_labs == 1:
        failures = 0
        for index, lab_dir in enumerate(lab_dirs, start=1):
            if not _process_lab(lab_dir, index, total_labs, min_year, timeout, dry_run, extractor):
                failures += 1
        print(f"[progress] finished {total_labs - failures}/{total_labs} labs; failed: {failures}")
        return failures

    failures = 0
    with ThreadPoolExecutor(max_workers=min(workers, total_labs)) as executor:
        futures = [
            executor.submit(_process_lab, lab_dir, index, total_labs, min_year, timeout, dry_run, extractor)
            for index, lab_dir in enumerate(lab_dirs, start=1)
        ]
        for future in as_completed(futures):
            if not future.result():
                failures += 1

    print(f"[progress] finished {total_labs - failures}/{total_labs} labs; failed: {failures}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download new lab papers listed on publication pages.")
    parser.add_argument("--labs-root", type=Path, default=Path("labs"))
    parser.add_argument("--lab", default=None, help="Only process one lab folder name under --labs-root.")
    parser.add_argument("--min-year", type=int, default=DEFAULT_MIN_YEAR)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Number of lab folders to scan in parallel.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N labs.")
    parser.add_argument("--bilibili-only", action="store_true", help="Only process lab folders whose link.txt points to Bilibili.")
    parser.add_argument("--bilibili-cookies", default=None, help="Path to a cookies.txt file for Bilibili yt-dlp requests.")
    parser.add_argument(
        "--bilibili-cookies-from-browser",
        default=None,
        help="Browser name for yt-dlp --cookies-from-browser, for example: chrome.",
    )
    parser.add_argument(
        "--extractor",
        choices=("static", "ai", "hybrid"),
        default="static",
        help="Use static HTML parsing, AI extraction, or AI with static fallback.",
    )
    args = parser.parse_args(argv)

    if args.bilibili_cookies:
        os.environ["BILIBILI_COOKIES"] = args.bilibili_cookies
    if args.bilibili_cookies_from_browser:
        os.environ["BILIBILI_COOKIES_FROM_BROWSER"] = args.bilibili_cookies_from_browser
    if args.bilibili_only and not os.environ.get("BILIBILI_COOKIES") and not os.environ.get("BILIBILI_COOKIES_FROM_BROWSER"):
        os.environ["BILIBILI_COOKIES_FROM_BROWSER"] = "chrome"

    lab_dirs = discover_lab_dirs(args.labs_root)
    if args.lab is not None:
        lab_dirs = [lab_dir for lab_dir in lab_dirs if lab_dir.name == args.lab]
    if args.bilibili_only:
        lab_dirs = filter_bilibili_lab_dirs(lab_dirs)
    if args.limit is not None:
        lab_dirs = lab_dirs[: args.limit]
    if not lab_dirs:
        print(f"No lab directories with link.txt found under {args.labs_root}", file=sys.stderr)
        return 1

    failures = run_labs(
        lab_dirs,
        min_year=args.min_year,
        timeout=args.timeout,
        dry_run=args.dry_run,
        extractor=args.extractor,
        workers=args.workers,
    )
    return 1 if failures else 0


def _find_recent_year(text: str, min_year: int) -> int | None:
    years = _find_years(text)
    years = [year for year in years if year >= min_year]
    return max(years) if years else None


def _find_years(text: str) -> list[int]:
    return [int(match) for match in re.findall(r"\b(20\d{2})\b", text)]


def _find_pdf_url(links: object, base_url: str) -> str | None:
    for href, label in links:
        pdf_url = _normalize_pdf_url(href, base_url)
        lower_href = href.lower()
        lower_label = label.lower()
        if pdf_url and (lower_href.endswith(".pdf") or ".pdf" in lower_href or "arxiv.org/abs/" in lower_href):
            return pdf_url
        if pdf_url and "pdf" == lower_label:
            return pdf_url
    return None


def _parse_rai_resource_cards(html: str, base_url: str, min_year: int) -> list[tuple[str, int, str]]:
    cards: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r"<article\b.*?</article>", html, flags=re.DOTALL | re.IGNORECASE):
        card = match.group(0)
        if "resources/papers/" not in card:
            continue
        title_match = re.search(
            r"<h3\b[^>]*>.*?<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>.*?</h3>",
            card,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not title_match:
            continue
        page_url = urljoin(base_url, unescape(title_match.group(1)).strip())
        title = clean_title(_strip_html(title_match.group(2)))
        year = _find_recent_year(card, min_year)
        if not title or year is None or not is_probable_publication_title(title):
            continue
        if page_url in seen:
            continue
        seen.add(page_url)
        cards.append((title, year, page_url))
    return cards


def _iter_rai_resource_cards(html: str, base_url: str, min_year: int, timeout: int) -> list[tuple[str, int, str]]:
    cards = _parse_rai_resource_cards(html, base_url, min_year)
    seen = {page_url for _, _, page_url in cards}
    all_cards = list(cards)
    offset = RAI_LOAD_MORE_PAGE_SIZE

    for _ in range(RAI_LOAD_MORE_MAX_PAGES):
        more_html = fetch_rai_wpgb_posts(base_url, offset=offset, timeout=timeout)
        offset += RAI_LOAD_MORE_PAGE_SIZE
        if not more_html:
            break
        page_cards = _parse_rai_resource_cards(more_html, base_url, min_year)
        if not page_cards:
            break
        for title, year, page_url in page_cards:
            if page_url in seen:
                continue
            seen.add(page_url)
            all_cards.append((title, year, page_url))
        if max((year for _, year, _ in page_cards), default=0) < min_year:
            break

    return all_cards


def _strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return unescape(" ".join(value.split()))


def _titles_match(left: str, right: str) -> bool:
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens)) >= 0.72


def _title_tokens(title: str) -> set[str]:
    stop_words = {"a", "an", "and", "for", "from", "in", "of", "on", "the", "to", "using", "via", "with"}
    return {token for token in re.findall(r"[a-z0-9]+", title.lower()) if token not in stop_words}


def _find_arxiv_pdf_url(text: str) -> str | None:
    match = re.search(r"\barxiv\s*:\s*(\d{4}\.\d{4,5}(?:v\d+)?)\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    return _normalize_pdf_url(match.group(1), "https://arxiv.org/")


def _normalize_pdf_url(url: str, base_url: str) -> str | None:
    if not url:
        return None
    arxiv_id_match = re.fullmatch(r"(?:arxiv:)?\s*(\d{4}\.\d{4,5}(?:v\d+)?)", url.strip(), flags=re.IGNORECASE)
    if arxiv_id_match:
        return f"https://arxiv.org/pdf/{arxiv_id_match.group(1)}.pdf"
    absolute_url = urljoin(base_url, url)
    lower_url = absolute_url.lower()
    if "arxiv.org/abs/" in lower_url:
        paper_id = absolute_url.rstrip("/").split("/")[-1]
        return f"https://arxiv.org/pdf/{paper_id}.pdf" if _is_arxiv_id(paper_id) else None
    if "arxiv.org/pdf/" in lower_url:
        paper_id = absolute_url.rstrip("/").split("/")[-1]
        paper_id = re.sub(r"\.pdf$", "", paper_id, flags=re.IGNORECASE)
        return f"https://arxiv.org/pdf/{paper_id}.pdf" if _is_arxiv_id(paper_id) else None
    if lower_url.endswith(".pdf") or ".pdf" in lower_url:
        return _quote_url_path(absolute_url)
    return None


def _is_arxiv_id(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", value.strip(), flags=re.IGNORECASE))


def _quote_url_path(url: str) -> str:
    parsed = urlparse(url)
    path = quote(parsed.path, safe="/:%")
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


def _extract_bibtex_field(entry: str, field_name: str) -> str | None:
    match = re.search(rf"\b{re.escape(field_name)}\s*=\s*", entry, flags=re.IGNORECASE)
    if not match:
        return None
    index = match.end()
    while index < len(entry) and entry[index].isspace():
        index += 1
    if index >= len(entry):
        return None
    if entry[index] == "{":
        value, _ = _read_balanced_braces(entry, index)
        return value.strip() if value is not None else None
    if entry[index] == '"':
        end = entry.find('"', index + 1)
        return entry[index + 1 : end].strip() if end != -1 else None
    end_match = re.search(r"[,}\n]", entry[index:])
    end = index + end_match.start() if end_match else len(entry)
    return entry[index:end].strip()


def _read_balanced_braces(text: str, start: int) -> tuple[str | None, int]:
    if start >= len(text) or text[start] != "{":
        return (None, start)
    depth = 0
    value: list[str] = []
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
            if depth > 1:
                value.append(char)
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return ("".join(value), index + 1)
            value.append(char)
            continue
        value.append(char)
    return (None, start)


def _extract_title(block: dict[str, object], pdf_url: str) -> str:
    titles = [str(part) for part in block["titles"] if len(str(part)) > 8]
    if titles:
        return clean_title(titles[0])
    headings = [str(part) for part in block["headings"] if len(str(part)) > 8]
    if headings:
        return clean_title(headings[0])
    text = " ".join(str(part) for part in block["text"])
    text = re.sub(r"\b(19|20)\d{2}\b.*$", "", text).strip()
    basename = Path(urlparse(pdf_url).path).stem
    return clean_title(text or basename)


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip(" -:|")
    title = _trim_author_tail(title)
    title = re.sub(r"\s+In\s+[A-Z][A-Za-z0-9 -]+$", "", title)
    return title[:180] or "Untitled Paper"


def _trim_author_tail(title: str) -> str:
    if "," not in title:
        return title
    prefix = title.split(",", 1)[0].strip()
    words = prefix.split()
    if len(words) < 5:
        return title
    if not (_is_capitalized_word(words[-1]) and _is_capitalized_word(words[-2])):
        return title

    kept = words[:-2]
    protected_title_endings = {
        "control",
        "incentives",
        "manipulation",
        "play",
        "prediction",
        "reality",
        "rewards",
        "synthesis",
        "touch",
    }
    return " ".join(kept) or title


def _is_capitalized_word(word: str) -> bool:
    return bool(re.match(r"^[A-Z][\w'`-]+$", word))


def _parse_json_from_text(text: str) -> object:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            print(f"[extract:json] malformed fenced JSON ignored: {exc}", file=sys.stderr)
            return []
    start_positions = [pos for pos in (text.find("["), text.find("{")) if pos != -1]
    if not start_positions:
        return []
    start = min(start_positions)
    end = max(text.rfind("]"), text.rfind("}"))
    if end <= start:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        print(f"[extract:json] malformed JSON ignored: {exc}", file=sys.stderr)
        return []


def _coerce_year(value: object) -> int | None:
    if isinstance(value, int):
        return value
    match = re.search(r"\b(20\d{2})\b", str(value))
    return int(match.group(1)) if match else None


def _build_ai_prompt(html: str, base_url: str, min_year: int) -> str:
    compact_html = re.sub(r"\s+", " ", html)[:AI_HTML_CHAR_LIMIT]
    return f"""
Extract papers from this lab publication page.

Rules:
- Only include papers from {min_year} or later.
- Prefer a direct PDF URL.
- If a paper link is an arXiv abs URL, include that URL as pdf_url; the caller will normalize it.
- Ignore talks, news, section headings, videos, jobs, and generic research categories.
- Return JSON only as an array of objects with exactly these keys:
  title, year, url, pdf_url

Base URL: {base_url}

HTML:
{compact_html}
""".strip()


def _build_bilibili_ai_prompt(video_text: str, base_url: str, min_year: int) -> str:
    compact_text = re.sub(r"\n{3,}", "\n\n", video_text)[:AI_VIDEO_TEXT_CHAR_LIMIT]
    return f"""
Extract arXiv papers mentioned by these Bilibili videos.

Rules:
- Only include papers from {min_year} or later.
- Prefer explicit arXiv URLs or IDs from the title, description, tags, or subtitles.
- If a video summarizes multiple papers, return every paper you can identify.
- Ignore channel names, playlists, generic AI news, sponsorships, and non-paper topics.
- Return JSON only as an array of objects with exactly these keys:
  title, year, video_url, arxiv_url

Bilibili channel URL: {base_url}

Video metadata:
{compact_text}
""".strip()


def _run_yt_dlp_json(args: list[str], timeout: int) -> object:
    command = ["yt-dlp", *_yt_dlp_auth_args(), *args]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is required for Bilibili channel extraction") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        if "412" in message and "bilibili" in " ".join(command).lower():
            message = (
                f"{message}\n"
                "Bilibili often blocks anonymous yt-dlp requests. Try one of:\n"
                "  python3 labs/download_paper.py --bilibili-only --dry-run --bilibili-cookies-from-browser chrome\n"
                "  python3 labs/download_paper.py --bilibili-only --dry-run --bilibili-cookies /path/to/bilibili-cookies.txt"
            )
        raise RuntimeError(f"yt-dlp failed: {message}") from exc
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("yt-dlp returned invalid JSON") from exc


def _yt_dlp_auth_args() -> list[str]:
    cookies_path = os.environ.get("BILIBILI_COOKIES")
    if cookies_path:
        return ["--cookies", cookies_path]
    cookies_browser = os.environ.get("BILIBILI_COOKIES_FROM_BROWSER")
    if cookies_browser:
        return ["--cookies-from-browser", cookies_browser]
    return []


def _bilibili_entry_url(entry: dict[str, object]) -> str | None:
    raw_url = str(entry.get("webpage_url") or entry.get("url") or entry.get("id") or "").strip()
    if not raw_url:
        return None
    if raw_url.startswith(("http://", "https://")):
        return raw_url
    if raw_url.startswith("BV") or raw_url.startswith("av"):
        return f"https://www.bilibili.com/video/{raw_url}"
    return raw_url


def _bilibili_video_key(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    for part in path.split("/"):
        if part.startswith("BV") or part.startswith("av"):
            return part.rstrip("/")
    return None


def _build_arxiv_query_from_bilibili_metadata(item: dict[str, object]) -> str | None:
    parts = [
        str(item.get("title") or ""),
        str(item.get("description") or ""),
    ]
    tags = item.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    text = " ".join(parts)
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text)
    stop_words = {
        "and",
        "arxiv",
        "bilibili",
        "paper",
        "papers",
        "reading",
        "share",
        "sharing",
        "the",
        "video",
        "with",
    }
    kept: list[str] = []
    seen: set[str] = set()
    for word in words:
        normalized = word.lower().strip("-")
        if normalized in stop_words or normalized in seen:
            continue
        seen.add(normalized)
        kept.append(word)
        if len(kept) >= 8:
            break
    return " ".join(kept) if len(kept) >= 3 else None


def _parse_arxiv_atom_candidates(atom: str, video_url: str, min_year: int) -> list[PaperCandidate]:
    try:
        root = ElementTree.fromstring(atom)
    except ElementTree.ParseError:
        return []
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    candidates: list[PaperCandidate] = []
    for entry in root.findall("atom:entry", namespace):
        title = _xml_child_text(entry, "atom:title", namespace)
        paper_id = _xml_child_text(entry, "atom:id", namespace)
        published = _xml_child_text(entry, "atom:published", namespace)
        year = _coerce_year(published)
        pdf_url = _normalize_pdf_url(paper_id or "", video_url)
        if not title or year is None or year < min_year or not pdf_url:
            continue
        candidates.append(PaperCandidate(clean_title(title), year, video_url, pdf_url))
    return candidates


def _xml_child_text(node: ElementTree.Element, path: str, namespace: dict[str, str]) -> str | None:
    child = node.find(path, namespace)
    if child is None or child.text is None:
        return None
    return " ".join(child.text.split())


def _nearest_bilibili_title(text: str, position: int) -> str | None:
    prefix = text[:position]
    matches = list(re.finditer(r"^Title:\s*(.+)$", prefix, flags=re.MULTILINE))
    return matches[-1].group(1).strip() if matches else None


def _nearest_bilibili_video_url(text: str, position: int) -> str | None:
    prefix = text[:position]
    matches = list(re.finditer(r"^URL:\s*(https?://\S+)$", prefix, flags=re.MULTILINE))
    return matches[-1].group(1).strip() if matches else None


def _extract_chat_content(raw: object) -> str:
    if not isinstance(raw, dict):
        return ""
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
    output = raw.get("output_text")
    return output if isinstance(output, str) else ""


if __name__ == "__main__":
    raise SystemExit(main())
