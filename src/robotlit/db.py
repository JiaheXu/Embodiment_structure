"""Portable persistence. PostgreSQL is production; SQLite supports offline pilots."""
import json
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (JSON, Boolean, Column, Float, ForeignKey, Integer, MetaData,
                        String, Table, Text, UniqueConstraint, create_engine, event,
                        func, inspect, select, text)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector

metadata = MetaData()
json_type = JSON().with_variant(JSONB(), "postgresql")


def ident(name, target=None, primary=False):
    args = [name, String(36)]
    if target:
        args.append(ForeignKey(target))
    return Column(*args, primary_key=primary, nullable=not primary)


papers = Table("papers", metadata, ident("paper_id", primary=True), Column("title", Text, nullable=False), Column("year", Integer),
               Column("title_source", Text, nullable=False, server_default="unknown"))
documents = Table("documents", metadata, ident("document_id", primary=True), ident("paper_id", "papers.paper_id"),
                  Column("sha256", String(64), nullable=False, unique=True), Column("blob_path", Text, nullable=False),
                  Column("byte_size", Integer), Column("page_count", Integer), Column("active_generation_id", String(36)),
                  Column("facts_ready", Boolean, default=False), Column("created_at", Float, default=time.time))
source_files = Table("source_files", metadata, Column("path", Text, primary_key=True), Column("root_id", Text),
                     ident("document_id", "documents.document_id"), Column("size", Integer), Column("mtime_ns", Integer),
                     Column("last_seen", Float), Column("available", Boolean), Column("summary_path", Text))
generations = Table("generations", metadata, ident("generation_id", primary=True), ident("document_id", "documents.document_id"),
                    Column("config_hash", String(64), nullable=False), Column("parser", Text), Column("embedding_revision", Text),
                    Column("ready", Boolean, default=False), Column("artifact_path", Text), Column("quality", json_type),
                    Column("created_at", Float, default=time.time), UniqueConstraint("document_id", "config_hash"))
blocks = Table("blocks", metadata, ident("block_id", primary=True), ident("document_id", "documents.document_id"),
               ident("generation_id", "generations.generation_id"), Column("pdf_page", Integer, nullable=False),
               Column("bbox", json_type), Column("text", Text, nullable=False), Column("content_sha256", String(64)),
               Column("kind", Text), Column("section", Text), Column("structured", json_type))
chunks = Table("chunks", metadata, ident("chunk_id", primary=True), ident("document_id", "documents.document_id"),
               ident("generation_id", "generations.generation_id"), Column("title", Text), Column("text", Text), Column("spans", json_type),
               Column("section", Text), Column("kind", Text), Column("vector", JSON().with_variant(Vector(1024), "postgresql")),
               Column("search_vector", Text().with_variant(TSVECTOR(), "postgresql")))
summaries = Table("summaries", metadata, Column("path", Text, primary_key=True), Column("title", Text),
                  Column("text", Text), Column("sha256", String(64)), Column("root_id", Text), Column("pdf_path", Text),
                  ident("document_id", "documents.document_id"), Column("search_vector", Text().with_variant(TSVECTOR(), "postgresql")))
configs = Table("method_configs", metadata, ident("config_id", primary=True), ident("document_id", "documents.document_id"),
                Column("payload", json_type), Column("revision", Integer, nullable=False))
assertions = Table("facet_assertions", metadata, ident("assertion_id", primary=True), ident("config_id", "method_configs.config_id"),
                   Column("facet", Text, index=True), Column("payload", json_type), Column("revision", Integer, nullable=False),
                   ident("supersedes", "facet_assertions.assertion_id"))
records = Table("scientific_records", metadata, ident("record_id", primary=True), ident("config_id", "method_configs.config_id"),
                Column("record_type", Text), Column("payload", json_type), Column("revision", Integer, nullable=False))
record_revisions = Table("record_revisions", metadata, ident("revision_id", primary=True), ident("record_id", "scientific_records.record_id"),
                         Column("payload", json_type), Column("revision", Integer, nullable=False), Column("reason", Text))
revisions = Table("revisions", metadata, Column("id", Integer, primary_key=True), Column("watermark", Integer, nullable=False))
jobs = Table("jobs", metadata, ident("job_id", primary=True), Column("stage", Text, index=True), Column("key", Text),
             Column("payload", json_type), Column("state", Text, index=True), Column("attempt", Integer), Column("fence", Integer),
             Column("lease_until", Float), Column("worker", Text), Column("next_attempt", Float), Column("error", Text),
             Column("result", json_type), Column("created_at", Float), UniqueConstraint("stage", "key"))
runs = Table("runs", metadata, ident("run_id", primary=True), Column("kind", Text), Column("state", Text),
             Column("request", json_type), Column("result", json_type), Column("error", Text), Column("created_at", Float))
events = Table("run_events", metadata, Column("event_id", Integer, primary_key=True, autoincrement=True),
               ident("run_id", "runs.run_id"), Column("payload", json_type), Column("created_at", Float))
projects = Table("projects", metadata, Column("project_id", String(36), primary_key=True),
                 Column("version", Integer, primary_key=True), Column("profile", json_type), Column("created_at", Float))
experiments = Table("experiments", metadata, ident("experiment_id", primary=True), Column("project_id", String(36)),
                    Column("project_version", Integer), Column("payload", json_type), Column("created_at", Float))
cloud_usage = Table("cloud_usage", metadata, Column("scope_key", Text, primary_key=True), Column("usage", json_type))
cloud_attempts = Table("cloud_attempts", metadata, ident("attempt_id", primary=True),
                       Column("scope_key", Text, ForeignKey("cloud_usage.scope_key")), Column("task", Text),
                       Column("state", Text), Column("input_reservation", Integer), Column("output_reservation", Integer),
                       Column("provider_usage", json_type), Column("created_at", Float))


def new_id():
    return str(uuid4())


class Repository:
    def __init__(self, url):
        if url.startswith("sqlite:///") and not url.endswith(":memory:"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {})
        self.postgres = self.engine.dialect.name == "postgresql"
        if not self.postgres:
            @event.listens_for(self.engine, "connect")
            def sqlite_setup(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA journal_mode=WAL")

    def initialize(self):
        if self.postgres:
            with self.engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        metadata.create_all(self.engine)
        with self.write() as conn:
            if "title_source" not in {column["name"] for column in inspect(conn).get_columns("papers")}:
                conn.execute(text("ALTER TABLE papers ADD COLUMN title_source TEXT NOT NULL DEFAULT 'unknown'"))
            if not conn.execute(select(revisions)).first():
                conn.execute(revisions.insert().values(id=1, watermark=0))
            if self.postgres:
                conn.execute(text("CREATE INDEX IF NOT EXISTS chunks_fts ON chunks USING gin(search_vector)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS summaries_fts ON summaries USING gin(search_vector)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS chunks_vector ON chunks USING hnsw(vector vector_cosine_ops)"))
            else:
                self.initialize_fts(conn)

    def initialize_fts(self, conn):
        for table_name, id_column in (("chunks", "chunk_id"), ("summaries", "path")):
            name = table_name + "_fts"
            exists = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE name=?", (name,)).first()
            conn.exec_driver_sql(f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} USING fts5({id_column} UNINDEXED, title, text, content='{table_name}', content_rowid='rowid')")
            conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {name}_insert AFTER INSERT ON {table_name} BEGIN INSERT INTO {name}(rowid,{id_column},title,text) VALUES(new.rowid,new.{id_column},new.title,new.text); END")
            conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {name}_delete AFTER DELETE ON {table_name} BEGIN INSERT INTO {name}({name},rowid,{id_column},title,text) VALUES('delete',old.rowid,old.{id_column},old.title,old.text); END")
            conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {name}_update AFTER UPDATE ON {table_name} BEGIN INSERT INTO {name}({name},rowid,{id_column},title,text) VALUES('delete',old.rowid,old.{id_column},old.title,old.text); INSERT INTO {name}(rowid,{id_column},title,text) VALUES(new.rowid,new.{id_column},new.title,new.text); END")
            if not exists:
                conn.exec_driver_sql(f"INSERT INTO {name}({name}) VALUES('rebuild')")

    @contextmanager
    def write(self):
        with self.engine.connect() as conn:
            if not self.postgres:
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.begin()
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def rows(self, table, condition=None, conn=None):
        statement = select(table)
        if condition is not None:
            statement = statement.where(condition)
        if conn is not None:
            return [dict(row) for row in conn.execute(statement).mappings()]
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def one(self, table, condition, conn=None):
        found = self.rows(table, condition, conn)
        if not found:
            raise ValueError(f"Unknown {table.name} ID")
        return found[0]

    def bump_revision(self, conn):
        return conn.execute(revisions.update().where(revisions.c.id == 1).values(watermark=revisions.c.watermark + 1)
                            .returning(revisions.c.watermark)).scalar_one()

    def corpus_snapshot(self):
        with self.write() as conn:
            # Serialize against fact publication; facts at the watermark are immutable.
            statement = select(revisions.c.watermark).where(revisions.c.id == 1)
            if self.postgres:
                statement = statement.with_for_update()
            watermark = conn.execute(statement).scalar_one()
            docs = self.rows(documents, documents.c.active_generation_id.is_not(None), conn)
            return {"snapshot_id": new_id(), "documents": [{"document_id": d["document_id"], "generation_id": d["active_generation_id"],
                     "paper_id": d["paper_id"]} for d in sorted(docs, key=lambda x: x["document_id"])], "assertion_watermark": watermark}

    def config_assertions(self, config_id, watermark=None):
        condition = assertions.c.config_id == str(config_id)
        if watermark is not None:
            condition &= assertions.c.revision <= watermark
        rows = self.rows(assertions, condition)
        superseded = {r["supersedes"] for r in rows if r["supersedes"]}
        return [r["payload"] for r in rows if r["assertion_id"] not in superseded]

    def config_records(self, config_id, watermark=None):
        output = []
        for record in self.rows(records, records.c.config_id == str(config_id)):
            if watermark is not None and record["revision"] > watermark:
                continue
            history = self.rows(record_revisions, record_revisions.c.record_id == record["record_id"])
            history = [r for r in history if watermark is None or r["revision"] <= watermark]
            output.append(max(history, key=lambda r: r["revision"])["payload"] if history else record["payload"])
        return output

    def create_run(self, kind, request):
        rid = new_id()
        with self.write() as conn:
            conn.execute(runs.insert().values(run_id=rid, kind=kind, state="queued", request=request, created_at=time.time()))
            self.add_event(rid, {"state": "queued"}, conn)
        return rid

    def add_event(self, rid, payload, conn):
        conn.execute(events.insert().values(run_id=rid, payload=payload, created_at=time.time()))

    def update_run(self, rid, state, result=None, error=None, conn=None):
        if conn is None:
            with self.write() as connection:
                self.update_run(rid, state, result, error, connection)
            return
        conn.execute(runs.update().where(runs.c.run_id == rid).values(state=state, result=result, error=error))
        self.add_event(rid, {"state": state, "error": error}, conn)

    def create_project(self, profile):
        p = {"project_id": new_id(), "version": 1, "profile": profile, "created_at": time.time()}
        with self.write() as conn:
            conn.execute(projects.insert().values(**p))
        return p

    def project(self, project_id, version=None, conn=None):
        rows = self.rows(projects, projects.c.project_id == str(project_id), conn)
        rows = [p for p in rows if version is None or p["version"] == version]
        if not rows:
            raise ValueError("Unknown project/version")
        return max(rows, key=lambda p: p["version"])

    def update_project(self, project_id, expected_version, profile):
        with self.write() as conn:
            if self.postgres:
                conn.execute(select(projects).where(projects.c.project_id == str(project_id)).with_for_update()).all()
            current = self.project(project_id, conn=conn)
            if current["version"] != expected_version:
                raise ValueError("Project version conflict")
            updated = {"project_id": str(project_id), "version": expected_version + 1, "profile": profile, "created_at": time.time()}
            conn.execute(projects.insert().values(**updated))
            return updated

    def add_experiment(self, payload):
        self.project(payload["project_id"], payload["project_version"])
        record = {**payload, "experiment_id": new_id()}
        with self.write() as conn:
            conn.execute(experiments.insert().values(experiment_id=record["experiment_id"], project_id=payload["project_id"],
                         project_version=payload["project_version"], payload=record, created_at=time.time()))
        return record
