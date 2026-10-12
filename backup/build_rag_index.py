from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labs.download_paper import safe_filename


RAG_INDEX_DIR_NAME = "rag_index"
EMBEDDING_DIMS = 384
CHUNK_FIELDS = [
    "abstract",
    "tldr",
    "problem",
    "motivation",
    "method",
    "results",
    "benchmark_and_evaluation",
    "embodiment_and_generalization",
    "implementation_notes",
    "limitations",
    "comparison_summary",
    "failure_modes",
    "discussion_notes",
]


def discover_summary_json_files(labs_root: Path) -> list[Path]:
    return sorted(labs_root.glob("*/summary_json/*.json"), key=lambda path: path.as_posix().casefold())


def build_rag_index(labs_root: Path, output_dir: Path | None = None) -> dict[str, int]:
    output_dir = output_dir or labs_root / RAG_INDEX_DIR_NAME
    papers: list[dict[str, object]] = []
    chunks: list[dict[str, object]] = []
    embeddings: list[dict[str, object]] = []
    paper_embeddings: list[dict[str, object]] = []

    for summary_path in discover_summary_json_files(labs_root):
        summary = _load_json_object(summary_path)
        if summary is None:
            continue
        lab_dir = summary_path.parents[1]
        paper = _paper_record_for_summary(labs_root, lab_dir, summary_path, summary)
        papers.append(paper)
        paper_embeddings.append({"paper_id": paper["paper_id"], "embedding": hash_embed(_paper_filter_text(paper))})
        for chunk in _chunks_for_paper(paper, summary):
            chunks.append(chunk)
            embeddings.append({"chunk_id": chunk["chunk_id"], "embedding": hash_embed(str(chunk["text"]))})

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "papers.jsonl", papers)
    _write_jsonl(output_dir / "chunks.jsonl", chunks)
    _write_jsonl(output_dir / "embeddings.jsonl", embeddings)
    _write_jsonl(output_dir / "paper_embeddings.jsonl", paper_embeddings)
    return {"papers": len(papers), "chunks": len(chunks)}


def search_index(
    index_dir: Path,
    query: str = "",
    keyword: str = "",
    top_k: int = 10,
) -> list[dict[str, object]]:
    papers = _read_jsonl(index_dir / "papers.jsonl")
    chunks = _read_jsonl(index_dir / "chunks.jsonl")
    embeddings = {str(item.get("chunk_id")): item.get("embedding") for item in _read_jsonl(index_dir / "embeddings.jsonl")}
    paper_embeddings = {
        str(item.get("paper_id")): item.get("embedding")
        for item in _read_jsonl(index_dir / "paper_embeddings.jsonl")
    }
    query_text = " ".join(part for part in [keyword, query] if part).strip()
    if not query_text:
        return []
    query_embedding = hash_embed(query_text)
    keyword_terms = _tokens(keyword)

    chunks_by_paper: dict[str, list[dict[str, object]]] = {}
    for chunk in chunks:
        paper_id = str(chunk.get("paper_id") or "")
        if paper_id:
            chunks_by_paper.setdefault(paper_id, []).append(chunk)

    scored: list[dict[str, object]] = []
    for paper in papers:
        paper_id = str(paper.get("paper_id") or "")
        if not paper_id:
            continue
        paper_keywords = [str(value).lower() for value in paper.get("paper_keywords", []) if value]
        paper_embedding = paper_embeddings.get(paper_id)
        if isinstance(paper_embedding, list):
            score = cosine_similarity(query_embedding, [float(value) for value in paper_embedding])
        else:
            score = cosine_similarity(query_embedding, hash_embed(_paper_filter_text(paper)))
        if keyword_terms and any(all(term in _tokens(paper_keyword) for term in keyword_terms) for paper_keyword in paper_keywords):
            score += 1.0

        supporting_chunks: list[dict[str, object]] = []
        for chunk in chunks_by_paper.get(paper_id, []):
            chunk_embedding = embeddings.get(str(chunk.get("chunk_id")))
            if not isinstance(chunk_embedding, list):
                continue
            chunk_score = cosine_similarity(query_embedding, [float(value) for value in chunk_embedding])
            chunk_score += lexical_overlap_score(query_text, str(chunk.get("text") or ""))
            if chunk_score <= 0:
                continue
            supporting_chunks.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "section": chunk.get("section"),
                    "score": round(chunk_score, 6),
                    "text": chunk.get("text"),
                }
            )
        supporting_chunks.sort(key=lambda item: -float(item["score"]))
        if supporting_chunks:
            score += float(supporting_chunks[0]["score"]) * 0.25
        if score <= 0:
            continue
        scored.append(
            {
                "paper_id": paper_id,
                "title": paper.get("title"),
                "year": paper.get("year"),
                "lab": paper.get("lab"),
                "pdf_url": paper.get("pdf_url"),
                "page_url": paper.get("page_url"),
                "abstract": paper.get("abstract"),
                "score": round(score, 6),
                "paper_keywords": paper.get("paper_keywords", []),
                "index_tags": paper.get("index_tags", {}),
                "supporting_chunks": supporting_chunks[:3],
            }
        )
    scored.sort(key=lambda item: (-float(item["score"]), str(item["title"])))
    return scored[:top_k]


def _paper_filter_text(paper: dict[str, object]) -> str:
    parts = [
        paper.get("title"),
        paper.get("abstract"),
        paper.get("paper_keywords"),
        paper.get("index_tags"),
    ]
    return " ".join(_value_to_text(part) for part in parts if part)


def search_chunks(
    index_dir: Path,
    query: str = "",
    keyword: str = "",
    top_k: int = 10,
) -> list[dict[str, object]]:
    chunks = _read_jsonl(index_dir / "chunks.jsonl")
    embeddings = {str(item.get("chunk_id")): item.get("embedding") for item in _read_jsonl(index_dir / "embeddings.jsonl")}
    query_text = " ".join(part for part in [keyword, query] if part).strip()
    if not query_text:
        return []
    query_embedding = hash_embed(query_text)
    keyword_terms = _tokens(keyword)

    scored: list[dict[str, object]] = []
    for chunk in chunks:
        chunk_embedding = embeddings.get(str(chunk.get("chunk_id")))
        if not isinstance(chunk_embedding, list):
            continue
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        paper_keywords = [str(value).lower() for value in metadata.get("paper_keywords", []) if value]
        score = cosine_similarity(query_embedding, [float(value) for value in chunk_embedding])
        score += lexical_overlap_score(query_text, str(chunk.get("text") or ""))
        if keyword_terms and any(all(term in _tokens(paper_keyword) for term in keyword_terms) for paper_keyword in paper_keywords):
            score += 1.0
        if score <= 0:
            continue
        scored.append(
            {
                "paper_id": chunk.get("paper_id"),
                "chunk_id": chunk.get("chunk_id"),
                "title": metadata.get("title"),
                "year": metadata.get("year"),
                "lab": metadata.get("lab"),
                "section": chunk.get("section"),
                "score": round(score, 6),
                "text": chunk.get("text"),
                "paper_keywords": metadata.get("paper_keywords", []),
            }
        )
    scored.sort(key=lambda item: (-float(item["score"]), str(item["title"]), str(item["section"])))
    return scored[:top_k]


def hash_embed(text: str, dims: int = EMBEDDING_DIMS) -> list[float]:
    vector = [0.0] * dims
    for token in _tokens(text):
        vector[fnv1a_32(token) % dims] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def fnv1a_32(text: str) -> int:
    value = 2166136261
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def lexical_overlap_score(query: str, text: str) -> float:
    query_terms = set(_tokens(query))
    text_terms = set(_tokens(text))
    if not query_terms or not text_terms:
        return 0.0
    return len(query_terms & text_terms) / len(query_terms)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _paper_record_for_summary(
    labs_root: Path,
    lab_dir: Path,
    summary_path: Path,
    summary: dict[str, object],
) -> dict[str, object]:
    manifest_paper = _match_manifest_paper(lab_dir, summary_path)
    title = str(manifest_paper.get("title") or _title_from_summary_filename(summary_path))
    year = manifest_paper.get("year") or _year_from_summary_filename(summary_path)
    pdf_url = str(manifest_paper.get("pdf_url") or "")
    page_url = str(manifest_paper.get("page_url") or "")
    paper_id = stable_paper_id(str(lab_dir.name), title, str(year), pdf_url or page_url)
    return {
        "paper_id": paper_id,
        "title": title,
        "year": year,
        "lab": lab_dir.name,
        "pdf_url": pdf_url,
        "page_url": page_url,
        "pdf_path": str(manifest_paper.get("pdf_path") or ""),
        "abstract": str(summary.get("abstract") or ""),
        "paper_keywords": _string_list(summary.get("keywords_and_features")),
        "index_tags": summary.get("index_tags") if isinstance(summary.get("index_tags"), dict) else {},
        "summary_json_path": str(summary_path.relative_to(labs_root)),
    }


def stable_paper_id(lab: str, title: str, year: str, url: str) -> str:
    arxiv = _arxiv_id(url)
    if arxiv:
        return f"arxiv:{arxiv}"
    digest = hashlib.sha1(f"{lab}|{title}|{year}|{url}".encode("utf-8")).hexdigest()[:12]
    return f"paper:{digest}"


def _chunks_for_paper(paper: dict[str, object], summary: dict[str, object]) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    for section in CHUNK_FIELDS:
        text = _value_to_text(summary.get(section))
        if not text:
            continue
        chunk_id = f"{paper['paper_id']}:{section}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "paper_id": paper["paper_id"],
                "section": section,
                "text": text,
                "metadata": {
                    "title": paper["title"],
                    "year": paper["year"],
                    "lab": paper["lab"],
                    "paper_keywords": paper["paper_keywords"],
                    "index_tags": paper["index_tags"],
                },
            }
        )
    return chunks


def _match_manifest_paper(lab_dir: Path, summary_path: Path) -> dict[str, object]:
    manifest_path = lab_dir / "papers.json"
    papers = _load_json_array(manifest_path)
    stem = summary_path.stem
    for paper in papers:
        year = str(paper.get("year", "unknown"))
        title = str(paper.get("title", "paper"))
        if stem == f"{year}-{safe_filename(title)}":
            return paper
    return papers[0] if len(papers) == 1 else {}


def _value_to_text(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return " ".join(part for part in (_value_to_text(item) for item in value) if part)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = _value_to_text(item)
            if text:
                parts.append(f"{key}: {text}")
        return " ".join(parts)
    return str(value)


def _load_json_object(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _load_json_array(path: Path) -> list[dict[str, object]]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _write_jsonl(path: Path, items: Iterable[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value if item] if isinstance(value, list) else []


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9+.-]*", text.lower())


def _arxiv_id(url: str) -> str | None:
    match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", url)
    return match.group(1) if match else None


def _year_from_summary_filename(path: Path) -> str:
    match = re.match(r"(\d{4})-", path.stem)
    return match.group(1) if match else "unknown"


def _title_from_summary_filename(path: Path) -> str:
    return re.sub(r"^\d{4}-", "", path.stem).replace("-", " ").strip() or "Unknown title"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and query a small RAG index from summarized lab papers.")
    parser.add_argument("--labs-root", type=Path, default=Path("labs"))
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--query", default="", help="Search requirement text after building or loading the index.")
    parser.add_argument("--keyword", default="", help="Search paper-provided keywords after building or loading the index.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--search-only", action="store_true", help="Do not rebuild before searching.")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or args.labs_root / RAG_INDEX_DIR_NAME
    if not args.search_only:
        stats = build_rag_index(args.labs_root, output_dir)
        print(f"[rag:index] papers={stats['papers']} chunks={stats['chunks']} -> {output_dir}")
        return 0
    if args.query or args.keyword:
        for result in search_index(output_dir, query=args.query, keyword=args.keyword, top_k=args.top_k):
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
