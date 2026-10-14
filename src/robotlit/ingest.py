import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from .contracts import DocumentRef, SourceRecord
from .db import blocks, chunks, documents, generations, new_id, papers, source_files, summaries
from .titles import paper_url, pdf_title, video_record


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for piece in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        temporary = Path(tmp.name)
        json.dump(payload, tmp, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Ingestor:
    def __init__(self, repo, settings):
        self.repo, self.settings = repo, settings
        self._title_cache = {}

    def root(self, root_id):
        if root_id not in self.settings.source_roots:
            raise ValueError("Unknown configured source root")
        root = self.settings.source_roots[root_id]
        if not root.is_dir():
            raise ValueError(f"Source root does not exist: {root}")
        return root

    def inventory(self, root_id, limit=None):
        root = self.root(root_id)
        if limit is not None and limit < 1:
            raise ValueError("Limit must be positive")
        metadata, paper_titles = {}, {}
        for manifest in sorted(root.glob("*/papers.json")):
            try:
                rows = json.loads(manifest.read_text())
                if not isinstance(rows, list):
                    continue
                for item in rows:
                    if not isinstance(item, dict) or not item.get("pdf_path"):
                        continue
                    path = (manifest.parent / item["pdf_path"]).resolve()
                    if path.is_relative_to(root):
                        metadata[path] = item
                    if item.get("title") and item.get("pdf_url") and not video_record(item) and not re.search(r'[\u3400-\u9fff]', item['title']):
                        paper_titles[paper_url(item['pdf_url'])] = item['title']
            except (ValueError, OSError):
                continue
        found = []
        for path in sorted(root.rglob("*.pdf")):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            stat = path.stat()
            info = metadata.get(path.resolve(), {})
            title = info.get("paper_title") or info.get("title") or re.sub(r'^\d{4}-', '', path.stem)
            title_source = "manifest" if info.get("paper_title") or info.get("title") else "filename"
            if not info.get("paper_title") and (video_record(info) or re.search(r'[\u3400-\u9fff]', title)):
                known = paper_titles.get(paper_url(info.get('pdf_url')))
                key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
                if known:
                    title, title_source = known, "manifest"
                else:
                    if key not in self._title_cache:
                        self._title_cache[key] = pdf_title(path)
                    title = self._title_cache[key] or re.sub(r'^\d{4}-', '', path.stem)
                    title_source = "pdf" if self._title_cache[key] else "filename"
            summary = path.parent.parent / "summary" / (path.stem + ".md")
            found.append(SourceRecord(root_id=root_id, path=path.resolve(), size=stat.st_size, mtime_ns=stat.st_mtime_ns,
                         title=title, title_source=title_source, year=info.get("year"), summary_path=summary if summary.is_file() else None))
            if limit is not None and len(found) >= limit:
                break
        return found

    def snapshot(self, source):
        root = self.root(source.root_id)
        path = source.path.resolve()
        if not path.is_relative_to(root) or source.path.is_symlink():
            raise ValueError("Source outside configured root")
        blob_dir = self.settings.data_dir / "blobs"
        blob_dir.mkdir(parents=True, exist_ok=True)
        before = path.stat()
        digest = hashlib.sha256()
        temporary = None
        try:
            with path.open("rb") as src, tempfile.NamedTemporaryFile(dir=blob_dir, delete=False) as dst:
                temporary = Path(dst.name)
                if not src.read(5).startswith(b"%PDF-"):
                    raise ValueError("Missing PDF header")
                src.seek(0)
                for piece in iter(lambda: src.read(1024 * 1024), b""):
                    digest.update(piece)
                    dst.write(piece)
                dst.flush()
                os.fsync(dst.fileno())
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Source changed during snapshot; retry inventory")
            sha = digest.hexdigest()
            if file_hash(temporary) != sha:
                raise ValueError("Snapshot checksum mismatch")
            blob = blob_dir / f"{sha}.pdf"
            # One writer holds the document identity transaction, including blob publication.
            with self.repo.write() as conn:
                if self.repo.postgres:
                    from sqlalchemy import text
                    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(sha[:15], 16)})
                existing = self.repo.rows(documents, documents.c.sha256 == sha, conn)
                if blob.exists():
                    if file_hash(blob) != sha:
                        raise ValueError("Managed snapshot integrity failure")
                else:
                    os.replace(temporary, blob)
                    blob.chmod(0o444)
                if existing:
                    document = existing[0]
                    old_paper = self.repo.one(papers, papers.c.paper_id == document["paper_id"], conn)
                    priority = {"unknown": 0, "filename": 1, "manifest": 3, "pdf": 2}
                    if priority[source.title_source] >= priority[old_paper["title_source"]]:
                        conn.execute(papers.update().where(papers.c.paper_id == document["paper_id"]).values(title=source.title, title_source=source.title_source))
                        conn.execute(chunks.update().where((chunks.c.document_id == document["document_id"]) & (chunks.c.title != source.title)).values(title=source.title))
                        if self.repo.postgres and old_paper["title"] != source.title:
                            from sqlalchemy import text
                            conn.execute(text("UPDATE chunks SET search_vector=setweight(to_tsvector('english',coalesce(title,'')),'A') || setweight(to_tsvector('english',coalesce(section,'')),'B') || setweight(to_tsvector('english',coalesce(text,'')),'C') WHERE document_id=:did"), {'did': document['document_id']})

                else:
                    pid, did = new_id(), new_id()
                    conn.execute(papers.insert().values(paper_id=pid, title=source.title, title_source=source.title_source, year=source.year))
                    document = dict(document_id=did, paper_id=pid, sha256=sha, blob_path=str(blob), byte_size=after.st_size)
                    conn.execute(documents.insert().values(**document))
                values = dict(root_id=source.root_id, document_id=document["document_id"], size=after.st_size,
                              mtime_ns=after.st_mtime_ns, last_seen=time.time(), available=True,
                              summary_path=str(source.summary_path) if source.summary_path else None)
                aliases = self.repo.rows(source_files, source_files.c.path == str(path), conn)
                if aliases:
                    conn.execute(source_files.update().where(source_files.c.path == str(path)).values(**values))
                else:
                    conn.execute(source_files.insert().values(path=str(path), **values))
                conn.execute(summaries.update().where(summaries.c.pdf_path == str(path)).values(document_id=document["document_id"]))
                title = self.repo.one(papers, papers.c.paper_id == document["paper_id"], conn)["title"]
            return DocumentRef(document_id=document["document_id"], paper_id=document["paper_id"], sha256=sha,
                               blob_path=str(blob), title=title)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def index_summaries(self, root_id):
        root = self.root(root_id)
        titles = {str(source.path): source.title for source in self.inventory(root_id)}
        count, errors = 0, []
        paths = sorted(set(root.glob("*/summary/*.md")) | set(root.glob("*/summaries/*.md")))
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            try:
                body = path.read_text(encoding="utf-8")
                pdf = (path.parent.parent / "pdfs" / (path.stem + ".pdf")).resolve()
                title = titles.get(str(pdf)) or re.sub(r'^\d{4}-', '', path.stem)
                body = re.sub(r'^# [^\n]*', lambda _: '# ' + title, body, count=1, flags=re.MULTILINE)
                payload = dict(path=str(path.resolve()), title=title, text=body,
                               sha256=hashlib.sha256(body.encode()).hexdigest(), root_id=root_id, pdf_path=str(pdf))
                with self.repo.write() as conn:
                    alias = self.repo.rows(source_files, source_files.c.path == str(pdf), conn)
                    payload["document_id"] = alias[0]["document_id"] if alias else None
                    old = self.repo.rows(summaries, summaries.c.path == payload["path"], conn)
                    if old:
                        conn.execute(summaries.update().where(summaries.c.path == payload["path"]).values(**payload))
                    else:
                        conn.execute(summaries.insert().values(**payload))
                    if self.repo.postgres:
                        from sqlalchemy import text
                        conn.execute(text("UPDATE summaries SET search_vector=setweight(to_tsvector('english',coalesce(title,'')),'A') || setweight(to_tsvector('english',coalesce(text,'')),'C') WHERE path=:path"), {"path": str(path.resolve())})
                count += 1
            except (OSError, ValueError) as exc:
                errors.append({"path": str(path), "error": str(exc)})
        return {"indexed": count, "failed": len(errors), "errors": errors, "verified": False}

    def config_hash(self):
        config = {"parser": self.settings.parser, "parser_revision": "native-1" if self.settings.parser == "native" else version("docling"),
                  "chunk_words": self.settings.chunk_words, "chunker_revision": "1", "retrieval": self.settings.retrieval,
                  "embedding_revision": self.settings.embedding_revision, "embedding_model": self.settings.embedding_model}
        return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

    def prepare(self, document):
        if isinstance(document, DocumentRef):
            document = document.model_dump(mode="json")
        if file_hash(document["blob_path"]) != document["sha256"]:
            raise ValueError("Immutable snapshot checksum mismatch")
        config_hash = self.config_hash()
        existing = self.repo.rows(generations, (generations.c.document_id == document["document_id"]) & (generations.c.config_hash == config_hash))
        if existing and existing[0]["ready"]:
            return {"existing": existing[0]}
        gid = new_id()
        artifact_dir = self.settings.data_dir / "artifacts" / gid
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / "parsed.json"
        try:
            result = subprocess.run([sys.executable, "-m", "robotlit.parser", self.settings.parser, document["blob_path"], str(artifact), str(self.settings.parser_memory_mb)],
                                    capture_output=True, timeout=self.settings.document_timeout_seconds,
                                    env={**os.environ, "PYTHONPATH": os.pathsep.join(str(p) for p in sys.path if p)})
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Parser timeout; document requires review") from exc
        if result.returncode:
            raise ValueError("Parser failed: " + result.stderr.decode(errors="replace")[-1500:])
        parsed = json.loads(artifact.read_text())
        block_rows, chunk_rows = [], []
        for item in parsed["blocks"]:
            bid = new_id()
            text = item["text"]
            block_rows.append(dict(block_id=bid, document_id=document["document_id"], generation_id=gid,
                             content_sha256=hashlib.sha256(text.encode()).hexdigest(), **item))
            words = list(re.finditer(r"\S+", text))
            step = max(1, self.settings.chunk_words - 50)
            for start in range(0, len(words), step):
                end = min(start + self.settings.chunk_words, len(words))
                lo, hi = words[start].start(), words[end - 1].end()
                chunk_rows.append(dict(chunk_id=new_id(), document_id=document["document_id"], generation_id=gid,
                                  title=document.get("title", ""), text=text[lo:hi], spans=[{"block_id": bid, "char_start": lo, "char_end": hi}],
                                  section=item["section"], kind=item["kind"]))
                if end == len(words):
                    break
        if self.settings.retrieval == "bge":
            from .retrieval import LocalModels
            vectors = LocalModels(self.settings).embed([c["text"] for c in chunk_rows])
            for row, vector in zip(chunk_rows, vectors, strict=True):
                row["vector"] = vector
        return {"generation": dict(generation_id=gid, document_id=document["document_id"], config_hash=config_hash,
                parser=self.settings.parser, embedding_revision=self.settings.embedding_revision, ready=True,
                artifact_path=str(artifact), quality=parsed["quality"]), "page_count": parsed["page_count"],
                "blocks": block_rows, "chunks": chunk_rows}

    def publish(self, prepared, conn):
        if "existing" in prepared:
            generation = prepared["existing"]
        else:
            generation = prepared["generation"]
            # Serialized publication deduplicates identical configuration work.
            if self.repo.postgres:
                conn.execute(select(documents).where(documents.c.document_id == generation["document_id"]).with_for_update()).all()
            old = self.repo.rows(generations, (generations.c.document_id == generation["document_id"]) &
                                 (generations.c.config_hash == generation["config_hash"]), conn)
            if old and old[0]["ready"]:
                generation = old[0]
            else:
                conn.execute(generations.insert().values(**generation))
                conn.execute(blocks.insert(), prepared["blocks"])
                conn.execute(chunks.insert(), prepared["chunks"])
                if self.repo.postgres:
                    from sqlalchemy import text
                    conn.execute(text("UPDATE chunks SET search_vector = setweight(to_tsvector('english',coalesce(title,'')),'A') || setweight(to_tsvector('english',coalesce(section,'')),'B') || setweight(to_tsvector('english',coalesce(text,'')),'C') WHERE generation_id=:gid"), {"gid": generation["generation_id"]})
                conn.execute(documents.update().where(documents.c.document_id == generation["document_id"]).values(page_count=prepared["page_count"]))
        conn.execute(documents.update().where(documents.c.document_id == generation["document_id"]).values(active_generation_id=generation["generation_id"]))
        return generation
