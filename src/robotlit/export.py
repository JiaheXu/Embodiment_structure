import json


def markdown(result):
    lines = ["# Literature search", "", "## Interpretation", "", json.dumps(result.get("resolved_interpretation", {}), ensure_ascii=False),
             "", "## Coverage", "", "```json", json.dumps(result.get("coverage", {}), ensure_ascii=False, indent=2), "```", ""]
    for bucket in ("confirmed", "partial", "unresolved", "excluded", "discovery_only"):
        lines.extend(["## " + bucket.replace("_", " ").title(), ""])
        for paper in result.get(bucket, []):
            lines.extend(["### " + paper["title"], "", f"Document: {paper.get('document_id')}", ""])
            for config in paper.get("configurations", []):
                lines.extend([f"Configuration: {config['label']} ({config['status']})", "",
                              "```json", json.dumps(config, ensure_ascii=False, indent=2), "```", ""])
            for passage in paper.get("source_passages", []):
                lines.extend([f"[PDF page {passage['pdf_page']}]({passage['source_url']}) — block `{passage['block_id']}`", "",
                              "> " + passage["text"].replace("\n", "\n> "), ""])
            if paper.get("summary_hits"):
                lines.extend(["Unverified summary discovery; summary text cannot establish a factual match.", ""])
    if result.get("comparison"):
        lines.extend(["## Comparison", "", "```json", json.dumps(result["comparison"], ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## Usage", "", "```json", json.dumps(result.get("usage", {}), indent=2), "```", ""])
    return "\n".join(lines)
