"""Metrics over judged data only; unlabeled corpus entries are not negatives."""
import json
import time
from pathlib import Path

from .contracts import SearchRequest


def evaluate(system, dataset):
    labels = [json.loads(line) for line in Path(dataset).read_text().splitlines() if line.strip()]
    reports = []
    for label in labels:
        start = time.monotonic()
        result = system.run_search(SearchRequest(question=label["question"], plan=label.get("plan")))
        candidates = [m for name in ("confirmed", "partial", "unresolved", "discovery_only") for m in result[name]]
        ranked = [m.get("document_id") for m in candidates if m.get("document_id")]
        relevance = label.get("relevance", {})
        relevant = {did for did, judged in relevance.items() if judged is True}
        top10_judged = [did for did in ranked[:10] if did in relevance]
        reports.append({"question": label["question"], "split": label.get("split", "unspecified"),
                        "recall_at_50": len(relevant.intersection(ranked[:50])) / len(relevant) if relevant else None,
                        "recall_denominator": len(relevant),
                        "precision_at_10": sum(relevance[did] is True for did in top10_judged) / len(top10_judged) if top10_judged else None,
                        "precision_denominator": len(top10_judged), "unresolved": len(result["unresolved"]),
                        "coverage": result["coverage"], "latency_seconds": time.monotonic() - start, "usage": result["usage"],
                        "hard_criterion_violation_rate": None, "citation_support_rate": None,
                        "extraction_accuracy": None, "annotation_limits": "Only explicitly judged relevance is scored; other metrics require human labels."})
    return {"schema_version": "1.1", "dataset": str(dataset), "questions": len(labels), "reports": reports,
            "configuration": {"parser": system.settings.parser, "retrieval": system.settings.retrieval,
                              "embedding_revision": system.settings.embedding_revision},
            "target_gates_passed": False, "limitations": "Human evidence judgments and held-out production-model baselines are required before corpus-wide enrichment."}
