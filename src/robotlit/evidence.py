import hashlib

from sqlalchemy import select

from .contracts import EvidenceRef, FacetAssertion, PaperFactBatch, StructuredRecord
from .db import assertions, blocks, configs, documents, records, record_revisions


class EvidenceService:
    def __init__(self, repo):
        self.repo = repo

    def ref(self, block, start=0, end=None):
        return {"document_id": block["document_id"], "generation_id": block["generation_id"],
                "block_id": block["block_id"], "pdf_page": block["pdf_page"], "bbox": block["bbox"],
                "content_sha256": block["content_sha256"], "char_start": start,
                "char_end": len(block["text"]) if end is None else end}

    def resolve(self, reference):
        # Resolved passages carry display fields; validate only their source locator.
        ref = EvidenceRef.model_validate({k: v for k, v in reference.items() if k in EvidenceRef.model_fields}) if isinstance(reference, dict) else reference
        block = self.repo.one(blocks, blocks.c.block_id == str(ref.block_id))
        for field in ("document_id", "generation_id", "pdf_page", "content_sha256", "bbox"):
            expected = getattr(ref, field)
            expected = str(expected) if field.endswith("_id") else expected
            if block[field] != expected:
                raise ValueError(f"Evidence {field} does not match stored source")
        body = block["text"]
        if hashlib.sha256(body.encode()).hexdigest() != ref.content_sha256:
            raise ValueError("Stored block integrity failure")
        end = len(body) if ref.char_end is None else ref.char_end
        if not 0 <= ref.char_start < end <= len(body):
            raise ValueError("Invalid evidence offsets")
        return {**self.ref(block, ref.char_start, end), "text": body[ref.char_start:end], "kind": block["kind"],
                "section": block["section"], "structured": block["structured"],
                "source_url": f"/v1/documents/{ref.document_id}/pdf#page={ref.pdf_page}"}

    def validate_batch(self, batch):
        batch = PaperFactBatch.model_validate(batch) if isinstance(batch, dict) else batch
        registry = {str(c.config_id): str(c.document_id) for c in batch.configs}
        for config in batch.configs:
            self.repo.one(documents, documents.c.document_id == str(config.document_id))
            for ref in config.identity_evidence:
                self.resolve(ref)
                if ref.document_id != config.document_id:
                    raise ValueError("Configuration identity cites a different document")
        for value in [*batch.assertions, *batch.records]:
            cid = str(value.config_id)
            if cid not in registry:
                registry[cid] = self.repo.one(configs, configs.c.config_id == cid)["document_id"]
            fields = list(value.fields.values()) if isinstance(value, StructuredRecord) else [value]
            for field in fields:
                if field.evidence_status in ("supported", "refuted") and not field.evidence_refs:
                    raise ValueError("A supported scientific field requires source evidence")
                for ref in field.evidence_refs:
                    self.resolve(ref)
                    if str(ref.document_id) != registry[cid]:
                        raise ValueError("Assertion references a different document/configuration")
        return batch

    def publish_facts(self, batch, conn=None):
        batch = self.validate_batch(batch)
        if conn is None:
            with self.repo.write() as connection:
                return self.publish_facts(batch, connection)
        revision = self.repo.bump_revision(conn)
        for config in batch.configs:
            payload = config.model_dump(mode="json")
            old = self.repo.rows(configs, configs.c.config_id == str(config.config_id), conn)
            if old:
                if old[0]["payload"] != payload:
                    raise ValueError("Configuration identity is immutable")
            else:
                conn.execute(configs.insert().values(config_id=str(config.config_id), document_id=str(config.document_id),
                             payload=payload, revision=revision))
        for assertion in batch.assertions:
            payload = assertion.model_dump(mode="json")
            old = self.repo.rows(assertions, assertions.c.assertion_id == str(assertion.assertion_id), conn)
            if old:
                if old[0]["payload"] != payload:
                    raise ValueError("Assertion identity is immutable")
            else:
                if assertion.supersedes is not None:
                    previous = self.repo.one(assertions, assertions.c.assertion_id == str(assertion.supersedes), conn)
                    if previous["config_id"] != str(assertion.config_id) or previous["facet"] != assertion.facet:
                        raise ValueError("Correction must keep configuration and facet")
                conn.execute(assertions.insert().values(assertion_id=str(assertion.assertion_id), config_id=str(assertion.config_id),
                             facet=assertion.facet, payload=payload, revision=revision,
                             supersedes=str(assertion.supersedes) if assertion.supersedes else None))
        for record in batch.records:
            payload = record.model_dump(mode="json")
            old = self.repo.rows(records, records.c.record_id == str(record.record_id), conn)
            if old and old[0]["payload"] != payload:
                raise ValueError("Use append-only record correction")
            if not old:
                conn.execute(records.insert().values(record_id=str(record.record_id), config_id=str(record.config_id),
                             record_type=record.record_type, payload=payload, revision=revision))
        for did in {str(c.document_id) for c in batch.configs}:
            conn.execute(documents.update().where(documents.c.document_id == did).values(facts_ready=True))
        return {"revision": revision, "assertions": len(batch.assertions), "records": len(batch.records)}

    def correct(self, assertion_id, value, evidence_refs, reason):
        if not reason.strip():
            raise ValueError("Correction requires a reason")
        old = self.repo.one(assertions, assertions.c.assertion_id == str(assertion_id))
        payload = old["payload"]
        correction = FacetAssertion(config_id=payload["config_id"], facet=payload["facet"], value=value,
                         evidence_refs=evidence_refs, evidence_status="supported", origin="human_review",
                         rationale=reason, supersedes=assertion_id)
        with self.repo.write() as conn:
            if self.repo.postgres:
                conn.execute(select(configs).where(configs.c.config_id == old["config_id"]).with_for_update()).all()
            descendants = self.repo.rows(assertions, assertions.c.supersedes == str(assertion_id), conn)
            if descendants:
                raise ValueError("Assertion already corrected; refresh the current revision")
            self.publish_facts(PaperFactBatch(assertions=[correction]), conn)
        return correction.model_dump(mode="json")

    def correct_record(self, record_id, fields, reason):
        if not reason.strip():
            raise ValueError("Correction requires a reason")
        with self.repo.write() as conn:
            if self.repo.postgres:
                conn.execute(select(records).where(records.c.record_id == str(record_id)).with_for_update()).all()
            original = self.repo.one(records, records.c.record_id == str(record_id), conn)
            history = self.repo.rows(record_revisions, record_revisions.c.record_id == str(record_id), conn)
            payload = max(history, key=lambda r: r["revision"])["payload"] if history else original["payload"]
            record = StructuredRecord.model_validate({**payload, "fields": {**payload["fields"], **fields}})
            self.validate_batch(PaperFactBatch(records=[record]))
            from .db import new_id
            conn.execute(record_revisions.insert().values(revision_id=new_id(), record_id=str(record_id),
                         payload=record.model_dump(mode="json"), revision=self.repo.bump_revision(conn), reason=reason))
            return record.model_dump(mode="json")
