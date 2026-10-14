"""Application orchestration; all publication is fenced and transactional."""
import hashlib
import json
import threading
import time
from pathlib import Path
from uuid import UUID
from sqlalchemy import select

from .contracts import Budget, DocumentRef, SearchRequest
from .db import (Repository, blocks, configs, documents, experiments, generations, jobs,
                 new_id, papers, runs, summaries)
from .evidence import EvidenceService
from .facts import assess_comparison, classify, evaluate_predicate, evaluate_record_requirement
from .ingest import Ingestor, atomic_json
from .titles import paper_key
from .jobs import Queue
from .llm import BudgetExceeded, CloudUnavailable, Gateway, HTTPProvider, cloud_context, extract_facts
from .planner import plan_query
from .retrieval import Retriever, tokens


class LiteratureSystem:
    def __init__(self, settings, repo=None, provider=None):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.repo = repo or Repository(settings.database_url)
        self.repo.initialize()
        self.queue = Queue(self.repo, lease_seconds=settings.lease_seconds, max_attempts=settings.max_job_attempts)
        self.ingestor = Ingestor(self.repo, settings)
        self.evidence = EvidenceService(self.repo)
        self.retriever = Retriever(self.repo, settings)
        self.provider = provider or (HTTPProvider(settings) if settings.cloud_enabled else None)

    def ingest(self, root_id, limit=None, dry_run=False, rid=None):
        rid = rid or self.repo.create_run("ingest", {"root_id": root_id, "limit": limit, "dry_run": dry_run})
        prepared = self.prepare_ingestion(root_id, limit, dry_run)
        with self.repo.write() as conn:
            self.publish_ingestion(rid, prepared, conn)
        self.refresh_ingestion(rid)
        return rid

    def prepare_ingestion(self, root_id, limit=None, dry_run=False):
        sources = self.ingestor.inventory(root_id, limit)
        if dry_run:
            return {"dry_run": True, "inventory": [s.model_dump(mode="json") for s in sources], "modified": False}
        self.ingestor.index_summaries(root_id)
        descriptors, errors = [], []
        for source in sources:
            try:
                document = self.ingestor.snapshot(source)
                key = f"{document.document_id}:{self.ingestor.config_hash()}"
                descriptors.append({"key": key, "document_id": str(document.document_id)})
            except (OSError, ValueError) as exc:
                errors.append({"path": str(source.path), "error": str(exc)})
        return {"descriptors": descriptors, "errors": errors, "inventoried": len(sources)}

    def publish_ingestion(self, rid, prepared, conn):
        if prepared.get("dry_run"):
            self.repo.update_run(rid, "succeeded", prepared, conn=conn)
            return
        ids = [self.queue.enqueue("index", d["key"], {"document_id": d["document_id"]}, conn, retry_failed=True) for d in prepared["descriptors"]]
        self.repo.update_run(rid, "running", {"job_ids": sorted(set(ids)), "snapshot_failures": prepared["errors"],
                             "inventoried": prepared["inventoried"], "facts": "deferred" if self.provider is None else "not_requested"}, conn=conn)

    def submit_ingest(self, root_id, limit=None, dry_run=False):
        self.ingestor.root(root_id)
        request = {"root_id": root_id, "limit": limit, "dry_run": dry_run}
        rid = self.repo.create_run("ingest", request)
        self.queue.enqueue("ingest", rid, {"run_id": rid, **request})
        return rid

    def refresh_ingestion(self, rid):
        run = self.repo.one(runs, runs.c.run_id == str(rid))
        if run["kind"] != "ingest" or run["request"].get("dry_run") or run["state"] in ("queued", "failed"):
            return
        payload = dict(run["result"] or {})
        ids = payload.get("job_ids", [])
        rows = self.repo.rows(jobs, jobs.c.job_id.in_(ids)) if ids else []
        if len(rows) != len(set(ids)):
            raise ValueError("An ingestion job is missing from the saved run")
        payload["searchable"] = sum(j["state"] == "succeeded" for j in rows)
        payload["failed"] = sum(j["state"] == "failed" for j in rows) + len(payload.get("snapshot_failures", []))
        payload["pending"] = sum(j["state"] in ("queued", "running", "retry_wait") for j in rows)
        payload["failures"] = [{"job_id": j["job_id"], "error": j["error"], "attempt": j["attempt"]} for j in rows if j["state"] == "failed"] + payload.get("snapshot_failures", [])
        state = "running" if payload["pending"] else "partial" if payload["failed"] else "succeeded"
        if run["state"] != state or run["result"] != payload or payload.get("reload_error"):
            if state in ("succeeded", "partial"):
                try:
                    self.reload_index()
                    payload.pop("reload_error", None)
                except OSError as exc:
                    payload["reload_error"] = str(exc)[:1000]
            self.repo.update_run(rid, state, payload)

    def reload_index(self):
        # Searches read live database rows; this title catalog is refreshed after publication.
        with self.repo.write() as conn:
            rows = conn.execute(select(documents, papers.c.title).join(papers, papers.c.paper_id == documents.c.paper_id)
                                .order_by(documents.c.document_id)).mappings().all()
            catalog = {"documents": [{"paper_key": paper_key(row["title"]), "title": row["title"],
                        "document_id": row["document_id"], "generation_id": row["active_generation_id"]} for row in rows]}
            atomic_json(self.settings.data_dir / "catalog.json", catalog)
        return {"documents": len(rows), "searchable": sum(bool(row["active_generation_id"]) for row in rows)}

    def status(self, rid):
        self.reconcile_run(str(rid))
        self.refresh_ingestion(rid)
        return self.repo.one(runs, runs.c.run_id == str(rid))

    def reconcile_run(self, rid):
        related = self.repo.rows(jobs, jobs.c.key == rid)
        for job in related:
            if job["state"] == "running" and job["lease_until"] <= self.queue.clock() and job["attempt"] >= self.settings.max_job_attempts:
                with self.repo.write() as conn:
                    conn.execute(jobs.update().where((jobs.c.job_id == job["job_id"]) & (jobs.c.state == "running") &
                                 (jobs.c.lease_until <= self.queue.clock())).values(state="failed", error="Lease expired; attempts exhausted"))
                job = self.queue.get(job["job_id"])
            run = self.repo.one(runs, runs.c.run_id == rid)
            if job["state"] == "failed" and run["state"] in ("queued", "running"):
                self.repo.update_run(rid, "failed", run["result"], error=job["error"])

    def submit_search(self, request):
        rid = self.repo.create_run("search", request.model_dump(mode="json"))
        self.queue.enqueue("search", rid, {"run_id": rid})
        return rid

    def _heartbeat(self, lease, stop):
        while not stop.wait(min(60, self.settings.lease_seconds / 3)):
            if not self.queue.heartbeat(lease):
                return

    def work_once(self, worker_id="local-worker"):
        lease = self.queue.claim_job(worker_id, ["ingest", "index", "search", "enrich", "advice"])
        if lease is None:
            return False
        stop = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(lease, stop), daemon=True)
        heartbeat.start()
        try:
            if lease.stage == "ingest":
                rid = lease.payload["run_id"]
                prepared = self.prepare_ingestion(lease.payload["root_id"], lease.payload.get("limit"), lease.payload.get("dry_run", False))
                self.queue.complete_job(lease, {"run_id": rid}, lambda c: self.publish_ingestion(rid, prepared, c))
            elif lease.stage == "index":
                # Resolve managed paths at execution, so restored queued jobs use restored blobs.
                document = self.repo.one(documents, documents.c.document_id == lease.payload["document_id"])
                title = self.repo.one(papers, papers.c.paper_id == document["paper_id"])["title"]
                prepared = self.ingestor.prepare({**document, "title": title})
                self.queue.complete_job(lease, {"document_id": lease.payload["document_id"]}, lambda c: self.ingestor.publish(prepared, c))
            elif lease.stage == "search":
                rid = lease.payload["run_id"]
                request = SearchRequest.model_validate(self.repo.one(runs, runs.c.run_id == rid)["request"])
                result = self.run_search(request, rid=rid, persist=False)
                self.queue.complete_job(lease, {"run_id": rid}, lambda c: self.repo.update_run(rid, "succeeded", result, conn=c))
            elif lease.stage == "enrich":
                result, batch = self.prepare_enrichment(lease.payload["document_id"], Budget.model_validate(lease.payload["budget"]), lease)
                self.queue.complete_job(lease, result, lambda c: self.evidence.publish_facts(batch, c))
            elif lease.stage == "advice":
                rid = lease.payload["run_id"]
                request = self.repo.one(runs, runs.c.run_id == rid)["request"]
                result = self.run_advice(**request, lease=lease)
                self.queue.complete_job(lease, {"run_id": rid}, lambda c: self.repo.update_run(rid, "succeeded", result, conn=c))
        except Exception as exc:
            # Invalid documents/schemas need review. Transport failures can retry within the job cap.
            permanent = isinstance(exc, (ValueError, CloudUnavailable, BudgetExceeded))
            self.queue.fail_job(lease, str(exc), permanent=permanent)
            if "run_id" in lease.payload:
                job = self.queue.get(lease.job_id)
                if job["state"] == "failed":
                    self.repo.update_run(lease.payload["run_id"], "failed", error=str(exc)[:2000])
        finally:
            stop.set()
            heartbeat.join(timeout=1)
        for run in self.repo.rows(runs, (runs.c.kind == "ingest") & (runs.c.state == "running")):
            self.refresh_ingestion(run["run_id"])
        return True

    def work_until_idle(self):
        while self.work_once():
            pass

    def _document_match(self, doc, plan, snapshot, hits):
        did = doc["document_id"]
        document = self.repo.one(documents, documents.c.document_id == did)
        paper = self.repo.one(papers, papers.c.paper_id == document["paper_id"])
        watermark = snapshot["assertion_watermark"]
        config_rows = self.repo.rows(configs, (configs.c.document_id == did) & (configs.c.revision <= watermark))
        matches = []
        if not config_rows:
            judgments = [{"id": p.id, "outcome": "unknown", "explanation": "Configuration not yet reviewed"}
                         for p in [*plan.hard_requirements, *plan.record_requirements]]
            matches.append({"config_id": None, "label": "unreviewed configuration", "judgments": judgments,
                            "status": classify([j["outcome"] for j in judgments])})
        for config in config_rows:
            cid = config["config_id"]
            facts = self.repo.config_assertions(cid, watermark)
            judgments = [evaluate_predicate(p, facts).model_dump(mode="json") for p in plan.hard_requirements]
            scientific_records = self.repo.config_records(cid, watermark)
            record_judgments = [evaluate_record_requirement(p, scientific_records).model_dump(mode="json") for p in plan.record_requirements]
            matches.append({"config_id": cid, "label": config["payload"]["label"], "judgments": judgments,
                            "record_judgments": record_judgments, "status": classify([j["outcome"] for j in judgments + record_judgments]),
                            "assertions": facts, "records": scientific_records,
                            "soft_preferences": [evaluate_predicate(p, facts).model_dump(mode="json") for p in plan.soft_preferences]})
        priority = {"confirmed": 0, "partial": 1, "unresolved": 2, "excluded": 3, "discovery_only": 4}
        status = min((m["status"] for m in matches), key=priority.get)
        source_passages = []
        for hit in hits:
            if hit["channel"] == "pdf":
                for span in hit["spans"]:
                    block = self.repo.one(blocks, blocks.c.block_id == span["block_id"])
                    source_passages.append(self.evidence.resolve(self.evidence.ref(block, span["char_start"], span["char_end"])))
            if len(source_passages) >= 16:
                break
        if not source_passages:
            source_blocks = self.repo.rows(blocks, blocks.c.generation_id == doc["generation_id"])
            if source_blocks:
                source_passages = [self.evidence.resolve(self.evidence.ref(source_blocks[0], 0, min(len(source_blocks[0]["text"]), 3000)))]
        return {"paper_id": paper["paper_id"], "paper_key": paper_key(paper["title"]), "document_id": did, "title": paper["title"], "year": paper["year"],
                "status": status, "configurations": matches, "source_passages": source_passages[:16],
                "summary_hits": [{"title": h["title"], "text": h["text"][:2000], "verified": False} for h in hits if h["channel"] == "summary"],
                "ranking": {"relevance": sum(h["rrf_score"] for h in hits), "channels": [h["channels"] for h in hits],
                            "reranker_score": max((h["reranker_score"] for h in hits if "reranker_score" in h), default=None),
                            "evidence_completeness": sum(j["outcome"] == "satisfied" for m in matches for j in m["judgments"])},
                "caveats": ["Bounded local collection search; no completeness or novelty claim."]}

    def run_search(self, request, rid=None, persist=True):
        request = SearchRequest.model_validate(request) if isinstance(request, dict) else request
        previous = None
        if request.resume_token:
            previous_run = self.repo.one(runs, runs.c.run_id == str(UUID(request.resume_token)))
            previous = previous_run["result"]
            if previous_run["kind"] != "search" or not previous or previous.get("mode") != "collection_review":
                raise ValueError("Token does not identify a resumable collection review")
            if not previous.get("resume_token"):
                raise ValueError("Collection review is already complete")
            request = SearchRequest.model_validate(previous_run["request"])
        plan = plan_query(request)
        snapshot = previous["snapshot"] if previous else self.repo.corpus_snapshot()
        mode = "collection_review" if plan.mode == "collection_review" or request.mode == "collection_review" else "quick"
        budget = request.budgets
        rid = rid or self.repo.create_run("search", request.model_dump(mode="json"))
        hits = self.retriever.retrieve(plan, snapshot)
        by_document, summary_only = {}, []
        snapshot_ids = {d["document_id"] for d in snapshot["documents"]}
        for hit in hits:
            if hit["document_id"] in snapshot_ids:
                by_document.setdefault(hit["document_id"], []).append(hit)
            elif hit["channel"] == "summary" and mode == "quick":
                summary_only.append(hit)
        document_ids = [d["document_id"] for d in snapshot["documents"]]
        if mode == "quick":
            def ranking(did):
                scores = [h["reranker_score"] for h in by_document[did] if "reranker_score" in h]
                return (-bool(scores), -max(scores) if scores else 0, -sum(h["rrf_score"] for h in by_document[did]), did)
            ordered = sorted(by_document, key=ranking)
            # Explicit metadata and unresolved exploration survive absent lexical hits.
            known = self.repo.rows(configs, configs.c.revision <= snapshot["assertion_watermark"])
            extra = [c["document_id"] for c in known if c["document_id"] in snapshot_ids and c["document_id"] not in ordered]
            ordered.extend(dict.fromkeys(extra))
            cap = min(120, budget.max_documents)
            if plan.hard_requirements or plan.record_requirements:
                unknown = [did for did in document_ids if did not in ordered]
                reserve = min(len(unknown), max(1, cap // 5))
                ordered = ordered[:cap - reserve] + unknown[:reserve]
            else:
                ordered = ordered[:cap]
        else:
            ordered = document_ids
        cursor = previous.get("cursor", 0) if previous else 0
        selected = ordered[cursor:cursor + budget.max_documents]
        output = {bucket: list(previous[bucket]) if previous else [] for bucket in ("confirmed", "partial", "unresolved", "excluded", "discovery_only")}
        index = {d["document_id"]: d for d in snapshot["documents"]}
        configurations_evaluated = previous["coverage"]["configurations_evaluated"] if previous else 0
        for did in selected:
            match = self._document_match(index[did], plan, snapshot, by_document.get(did, []))
            configurations_evaluated += len(match["configurations"])
            output[match["status"]].append(match)
        if mode == "quick":
            for hit in summary_only[:max(0, budget.max_documents - len(selected))]:
                from .sphere import source_pdf_url
                path = Path(hit['pdf_path']) if hit.get('pdf_path') else None
                source_url = source_pdf_url(path) if path and path.is_file() and any(
                    path.resolve().is_relative_to(root) for root in self.settings.source_roots.values()) else None
                output["unresolved"].append({"paper_id": None, "document_id": None, "title": hit["title"], "status": "unresolved",
                    "source_url": source_url,
                    "source_passages": [], "configurations": [], "summary_hits": [{"text": hit["text"][:2000], "verified": False}],
                    "caveats": ["Summary-only discovery: PDF has not been ingested; every scientific requirement remains unknown."]})
        cursor += len(selected)
        resume = rid if mode == "collection_review" and cursor < len(ordered) else None
        gateway = Gateway(self.provider, budget)
        result = {"schema_version": "1.1", "run_id": rid, "mode": mode, "plan": plan.model_dump(mode="json"),
                  "resolved_interpretation": plan.resolved_terms, "snapshot": snapshot, "cursor": cursor, "resume_token": resume,
                  "coverage": {"documents_in_snapshot": len(snapshot["documents"]), "searchable_documents": len(snapshot["documents"]),
                               "documents_evaluated": cursor, "configurations_evaluated": configurations_evaluated,
                               "configurations_semantically_reviewed": 0, "retrieved_documents": len(by_document),
                               "summary_only_candidates": len(summary_only), "unresolved_cases": len(output["unresolved"]),
                               "excluded_cases": len(output["excluded"]), "exhaustive": False,
                               "retrieval_backend": self.settings.retrieval, "facts_revision": snapshot["assertion_watermark"]},
                  "usage": gateway.usage, "enrichment": "deferred" if self.provider is None else "explicit_enrich_command_required",
                  "limitations": ["Local templates interpret supported query families; other wording uses unverified discovery.",
                                  "No cloud calls during search; explicit bounded enrichment is separate.",
                                  "Summaries can retrieve candidates but cannot verify paper-specific facts."], **output}
        if plan.comparison_request is not None:
            scoped = []
            comparison = plan.comparison_request
            for bucket_name in ("confirmed", "partial", "unresolved", "discovery_only"):
                bucket = output[bucket_name]
                for match in bucket:
                    for configuration in match["configurations"]:
                        if comparison.config_ids and configuration["config_id"] not in {str(cid) for cid in comparison.config_ids}:
                            continue
                        for record in configuration.get("records", []):
                            if record["record_type"] != "reported_result":
                                continue
                            if comparison.result_ids and record["record_id"] not in {str(rid) for rid in comparison.result_ids}:
                                continue
                            fields = {k: f["value"] for k, f in record["fields"].items() if f["value_state"] == "known" and f["evidence_status"] == "supported"}
                            protocol = {k.removeprefix("protocol."): v for k, v in fields.items() if k.startswith("protocol.")}
                            if any(fields.get(key) != value for key, value in comparison.protocol_constraints.items()):
                                continue
                            scoped.append({**fields, "protocol": protocol, "result_id": record["record_id"], "config_id": configuration["config_id"]})
            result["comparison"] = assess_comparison(scoped[:240], comparison.purpose)
        if persist:
            self.repo.update_run(rid, "succeeded", result)
        return result

    def enrich(self, document_id, budget=None):
        if self.provider is None:
            raise CloudUnavailable("Configure cloud_enabled, llm_base_url and llm_model before enrichment")
        did = str(UUID(str(document_id)))
        document = self.repo.one(documents, documents.c.document_id == did)
        if not document["active_generation_id"]:
            raise ValueError("Document must be indexed before enrichment")
        budget = budget or Budget()
        key = f"{did}:{document['active_generation_id']}:facts-1.1:{self.settings.llm_model}"
        return self.queue.enqueue("enrich", key, {"document_id": did, "budget": budget.model_dump(mode="json")})

    def prepare_enrichment(self, document_id, budget, lease=None):
        doc = self.repo.one(documents, documents.c.document_id == document_id)
        packet, consumed = [], 0
        source_blocks = self.repo.rows(blocks, blocks.c.generation_id == doc["active_generation_id"])
        for block in sorted(source_blocks, key=lambda b: (b["pdf_page"], b["block_id"])):
            available = max(0, 12000 - consumed)
            if not available or len(packet) >= 16:
                break
            # UTF-8 byte cap is conservative for model tokens and prevents full-document upload.
            body = block["text"].encode()[:available].decode("utf-8", errors="ignore")
            if body:
                packet.append(self.evidence.resolve(self.evidence.ref(block, 0, len(body))))
                consumed += len(body.encode())
        existing = [c["payload"] for c in self.repo.rows(configs, configs.c.document_id == document_id)]
        gateway = Gateway(self.provider, budget, repo=self.repo, scope_key="job:" + lease.job_id if lease else None,
                          lease_validator=(lambda conn: bool(self.repo.rows(jobs, self.queue.valid_condition(lease), conn))) if lease else None)
        batch = extract_facts(gateway, packet, existing)
        self.evidence.validate_batch(batch)
        # The provider can cite only spans it received, never hidden corpus blocks.
        allowed = {p["block_id"]: p for p in packet}
        references = [ref for c in batch.configs for ref in c.identity_evidence]
        references += [ref for a in batch.assertions for ref in a.evidence_refs]
        references += [ref for r in batch.records for f in r.fields.values() for ref in f.evidence_refs]
        for ref in references:
            item = allowed.get(str(ref.block_id))
            resolved = self.evidence.resolve(ref)
            if item is None or ref.char_start < item["char_start"] or resolved["char_end"] > item["char_end"]:
                raise ValueError("Extraction cites an uninspected source span")
        return {"usage": gateway.usage, "inspected_blocks": len(packet), "total_blocks": len(source_blocks),
                "review_complete": False}, batch

    def submit_advice(self, question, project_id, project_version=None):
        self.repo.project(project_id, project_version)
        rid = self.repo.create_run("advice", {"question": question, "project_id": project_id, "project_version": project_version})
        if self.provider is None:
            self.repo.update_run(rid, "deferred", {"reason": "Cloud advice disabled; project and experiment memory remain available"})
        else:
            self.queue.enqueue("advice", rid, {"run_id": rid})
        return rid

    def run_advice(self, question, project_id, project_version=None, lease=None):
        profile = self.repo.project(project_id, project_version)
        search = self.run_search(SearchRequest(question=question, budgets=Budget(max_documents=10, max_cloud_calls=0)))
        evidence = [ref for bucket in ("confirmed", "partial", "unresolved", "discovery_only") for match in search[bucket]
                    for ref in match["source_passages"]][:16]
        query_words = set(tokens(question))
        experiment_fields = {"hypothesis", "intervention", "baseline", "controlled_variables", "dataset", "task", "robot",
                             "metrics", "trial_counts", "observations", "interpretation", "project_version", "experiment_id"}
        history = []
        for row in self.repo.rows(experiments, experiments.c.project_id == str(project_id)):
            relevant = {k: v for k, v in row["payload"].items() if k in experiment_fields}
            if query_words.intersection(tokens(json.dumps(relevant, ensure_ascii=False))):
                history.append(relevant)
        history = history[-10:]
        project_fields = {"goals", "robot", "end_effectors", "observations", "camera_properties", "action_space", "policy_architecture",
                          "datasets", "compute_constraints", "latency_constraints", "known_failure_modes", "current_questions"}
        project_context = {k: v for k, v in profile["profile"].items() if k in project_fields}
        gateway = Gateway(self.provider, Budget(), repo=self.repo, scope_key="job:" + lease.job_id if lease else None,
                          lease_validator=(lambda conn: bool(self.repo.rows(jobs, self.queue.valid_condition(lease), conn))) if lease else None)
        answer = gateway.generate("advise", {"question": question, "project_context": cloud_context(project_context),
                                  "experiment_context": cloud_context(history), "untrusted_evidence": cloud_context(evidence)}, 3000)
        allowed = {ref["block_id"] for ref in evidence}
        claims = []
        for claim in answer.get("claims", []):
            if claim.get("claim_type") not in ("published_finding", "inference", "proposed_experiment"):
                continue
            refs = claim.get("evidence_refs", [])
            if claim["claim_type"] == "published_finding" and not refs:
                continue
            if all(str(ref.get("block_id")) in allowed for ref in refs):
                resolved_refs = [self.evidence.resolve(ref) for ref in refs]
                bounds = {ref["block_id"]: ref for ref in evidence}
                if any(ref["char_start"] < bounds[ref["block_id"]]["char_start"] or ref["char_end"] > bounds[ref["block_id"]]["char_end"] for ref in resolved_refs):
                    continue
                claim["evidence_refs"] = resolved_refs
                claim["review_state"] = "semantic_support_unreviewed"
                claims.append(claim)
        if any(c["claim_type"] == "published_finding" for c in claims):
            review = gateway.generate("review_advice", {"claims": claims, "untrusted_evidence": evidence}, 1000)
            indices = review.get("supported_claim_indices", [])
            if not isinstance(indices, list) or any(type(i) is not int or not 0 <= i < len(claims) for i in indices):
                raise ValueError("Advice reviewer returned invalid claim indices")
            claims = [c for i, c in enumerate(claims) if c["claim_type"] != "published_finding" or i in indices]
            for claim in claims:
                if claim["claim_type"] == "published_finding":
                    claim["review_state"] = "semantically_reviewed"
        return {"schema_version": "1.1", "project_id": profile["project_id"], "project_version": profile["version"],
                "claims": claims, "proposed_experiments": [{**p, "status": "untested"} for p in answer.get("proposed_experiments", [])],
                "usage": gateway.usage, "coverage": search["coverage"], "source_run_id": search["run_id"]}
