import math
import re
from collections import Counter, defaultdict

from sqlalchemy import bindparam, func, select, text

from .db import chunks, generations, summaries


def tokens(text):
    return re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", text.casefold())


def rrf(rank_lists, k=60):
    scores = defaultdict(float)
    for ranked in rank_lists:
        for rank, identifier in enumerate(ranked, 1):
            scores[identifier] += 1 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


class LocalModels:
    _models = {}

    def __init__(self, settings):
        self.settings = settings

    def embed(self, texts):
        from sentence_transformers import SentenceTransformer
        key = (self.settings.embedding_model, self.settings.embedding_revision, self.settings.device)
        if key not in self._models:
            self._models[key] = SentenceTransformer(key[0], revision=key[1], device=key[2])
        model = self._models[key]
        vectors = model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=False).tolist()
        if any(len(v) != 1024 or not all(math.isfinite(x) for x in v) for v in vectors):
            raise ValueError("BGE model returned invalid vectors")
        return vectors

    def rerank(self, query, passages):
        from sentence_transformers import CrossEncoder
        key = (self.settings.reranker_model, self.settings.reranker_revision, self.settings.device)
        if key not in self._models:
            self._models[key] = CrossEncoder(key[0], revision=key[1], device=key[2], max_length=2048)
        return self._models[key].predict([(query, p) for p in passages]).tolist()


class Retriever:
    def __init__(self, repo, settings):
        self.repo, self.settings = repo, settings

    def retrieve(self, plan, snapshot):
        gids = [doc["generation_id"] for doc in snapshot["documents"]]
        if self.settings.retrieval == "bge":
            indexed = self.repo.rows(generations, generations.c.generation_id.in_(gids))
            if any(g["embedding_revision"] != self.settings.embedding_revision for g in indexed):
                raise ValueError("Embedding revision mismatch; re-ingest with the configured pinned model before BGE search")
        items = {}
        rank_lists, attribution = [], defaultdict(list)
        queries = plan.search_queries or [""]
        for query in queries:
            terms = list(dict.fromkeys(tokens(query)))[:100]
            for table, identifier, channel in ((chunks, "chunk_id", "pdf"), (summaries, "path", "summary")):
                if table is chunks and not gids:
                    continue
                with self.repo.engine.connect() as conn:
                    if not terms:
                        statement = select(table).order_by(table.c[identifier]).limit(60)
                        if table is chunks:
                            statement = statement.where(chunks.c.generation_id.in_(gids))
                        found = conn.execute(statement).mappings().all()
                    elif self.repo.postgres:
                        tsquery = func.to_tsquery('english', ' | '.join(terms))
                        statement = select(table).where(table.c.search_vector.op('@@')(tsquery)).order_by(
                            func.ts_rank_cd(table.c.search_vector, tsquery).desc(), table.c[identifier]).limit(60)
                        if table is chunks:
                            statement = statement.where(chunks.c.generation_id.in_(gids))
                        found = conn.execute(statement).mappings().all()
                    else:
                        table_name = table.name
                        expression = ' OR '.join('"' + term + '"' for term in terms)
                        statement = text(f"SELECT t.* FROM {table_name}_fts f JOIN {table_name} t ON t.rowid=f.rowid WHERE {table_name}_fts MATCH :query " +
                                         ("AND t.generation_id IN :gids " if table is chunks else "") +
                                         f"ORDER BY bm25({table_name}_fts,0,3,1),t.{identifier} LIMIT 60")
                        parameters = {"query": expression}
                        if table is chunks:
                            statement = statement.bindparams(bindparam('gids', expanding=True))
                            parameters["gids"] = gids
                        found = conn.execute(statement, parameters).mappings().all()
                ranked = []
                for raw in found:
                    row = dict(raw)
                    if not self.repo.postgres:
                        import json
                        for key in ("spans", "vector"):
                            if isinstance(row.get(key), str):
                                row[key] = json.loads(row[key])
                    cid = row[identifier] if channel == "pdf" else "summary:" + row[identifier]
                    items[cid] = {**row, "chunk_id": cid, "channel": channel}
                    ranked.append(cid)
                    attribution[cid].append({"channel": "lexical" if channel == "pdf" else "summary_lexical", "rank": len(ranked), "query": query})
                rank_lists.append(ranked)
            if self.settings.retrieval == "bge" and gids:
                vector = LocalModels(self.settings).embed([query])[0]
                if self.repo.postgres:
                    with self.repo.engine.connect() as conn:
                        dense_rows = [dict(r) for r in conn.execute(select(chunks).where(chunks.c.generation_id.in_(gids))
                                      .where(chunks.c.vector.is_not(None)).order_by(chunks.c.vector.cosine_distance(vector)).limit(60)).mappings()]
                        ranked = [r["chunk_id"] for r in dense_rows]
                    items.update({r["chunk_id"]: {**r, "channel": "pdf"} for r in dense_rows})
                else:
                    # SQLite is for pilots; pgvector is required for scalable dense retrieval.
                    rows = self.repo.rows(chunks, chunks.c.generation_id.in_(gids))
                    similarity = [(r["chunk_id"], sum(a * b for a, b in zip(vector, r["vector"], strict=True))) for r in rows if r["vector"]]
                    ranked = [cid for cid, _ in sorted(similarity, key=lambda x: (-x[1], x[0]))[:60]]
                    items.update({r["chunk_id"]: {**r, "channel": "pdf"} for r in rows if r["chunk_id"] in ranked})
                rank_lists.append(ranked)
                for rank, cid in enumerate(ranked, 1):
                    attribution[cid].append({"channel": "dense", "rank": rank, "query": query})
        fused = rrf(rank_lists)
        if self.settings.retrieval == "bge" and fused:
            head = fused[:80]
            scores = LocalModels(self.settings).rerank(" ".join(queries), [items[cid]["text"] for cid, _ in head])
            head = sorted(zip(head, scores, strict=True), key=lambda x: (-x[1], x[0][0]))
            for (cid, _), score in head:
                items[cid]["reranker_score"] = float(score)
            fused = [pair for pair, _ in head] + fused[80:]
        result = []
        for cid, score in fused:
            row = items[cid]
            result.append({**row, "rrf_score": score, "channels": attribution[cid]})
        return result
