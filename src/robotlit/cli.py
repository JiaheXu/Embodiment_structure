import argparse
import json
import sys
import time
from pathlib import Path

from .config import Settings
from .contracts import Budget, QueryPlan, SearchRequest
from .db import documents, jobs, runs
from .export import markdown
from .service import LiteratureSystem


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def parser():
    root = argparse.ArgumentParser(description="Local evidence-preserving robot literature assistant")
    root.add_argument("--config", help="Settings YAML; defaults to config/robotlit.yaml")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("inventory", "ingest", "index-summaries"):
        p = commands.add_parser(name)
        p.add_argument("--source-root", default="papers")
        p.add_argument("--limit", type=int)
        p.add_argument("--dry-run", action="store_true")
        if name == "ingest":
            p.add_argument("--wait", action="store_true", help="Process jobs in this process until idle")
    p = commands.add_parser("worker")
    p.add_argument("--once", action="store_true", help="Process available work and exit")
    p.add_argument("--worker-id", default="local-worker")
    p = commands.add_parser("status")
    p.add_argument("--run-id")
    p.add_argument("--job-id")
    for name in ("search", "review-collection"):
        p = commands.add_parser(name)
        p.add_argument("question", nargs="?")
        p.add_argument("--plan")
        p.add_argument("--resume-token")
        p.add_argument("--max-documents", type=int, default=120)
        p.add_argument("--max-cloud-calls", type=int, default=0 if name == "search" else None)
        p.add_argument("--max-input-tokens", type=int, default=60000 if name == "search" else None)
        p.add_argument("--max-output-tokens", type=int, default=12000 if name == "search" else None)
        p.add_argument("--format", choices=["json", "markdown"], default="json")
    p = commands.add_parser("enrich")
    p.add_argument("--document-id", required=True)
    p.add_argument("--max-cloud-calls", type=int, default=2)
    p.add_argument("--max-input-tokens", type=int, default=60000)
    p.add_argument("--max-output-tokens", type=int, default=8000)
    p = commands.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p = commands.add_parser("evaluate")
    p.add_argument("--dataset", required=True)
    p.add_argument("--output")
    p = commands.add_parser("project")
    p.add_argument("--profile", required=True)
    p.add_argument("--project-id")
    p.add_argument("--expected-version", type=int)
    p = commands.add_parser("experiment")
    p.add_argument("--record", required=True)
    p = commands.add_parser("advise")
    p.add_argument("question")
    p.add_argument("--project", required=True)
    p = commands.add_parser("publish-facts")
    p.add_argument("--batch", required=True)
    for name in ("backup", "restore"):
        p = commands.add_parser(name)
        p.add_argument("--directory", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = Settings.load(args.config)
        if args.command == "restore":
            from .backup import restore
            emit(restore(args.directory, settings))
            return 0
        system = LiteratureSystem(settings)
        if args.command == "inventory":
            sources = system.ingestor.inventory(args.source_root, args.limit)
            emit({"count": len(sources), "bytes": sum(s.size for s in sources), "sources": [s.model_dump(mode="json") for s in sources], "modified": False})
        elif args.command == "index-summaries":
            if args.dry_run:
                root = system.ingestor.root(args.source_root)
                emit({"summaries": len(list(root.glob("*/summary/*.md"))), "modified": False})
            else:
                emit(system.ingestor.index_summaries(args.source_root))
        elif args.command == "ingest":
            rid = system.ingest(args.source_root, args.limit, args.dry_run)
            print(f"Ingestion run: {rid}", file=sys.stderr)
            if args.wait:
                system.work_until_idle()
            emit(system.status(rid))
        elif args.command == "worker":
            if args.once:
                system.work_until_idle()
            else:
                print("Worker running. Ctrl-C to stop.", file=sys.stderr)
                while True:
                    if not system.work_once(args.worker_id):
                        time.sleep(1)
        elif args.command == "status":
            if args.run_id:
                emit(system.status(args.run_id))
            elif args.job_id:
                emit(system.queue.get(args.job_id))
            else:
                emit({"documents": len(system.repo.rows(documents)), "snapshot": system.repo.corpus_snapshot(),
                      "jobs": [{k: j[k] for k in ("job_id", "stage", "state", "attempt", "error")} for j in system.repo.rows(jobs)]})
        elif args.command in ("search", "review-collection"):
            if any(getattr(args, k) is None for k in ("max_cloud_calls", "max_input_tokens", "max_output_tokens")):
                raise ValueError("Collection review requires explicit call/input/output budgets (use zero for local-only)")
            plan = QueryPlan.model_validate_json(Path(args.plan).read_text()) if args.plan else None
            budget = Budget(max_documents=args.max_documents, max_cloud_calls=args.max_cloud_calls,
                            max_input_tokens=args.max_input_tokens, max_output_tokens=args.max_output_tokens)
            result = system.run_search(SearchRequest(question=args.question, plan=plan, budgets=budget,
                           mode="collection_review" if args.command == "review-collection" else "quick", resume_token=args.resume_token))
            print(markdown(result)) if args.format == "markdown" else emit(result)
        elif args.command == "enrich":
            budget = Budget(max_cloud_calls=args.max_cloud_calls, max_input_tokens=args.max_input_tokens, max_output_tokens=args.max_output_tokens)
            emit({"job_id": system.enrich(args.document_id, budget)})
        elif args.command == "serve":
            if args.host not in ("127.0.0.1", "localhost", "::1"):
                raise ValueError("This personal service must bind to localhost; remote authentication is not implemented")
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(system), host=args.host, port=args.port)
        elif args.command == "evaluate":
            from .evaluation import evaluate
            report = evaluate(system, args.dataset)
            if args.output:
                Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
            emit(report)
        elif args.command == "project":
            profile = json.loads(Path(args.profile).read_text())
            if args.project_id:
                if not args.expected_version:
                    raise ValueError("Editing requires --expected-version")
                emit(system.repo.update_project(args.project_id, args.expected_version, profile))
            else:
                emit(system.repo.create_project(profile))
        elif args.command == "experiment":
            emit(system.repo.add_experiment(json.loads(Path(args.record).read_text())))
        elif args.command == "advise":
            emit({"run_id": system.submit_advice(args.question, args.project)})
        elif args.command == "publish-facts":
            from .contracts import PaperFactBatch
            emit(system.evidence.publish_facts(PaperFactBatch.model_validate_json(Path(args.batch).read_text())))
        elif args.command == "backup":
            from .backup import backup
            emit(backup(system, args.directory))
    except (ValueError, OSError) as exc:
        print(f"robotlit: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
