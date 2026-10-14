import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class Settings(BaseModel):
    source_roots: dict[str, Path] = Field(default_factory=lambda: {"papers": Path("labs").resolve()})
    data_dir: Path = Path("data/robotlit")
    database_url: str = "sqlite:///data/robotlit/catalog.sqlite"
    parser: Literal["native", "docling"] = "native"
    retrieval: Literal["lexical", "bge"] = "lexical"
    embedding_model: str = "BAAI/bge-m3"
    embedding_revision: str | None = None
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_revision: str | None = None
    device: str = "cpu"
    document_timeout_seconds: int = Field(default=900, gt=0)
    parser_memory_mb: int = Field(default=8192, ge=256)
    lease_seconds: int = Field(default=600, gt=0)
    max_job_attempts: int = Field(default=3, ge=1, le=3)
    chunk_words: int = Field(default=450, ge=50, le=700)
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key_env: str = "ROBOTLIT_LLM_API_KEY"
    cloud_enabled: bool = False

    @model_validator(mode="after")
    def validate_storage(self):
        self.data_dir = self.data_dir.resolve()
        self.source_roots = {key: value.resolve() for key, value in self.source_roots.items()}
        for root in self.source_roots.values():
            if self.data_dir == root or self.data_dir.is_relative_to(root):
                raise ValueError("Managed data must be outside read-only source roots")
        if self.database_url.startswith("sqlite:///") and not self.database_url.endswith(":memory:"):
            database_path = Path(self.database_url.removeprefix("sqlite:///")).resolve()
            if any(database_path.is_relative_to(root) for root in self.source_roots.values()):
                raise ValueError("Database cannot write inside read-only source roots")
        if self.retrieval == "bge":
            for revision in (self.embedding_revision, self.reranker_revision):
                if not revision or len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
                    raise ValueError("BGE mode requires immutable 40-character model commit revisions")
        if self.cloud_enabled and (not self.llm_base_url or not self.llm_model):
            raise ValueError("Cloud mode requires llm_base_url and llm_model")
        return self

    @classmethod
    def load(cls, path: str | Path | None = None):
        path = Path(path or os.environ.get("ROBOTLIT_CONFIG", "config/robotlit.yaml"))
        values = yaml.safe_load(path.read_text()) if path.exists() else {}
        values = values or {}
        if os.environ.get("ROBOTLIT_DATABASE_URL"):
            values["database_url"] = os.environ["ROBOTLIT_DATABASE_URL"]
        return cls(**values)
