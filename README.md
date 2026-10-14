# Robot Literature

Local robot-learning paper discovery with immutable PDF evidence, configuration-scoped facts, resumable jobs, and project/experiment memory.

```bash
UV_PROJECT_ENVIRONMENT=.venv-robotlit uv sync --locked --extra test
source .venv-robotlit/bin/activate
robotlit serve --host 127.0.0.1 --port 8000
# In a second terminal:
robotlit worker
```

Open <http://127.0.0.1:8000>. For direct searches:

```bash
robotlit index-summaries
robotlit ingest --source-root papers --limit 100 --wait
robotlit search "Find multi-view policies without supplied camera poses"
```

The runnable profile uses native PDF text and SQLite FTS. Summaries aid discovery and cannot verify matches. Cloud calls are disabled by default. Optional PostgreSQL, Docling and pinned BGE adapters require separate production validation.

See [the runbook](docs/runbook.md), [implementation status](docs/implementation_status.md), and [the supplied specification](docs/robot_literature_system_codex_spec.md).
