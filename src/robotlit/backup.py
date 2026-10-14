"""Portable logical backup with managed artifacts; never overwrite a live store."""
import json
import shutil
from pathlib import Path

from sqlalchemy import text

from .db import Repository, documents, generations, metadata
from .ingest import file_hash


def backup(system, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Backup destination must be a new directory")
    if destination.is_relative_to(system.settings.data_dir):
        raise ValueError("Backup must be outside the live managed store")
    if any(destination.is_relative_to(root) for root in system.settings.source_roots.values()):
        raise ValueError("Backup cannot write inside source roots")
    destination.mkdir(parents=True)
    tables, files = {}, []
    with system.repo.write() as conn:
        if system.repo.postgres:
            names = ", ".join('"' + table.name + '"' for table in metadata.sorted_tables)
            conn.execute(text(f"LOCK TABLE {names} IN SHARE MODE"))
        for table in metadata.sorted_tables:
            rows = system.repo.rows(table, conn=conn)
            # pgvector returns ndarrays, while portable JSON stores arrays.
            for row in rows:
                for key, value in row.items():
                    if hasattr(value, "tolist"):
                        row[key] = value.tolist()
            tables[table.name] = rows
        managed = set()
        for document in tables["documents"]:
            managed.add(Path(document["blob_path"]))
        for generation in tables["generations"]:
            artifact = Path(generation["artifact_path"])
            managed.update(artifact.parent.glob("*"))
        for source in sorted(managed):
            relative = source.resolve().relative_to(system.settings.data_dir)
            target = destination / "artifacts" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            files.append({"path": str(relative), "sha256": file_hash(target)})
    manifest = {"schema_version": "1.1", "tables": tables, "files": files,
                "original_data_dir": str(system.settings.data_dir), "database_kind": system.repo.engine.dialect.name}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return {"backup_dir": str(destination), "files": len(files), "tables": len(tables)}


def restore(source, settings):
    source = Path(source).resolve()
    if settings.data_dir.exists() and any(settings.data_dir.iterdir()):
        raise ValueError("Restore target data directory must be empty")
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["schema_version"] != "1.1":
        raise ValueError("Incompatible backup schema")
    validated = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        target = (settings.data_dir / relative).resolve()
        stored = (source / "artifacts" / relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(settings.data_dir) or not stored.is_relative_to(source / "artifacts"):
            raise ValueError("Unsafe backup artifact path")
        if file_hash(stored) != entry["sha256"]:
            raise ValueError("Backup artifact checksum mismatch")
        validated.append((stored, target))
    repo = Repository(settings.database_url)
    repo.initialize()
    with repo.write() as conn:
        if any(repo.rows(table, conn=conn) for table in metadata.sorted_tables if table.name != "revisions"):
            raise ValueError("Restore database must be empty")
        # Validate all managed paths before copying or inserting.
        old_root = Path(manifest["original_data_dir"])
        for table_name, key in (("documents", "blob_path"), ("generations", "artifact_path")):
            for row in manifest["tables"][table_name]:
                old_path = Path(row[key])
                if not old_path.is_relative_to(old_root):
                    raise ValueError("Invalid managed artifact reference in backup")
                row[key] = str(settings.data_dir / old_path.relative_to(old_root))
        for stored, target in validated:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stored, target)
        for table in metadata.sorted_tables:
            rows = manifest["tables"][table.name]
            if table.name == "revisions":
                conn.execute(table.delete())
            if rows:
                conn.execute(table.insert(), rows)
        if repo.postgres:
            # Sequence values are not included in a logical row export.
            conn.execute(text("SELECT setval(pg_get_serial_sequence('run_events','event_id'), COALESCE((SELECT max(event_id) FROM run_events),1), EXISTS(SELECT 1 FROM run_events))"))
    return {"files": len(validated), "restored": True}
