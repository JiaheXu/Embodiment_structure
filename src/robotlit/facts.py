"""Deterministic four-state evaluation; absence is never a factual negative."""
from .contracts import FacetAssertion, PredicateJudgment


def matches(operator, actual, desired):
    if operator == "eq":
        return actual == desired
    if operator == "gte":
        return actual >= desired
    if operator == "lte":
        return actual <= desired
    if operator == "contains":
        return desired in actual
    if operator == "in":
        return actual in desired
    raise ValueError("Unregistered operator")


def evaluate_predicate(predicate, assertions):
    relevant = [FacetAssertion.model_validate(a) if isinstance(a, dict) else a for a in assertions]
    relevant = [a for a in relevant if a.facet == predicate.facet]
    supported = [a for a in relevant if a.evidence_status == "supported" and a.evidence_refs]
    if any(a.evidence_status == "conflicted" for a in relevant):
        outcome = "conflicted"
    elif not supported:
        outcome = "unknown"
    elif any(a.value != supported[0].value for a in supported[1:]):
        outcome = "conflicted"
    else:
        outcome = "satisfied" if matches(predicate.operator, supported[0].value, predicate.value) else "contradicted"
    return PredicateJudgment(id=predicate.id, outcome=outcome, assertion_ids=[str(a.assertion_id) for a in supported],
                             evidence_refs=[ref for a in supported for ref in a.evidence_refs])


def classify(outcomes):
    if not outcomes:
        return "discovery_only"
    if all(o == "satisfied" for o in outcomes):
        return "confirmed"
    if "contradicted" not in outcomes:
        return "unresolved"
    return "partial" if "satisfied" in outcomes else "excluded"


def normalize_number(value, from_unit, to_unit):
    factors = {("percent", "fraction"): 0.01, ("fraction", "percent"): 100,
               ("milliseconds", "seconds"): 0.001, ("seconds", "milliseconds"): 1000,
               ("degrees", "radians"): __import__("math").pi / 180,
               ("radians", "degrees"): 180 / __import__("math").pi}
    if from_unit == to_unit:
        return value, None
    if (from_unit, to_unit) not in factors:
        raise ValueError("Incompatible units; no supported conversion")
    factor = factors[from_unit, to_unit]
    formula = "value / 100" if (from_unit, to_unit) == ("percent", "fraction") else f"value * {factor}"
    return value * factor, {"formula": formula, "from_unit": from_unit, "to_unit": to_unit}


def evaluate_record_requirement(requirement, records, complete_inventory=False):
    outcomes, witnesses = [], []
    for record in records:
        if record.get("record_type", requirement.record_type) != requirement.record_type:
            continue
        fields = record.get("fields", {})
        states, refs = [], []
        for f in requirement.filters:
            field = fields.get(f.field, {})
            if field.get("value_state") == "conflicted" or field.get("evidence_status") == "conflicted":
                states.append("conflicted")
            elif field.get("value_state") != "known" or field.get("evidence_status") != "supported":
                states.append("unknown")
            else:
                actual = field.get("value")
                try:
                    if f.unit is not None:
                        actual, _ = normalize_number(actual, field.get("unit"), f.unit)
                    states.append("satisfied" if matches(f.operator, actual, f.value) else "contradicted")
                    refs.extend(field.get("evidence_refs", []))
                except (ValueError, TypeError):
                    states.append("unknown")
        if all(s == "satisfied" for s in states):
            return PredicateJudgment(id=requirement.id, outcome="satisfied", evidence_refs=refs,
                                     explanation=f"One {requirement.record_type} record satisfies every filter")
        outcomes.append("contradicted" if "contradicted" in states else "conflicted" if "conflicted" in states else "unknown")
    result = "contradicted" if complete_inventory and outcomes and all(o == "contradicted" for o in outcomes) else "conflicted" if "conflicted" in outcomes else "unknown"
    return PredicateJudgment(id=requirement.id, outcome=result, explanation="No complete satisfying witness in reviewed records")


def assess_comparison(results, purpose="performance under reported setups"):
    required = ["metric_name", "unit", "aggregation", "protocol.benchmark", "protocol.tasks", "protocol.split",
                "protocol.robot", "protocol.success_definition", "protocol.execution"]
    def get(row, key):
        current = row
        for segment in key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
        return current
    missing = sorted({key for key in required if any(get(row, key) in (None, "", []) for row in results)})
    differences = {key: [get(r, key) for r in results] for key in required if results and any(get(r, key) != get(results[0], key) for r in results[1:])}
    versions = [get(row, "protocol.version") for row in results]
    if any(v is not None for v in versions):
        if any(v is None for v in versions):
            missing.append("protocol.version")
        elif len(set(versions)) > 1:
            differences["protocol.version"] = versions
    definitions = [row.get("metric_definition") for row in results]
    if any(d is not None for d in definitions):
        if any(d is None for d in definitions):
            missing.append("metric_definition")
        elif len(set(definitions)) > 1:
            differences["metric_definition"] = definitions
    optional = ["pretraining", "training_data", "sensors", "compute", "adaptation", "measurement_origin"]
    conditions = {k: [r.get(k) for r in results] for k in optional if results and any(r.get(k) != results[0].get(k) for r in results[1:])}
    if purpose == "causal architectural effect":
        uncontrolled = [key for key in optional if any(row.get(key) is None for row in results)]
        missing.extend(uncontrolled)
    outcome = "insufficient_context" if missing or len(results) < 2 else "incomparable" if differences else "conditional" if conditions else "comparable"
    return {"outcome": outcome, "purpose": purpose, "missing": missing, "differences": differences,
            "conditions": conditions, "results": results, "rule_version": "1.1", "ranked": False}
