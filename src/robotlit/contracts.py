from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .registry import FACETS, RECORDS, validate_filter, validate_value


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(Contract):
    document_id: UUID
    generation_id: UUID
    block_id: UUID
    pdf_page: int = Field(ge=1)
    bbox: list[float] | None = None
    content_sha256: str
    char_start: int = Field(default=0, ge=0)
    char_end: int | None = Field(default=None, ge=0)


class Predicate(Contract):
    id: str
    facet: str
    operator: Literal["eq", "gte", "lte", "contains", "in"]
    value: Any
    explanation: str = ""

    @model_validator(mode="after")
    def valid(self):
        if self.facet not in FACETS:
            raise ValueError(f"Unknown facet: {self.facet}")
        validate_filter(FACETS[self.facet], self.operator, self.value)
        return self


class RecordFilter(Contract):
    field: str
    operator: Literal["eq", "gte", "lte", "contains", "in"]
    value: Any
    unit: str | None = None
    explanation: str = ""


class RecordRequirement(Contract):
    id: str
    record_type: str
    quantifier: Literal["exists"] = "exists"
    filters: list[RecordFilter] = Field(min_length=1)

    @model_validator(mode="after")
    def valid(self):
        schema = RECORDS.get(self.record_type)
        if schema is None:
            raise ValueError("Unregistered record type")
        for f in self.filters:
            if f.field not in schema:
                raise ValueError(f"Unregistered field: {f.field}")
            validate_filter(schema[f.field], f.operator, f.value)
        return self


class Budget(Contract):
    max_documents: int = Field(default=120, ge=1)
    max_cloud_calls: int = Field(default=8, ge=0)
    max_input_tokens: int = Field(default=60000, ge=0)
    max_output_tokens: int = Field(default=12000, ge=0)
    max_rounds: int = Field(default=3, ge=1, le=3)


class ComparisonRequest(Contract):
    config_ids: list[UUID] = Field(default_factory=list, max_length=120)
    result_ids: list[UUID] = Field(default_factory=list, max_length=240)
    purpose: Literal["performance under reported setups", "causal architectural effect"] = "performance under reported setups"
    protocol_constraints: dict[str, Any] = Field(default_factory=dict)
    requested_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid(self):
        allowed = RECORDS["reported_result"]
        if any(key not in allowed or not key.startswith("protocol.") for key in self.protocol_constraints):
            raise ValueError("Invalid comparison protocol constraint")
        for key, value in self.protocol_constraints.items():
            validate_value(allowed[key], value)
        if any(key not in allowed for key in self.requested_fields):
            raise ValueError("Invalid comparison field")
        return self


class QueryPlan(Contract):
    intent: Literal["find_papers", "compare_methods", "advise_project", "survey_collection"] = "find_papers"
    resolved_terms: dict[str, str] = Field(default_factory=dict)
    hard_requirements: list[Predicate] = Field(default_factory=list)
    soft_preferences: list[Predicate] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list, max_length=4)
    evidence_targets: list[str] = Field(default_factory=list)
    mode: Literal["quick", "collection_review"] = "quick"
    project_id: UUID | None = None
    record_requirements: list[RecordRequirement] = Field(default_factory=list)
    comparison_request: ComparisonRequest | None = None

    @model_validator(mode="after")
    def unique_predicates(self):
        identifiers = [p.id for p in self.hard_requirements + self.record_requirements]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Requirement IDs must be unique")
        return self


class SearchRequest(Contract):
    question: str | None = Field(default=None, max_length=10000)
    plan: QueryPlan | None = None
    project_id: UUID | None = None
    project_version: int | None = None
    mode: Literal["quick", "collection_review"] = "quick"
    budgets: Budget = Field(default_factory=Budget)
    resume_token: str | None = None

    @model_validator(mode="after")
    def query_required(self):
        if not (self.question or self.plan or self.resume_token):
            raise ValueError("Provide a question, plan or resume token")
        if self.mode == "collection_review" and "budgets" not in self.model_fields_set:
            raise ValueError("Collection review requires explicit budgets")
        return self


class MethodConfig(Contract):
    config_id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    label: str
    description: str = ""
    identity_evidence: list[EvidenceRef] = Field(min_length=1)


class FacetAssertion(Contract):
    assertion_id: UUID = Field(default_factory=uuid4)
    config_id: UUID
    facet: str
    value: Any
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    evidence_status: Literal["supported", "refuted", "insufficient", "conflicted"] = "insufficient"
    origin: Literal["llm_extraction", "human_review"] = "llm_extraction"
    rationale: str = ""
    supersedes: UUID | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.facet not in FACETS:
            raise ValueError("Unregistered facet")
        validate_value(FACETS[self.facet], self.value)
        return self


class ScientificField(Contract):
    value: Any = None
    raw_value: Any = None
    value_state: Literal["known", "unknown", "conflicted", "not_applicable"] = "unknown"
    unknown_reason: Literal["not_reviewed", "partially_reviewed", "not_found_in_reviewed_scope", "parse_failure", "ambiguous"] | None = "not_reviewed"
    unit: str | None = None
    convention: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    evidence_status: Literal["supported", "refuted", "insufficient", "conflicted"] = "insufficient"
    value_origin: Literal["paper_reported", "system_derived", "user_annotation"] = "paper_reported"
    derivation: dict[str, Any] | None = None


class StructuredRecord(Contract):
    record_id: UUID = Field(default_factory=uuid4)
    config_id: UUID
    record_type: str
    protocol_id: UUID | None = None
    fields: dict[str, ScientificField] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid(self):
        schema = RECORDS.get(self.record_type)
        if schema is None:
            raise ValueError("Unregistered record type")
        for key, field in self.fields.items():
            if key not in schema:
                raise ValueError(f"Unregistered field: {key}")
            if field.value_state == "known":
                validate_value(schema[key], field.value)
        return self


class PaperFactBatch(Contract):
    configs: list[MethodConfig] = Field(default_factory=list)
    assertions: list[FacetAssertion] = Field(default_factory=list)
    records: list[StructuredRecord] = Field(default_factory=list)
    review_coverage: dict[str, Any] = Field(default_factory=dict)


class PredicateJudgment(Contract):
    id: str
    outcome: Literal["satisfied", "contradicted", "unknown", "conflicted"]
    assertion_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    explanation: str = ""


class SourceRecord(Contract):
    root_id: str
    path: Path
    size: int
    mtime_ns: int
    title: str
    title_source: Literal["unknown", "filename", "manifest", "pdf"] = "unknown"
    year: int | None = None
    summary_path: Path | None = None


class DocumentRef(Contract):
    document_id: UUID
    paper_id: UUID
    sha256: str
    blob_path: str
    title: str
