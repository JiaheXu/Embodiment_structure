import json
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .contracts import Budget, PaperFactBatch, SearchRequest
from .db import blocks, configs, documents, events, jobs, papers, projects, runs
from .export import markdown


class IngestRequest(BaseModel):
    source_root: str = "papers"
    limit: int | None = Field(default=None, ge=1)
    dry_run: bool = False


class CorrectionRequest(BaseModel):
    value: object
    evidence_refs: list[dict]
    reason: str = Field(min_length=1)


class ProjectEdit(BaseModel):
    expected_version: int = Field(ge=1)
    profile: dict


def create_app(system):
    app = FastAPI(title="Robot Literature", version="0.1.0")
    app.state.system = system
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != expected:
            return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def validation_error(request, exc):
        message = str(exc)
        status = 409 if "conflict" in message or "already corrected" in message else 404 if message.startswith("Unknown") else 422
        return JSONResponse({"detail": message}, status_code=status)

    @app.get("/", response_class=HTMLResponse)
    @app.get("/sphere", response_class=HTMLResponse)
    def home():
        return Path(__file__).with_name("sphere.html").read_text()

    @app.get("/workspace")
    def workspace():
        return RedirectResponse(url="/")

    @app.get("/assets/sphere.js")
    def sphere_script():
        return FileResponse(Path(__file__).with_name("sphere.js"), media_type="text/javascript")

    @app.get("/v1/sphere")
    def sphere_catalog():
        from .sphere import build_sphere
        sources, warnings = [], []
        for root_id in system.settings.source_roots:
            try:
                sources.extend(system.ingestor.inventory(root_id))
            except (ValueError, OSError):
                warnings.append(f"Source root '{root_id}' is unavailable; retained papers are still shown.")
        return {**build_sphere(system.repo, sources), 'inventory_warnings': warnings,
                'source_roots': list(system.settings.source_roots)}

    @app.get("/v1/health")
    def health():
        return {"schema_version": "1.1", "database": system.repo.engine.dialect.name, "retrieval": system.settings.retrieval,
                "parser": system.settings.parser, "cloud_enabled": system.provider is not None,
                "documents": len(system.repo.rows(documents)), "source_roots": list(system.settings.source_roots)}

    @app.post("/v1/ingest", status_code=202)
    def ingest(request: IngestRequest):
        return {"schema_version": "1.1", "run_id": system.submit_ingest(request.source_root, request.limit, request.dry_run)}

    @app.get("/v1/ingest/{run_id}")
    def ingestion_status(run_id: UUID):
        return system.status(str(run_id))

    @app.post("/v1/search", status_code=202)
    def search(request: SearchRequest):
        return {"schema_version": "1.1", "run_id": system.submit_search(request)}

    @app.get("/v1/search/{run_id}")
    def search_status(run_id: UUID):
        return system.status(str(run_id))

    @app.get("/v1/search/{run_id}/events")
    def progress(run_id: UUID, request: Request):
        system.repo.one(runs, runs.c.run_id == str(run_id))
        last = int(request.headers.get("last-event-id", "0"))
        def stream():
            nonlocal last
            import time
            while True:
                rows = system.repo.rows(events, (events.c.run_id == str(run_id)) & (events.c.event_id > last))
                for row in sorted(rows, key=lambda r: r["event_id"]):
                    last = row["event_id"]
                    yield f"id: {last}\nevent: progress\ndata: {json.dumps(row['payload'])}\n\n"
                run = system.status(str(run_id))
                if run["state"] in ("succeeded", "failed", "partial", "deferred"):
                    return
                yield ": heartbeat\n\n"
                time.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/v1/search/{run_id}/export")
    def export(run_id: UUID, format: str = "json"):
        result = system.status(str(run_id))["result"]
        if result is None:
            raise ValueError("Result is not ready")
        if format == "json":
            return JSONResponse(result)
        if format == "markdown":
            return PlainTextResponse(markdown(result), media_type="text/markdown")
        raise ValueError("Format must be json or markdown")

    @app.get("/v1/evidence/{block_id}")
    def evidence(block_id: UUID):
        block = system.repo.one(blocks, blocks.c.block_id == str(block_id))
        return {"schema_version": "1.1", **system.evidence.resolve(system.evidence.ref(block))}

    @app.get("/v1/source-files/{source_id}/pdf")
    def source_pdf(source_id: str):
        from .sphere import source_pdf_url
        for root_id in system.settings.source_roots:
            try:
                sources = system.ingestor.inventory(root_id)
            except (ValueError, OSError):
                continue
            for source in sources:
                if source_pdf_url(source.path) == f"/v1/source-files/{source_id}/pdf":
                    return FileResponse(source.path, media_type="application/pdf")
        raise ValueError("Unknown source PDF")

    @app.get("/v1/documents/{document_id}/pdf")
    def pdf(document_id: UUID):
        document = system.repo.one(documents, documents.c.document_id == str(document_id))
        path = Path(document["blob_path"]).resolve()
        if not path.is_relative_to(system.settings.data_dir / "blobs") or not path.is_file():
            raise ValueError("Unknown managed snapshot")
        return FileResponse(path, media_type="application/pdf")

    @app.get("/v1/papers")
    def catalog(offset: int = 0, limit: int = 50):
        from .titles import paper_key
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Invalid catalog page")
        with system.repo.engine.connect() as conn:
            result = conn.execute(select(papers).order_by(papers.c.title, papers.c.paper_id).offset(offset).limit(limit)).mappings().all()
        return {"schema_version": "1.1", "papers": [{**row, "paper_key": paper_key(row["title"])} for row in result], "offset": offset}

    @app.get("/v1/papers/{paper_id}")
    def paper(paper_id: UUID):
        from .titles import paper_key
        paper = system.repo.one(papers, papers.c.paper_id == str(paper_id))
        versions = system.repo.rows(documents, documents.c.paper_id == str(paper_id))
        return {"schema_version": "1.1", **paper, "paper_key": paper_key(paper["title"]), "versions": versions,
                "configurations": [c["payload"] for d in versions for c in system.repo.rows(configs, configs.c.document_id == d["document_id"])]}

    @app.get("/v1/configurations/{config_id}")
    def configuration(config_id: UUID):
        config = system.repo.one(configs, configs.c.config_id == str(config_id))
        return {"schema_version": "1.1", **config["payload"], "assertions": system.repo.config_assertions(config_id),
                "records": system.repo.config_records(config_id)}

    @app.post("/v1/facts")
    def facts(batch: PaperFactBatch):
        return system.evidence.publish_facts(batch)

    @app.post("/v1/documents/{document_id}/enrich", status_code=202)
    def enrich(document_id: UUID, budget: Budget):
        return {"schema_version": "1.1", "job_id": system.enrich(document_id, budget)}

    @app.post("/v1/assertions/{assertion_id}/corrections")
    def correction(assertion_id: UUID, request: CorrectionRequest):
        return system.evidence.correct(str(assertion_id), request.value, request.evidence_refs, request.reason)

    @app.post("/v1/records/{record_id}/corrections")
    def record_correction(record_id: UUID, request: dict):
        return system.evidence.correct_record(str(record_id), request["fields"], request["reason"])

    @app.get("/v1/projects")
    def project_list():
        rows = system.repo.rows(projects)
        latest = {}
        for p in rows:
            if p["project_id"] not in latest or p["version"] > latest[p["project_id"]]["version"]:
                latest[p["project_id"]] = p
        return list(latest.values())

    @app.post("/v1/projects", status_code=201)
    def create_project(profile: dict):
        return system.repo.create_project(profile)

    @app.patch("/v1/projects/{project_id}")
    def edit_project(project_id: UUID, request: ProjectEdit):
        return system.repo.update_project(project_id, request.expected_version, request.profile)

    @app.get("/v1/projects/{project_id}")
    def project(project_id: UUID, version: int | None = None):
        return system.repo.project(project_id, version)

    @app.post("/v1/experiments", status_code=201)
    def experiment(record: dict):
        required = {"project_id", "project_version", "observations"}
        if not required <= record.keys():
            raise ValueError("Experiment requires project_id, project_version and observations")
        return system.repo.add_experiment(record)

    @app.post("/v1/advice", status_code=202)
    def advice(request: dict):
        if not isinstance(request.get("question"), str) or not request.get("project_id"):
            raise ValueError("Advice requires question and project_id")
        return {"run_id": system.submit_advice(request["question"], str(UUID(request["project_id"])), request.get("project_version"))}

    @app.get("/v1/jobs/{job_id}")
    def job(job_id: UUID):
        return system.queue.get(str(job_id))

    return app
