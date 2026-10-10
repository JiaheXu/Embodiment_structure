from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_JSON_NAME = "knowledge_tree.json"
DEFAULT_HTML_NAME = "knowledge_tree.html"

BRANCH_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Benchmark / Evaluation", ("benchmark", "dataset", "leaderboard", "metric", "evaluation protocol", "challenge")),
    ("Perception", ("perception", "segmentation", "detection", "tracking", "pose estimation", "depth", "odometry", "slam")),
    ("World Model / Representation", ("world model", "scene representation", "occupancy", "3d reconstruction", "nerf", "gaussian splatting", "scene graph")),
    ("VLA / Robot Foundation Models", ("vla", "vision-language-action", "robot foundation model", "generalist robot", "action token")),
    ("VLM / Language Reasoning", ("vlm", "vision-language model", "language reasoning", "multimodal", "llm")),
    ("High-Level Planner", ("task planning", "high-level planner", "long-horizon", "subgoal", "planner")),
    ("Low-Level Planner / Motion Planner", ("motion planning", "trajectory optimization", "path planning", "low-level planner")),
    ("Controller", ("control", "controller", "mpc", "whole-body control", "impedance")),
    ("Manipulation", ("manipulation", "grasp", "dexterous", "hand", "gripper", "mobile manipulation")),
    ("Navigation", ("navigation", "object-goal", "mapless", "waypoint")),
    ("Locomotion", ("locomotion", "quadruped", "humanoid", "legged", "terrain")),
    ("Exploration", ("exploration", "active perception", "frontier", "information gain", "object search")),
    ("Data / Demonstrations", ("demonstration", "dataset", "data augmentation", "imitation", "behavior cloning", "teleop data")),
    ("Teleoperation", ("teleoperation", "teleop", "human demonstration", "remote operation")),
    ("Simulation", ("simulation", "simulator", "sim-to-real", "domain randomization", "synthetic data")),
    ("Digital Twin", ("digital twin", "scene digital twin", "real-time reconstruction", "closed-loop evaluation")),
    ("Sensors / Hardware", ("sensor", "tactile", "lidar", "camera", "depth", "hardware", "proprioception")),
    ("Deployment / Safety", ("deployment", "safety", "robustness", "failure", "real robot", "constraint")),
    ("System Integration", ("system", "pipeline", "integration", "calibration", "latency", "compute")),
]


@dataclass
class SummaryPaper:
    title: str
    year: str
    paper_url: str
    page_url: str
    lab: str
    summary_path: Path
    sections: dict[str, str] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)


def discover_summary_files(labs_root: Path) -> list[Path]:
    files: list[Path] = []
    for folder_name in ("summary", "summaries"):
        files.extend(labs_root.glob(f"*/{folder_name}/*.md"))
    return sorted(files, key=lambda path: str(path).casefold())


def parse_summary_file(path: Path, labs_root: Path) -> SummaryPaper:
    text = path.read_text(errors="replace")
    title = _first_heading(text) or path.stem
    year = _metadata_value(text, "Year")
    paper_url = _metadata_value(text, "Paper")
    page_url = _metadata_value(text, "Page")
    sections = _parse_sections(text)
    keywords = _extract_keywords(sections.get("Keywords And Features", "") or sections.get("Keywords", ""))
    lab = _lab_name(path, labs_root)
    return SummaryPaper(
        title=title,
        year=year,
        paper_url=paper_url,
        page_url=page_url,
        lab=lab,
        summary_path=path,
        sections=sections,
        keywords=keywords,
    )


def normalize_paper_key(paper_url: str, title: str, year: str) -> str:
    arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", paper_url, flags=re.IGNORECASE)
    if arxiv_match:
        return f"arxiv:{arxiv_match.group(1)}"
    if paper_url:
        parsed = urlparse(paper_url)
        clean_url = f"{parsed.netloc}{parsed.path}".rstrip("/").lower()
        if clean_url:
            return f"url:{clean_url}"
    return f"title:{year}:{_slug(title)}"


def classify_branches(title: str, summary_text: str, keywords: list[str]) -> list[str]:
    haystack = " ".join([title, summary_text, " ".join(keywords)]).lower()
    scored: list[tuple[int, int, str]] = []
    for order, (branch, terms) in enumerate(BRANCH_RULES):
        score = sum(1 for term in terms if term in haystack)
        if branch == "Benchmark / Evaluation" and score:
            score += 3
        if score:
            scored.append((-score, order, branch))
    if not scored:
        return ["Uncategorized"]
    return [branch for _, _, branch in sorted(scored)[:4]]


def build_knowledge_tree(labs_root: Path) -> dict[str, object]:
    by_key: dict[str, dict[str, object]] = {}
    for summary_file in discover_summary_files(labs_root):
        parsed = parse_summary_file(summary_file, labs_root)
        summary_text = "\n".join(parsed.sections.values())
        branches = classify_branches(parsed.title, _classification_text(parsed), parsed.keywords)
        key = normalize_paper_key(parsed.paper_url, parsed.title, parsed.year)
        record = by_key.get(key)
        relative_summary = str(parsed.summary_path.relative_to(labs_root))
        if record is None:
            record = {
                "id": f"paper-{len(by_key) + 1}",
                "title": parsed.title,
                "year": parsed.year,
                "paper_url": parsed.paper_url,
                "page_url": parsed.page_url,
                "labs": [],
                "summary_paths": [],
                "branches": [],
                "keywords": [],
                "excerpt": _excerpt(summary_text),
            }
            by_key[key] = record
        _append_unique(record["labs"], parsed.lab)
        _append_unique(record["summary_paths"], relative_summary)
        for branch in branches:
            _append_unique(record["branches"], branch)
        for keyword in parsed.keywords:
            _append_unique(record["keywords"], keyword)

    papers = sorted(by_key.values(), key=lambda item: (str(item["title"]).casefold(), str(item["year"])))
    branches: dict[str, list[dict[str, str]]] = {}
    for paper in papers:
        paper["labs"] = sorted(paper["labs"], key=str.casefold)
        paper["summary_paths"] = sorted(paper["summary_paths"], key=str.casefold)
        for branch in paper["branches"] or ["Uncategorized"]:
            branches.setdefault(branch, []).append({"id": str(paper["id"]), "title": str(paper["title"])})
    branches = {branch: sorted(items, key=lambda item: item["title"].casefold()) for branch, items in sorted(branches.items())}
    return {"branches": branches, "papers": papers}


def write_outputs(tree: dict[str, object], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / DEFAULT_JSON_NAME
    html_path = output_dir / DEFAULT_HTML_NAME
    json_path.write_text(json.dumps(tree, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    html_path.write_text(render_html(tree))
    return json_path, html_path


def render_html(tree: dict[str, object]) -> str:
    tree_json = json.dumps(tree, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Robot Knowledge Tree</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #1f2933; background: #f7f8fa; }}
    header {{ padding: 16px 24px; background: #16202a; color: white; }}
    main {{ display: grid; grid-template-columns: minmax(280px, 36%) 1fr; min-height: calc(100vh - 62px); }}
    nav {{ overflow: auto; padding: 16px; border-right: 1px solid #d8dee4; background: white; }}
    section {{ padding: 20px 24px; overflow: auto; }}
    details {{ margin-bottom: 10px; }}
    summary {{ cursor: pointer; font-weight: 700; }}
    button {{ display: block; width: 100%; margin: 4px 0; padding: 6px 8px; text-align: left; border: 1px solid #d8dee4; background: #fbfcfd; border-radius: 6px; cursor: pointer; }}
    button:hover {{ background: #eef5ff; }}
    .meta {{ color: #5c6b7a; }}
    .tag {{ display: inline-block; margin: 2px; padding: 2px 6px; background: #e8eef5; border-radius: 999px; font-size: 12px; }}
    a {{ color: #0b66c3; }}
    @media (max-width: 760px) {{ main {{ grid-template-columns: 1fr; }} nav {{ border-right: 0; border-bottom: 1px solid #d8dee4; }} }}
  </style>
</head>
<body>
  <header><h1>Robot Knowledge Tree</h1></header>
  <main>
    <nav id="tree"></nav>
    <section id="paper"><p>Select a paper from the tree.</p></section>
  </main>
  <script>
    const DATA = {tree_json};
    const paperById = Object.fromEntries(DATA.papers.map(p => [p.id, p]));
    const tree = document.getElementById('tree');
    const panel = document.getElementById('paper');
    for (const [branch, papers] of Object.entries(DATA.branches)) {{
      const details = document.createElement('details');
      details.open = true;
      const summary = document.createElement('summary');
      summary.textContent = `${{branch}} (${{papers.length}})`;
      details.appendChild(summary);
      for (const item of papers) {{
        const button = document.createElement('button');
        button.textContent = item.title;
        button.onclick = () => showPaper(item.id);
        details.appendChild(button);
      }}
      tree.appendChild(details);
    }}
    function showPaper(id) {{
      const p = paperById[id];
      const tags = (p.keywords || []).map(k => `<span class="tag">${{escapeHtml(k)}}</span>`).join(' ');
      panel.innerHTML = `
        <h2>${{escapeHtml(p.title)}}</h2>
        <p class="meta">${{escapeHtml(p.year || 'unknown')}} · ${{(p.labs || []).map(escapeHtml).join(', ')}}</p>
        <p><strong>Branches:</strong> ${{(p.branches || []).map(escapeHtml).join(', ')}}</p>
        <p><strong>Paper:</strong> ${{p.paper_url ? `<a href="${{escapeAttr(p.paper_url)}}">${{escapeHtml(p.paper_url)}}</a>` : 'N/A'}}</p>
        <p><strong>Page:</strong> ${{p.page_url ? `<a href="${{escapeAttr(p.page_url)}}">${{escapeHtml(p.page_url)}}</a>` : 'N/A'}}</p>
        <p><strong>Summary files:</strong><br>${{(p.summary_paths || []).map(escapeHtml).join('<br>')}}</p>
        <p>${{escapeHtml(p.excerpt || '')}}</p>
        <div>${{tags}}</div>
      `;
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}
    function escapeAttr(value) {{ return escapeHtml(value); }}
  </script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a browsable robot knowledge tree from paper summaries.")
    parser.add_argument("--labs-root", type=Path, default=Path("labs"))
    parser.add_argument("--output-dir", type=Path, default=Path("labs"))
    args = parser.parse_args(argv)

    tree = build_knowledge_tree(args.labs_root)
    json_path, html_path = write_outputs(tree, args.output_dir)
    print(f"[knowledge-tree] papers: {len(tree['papers'])}")
    print(f"[knowledge-tree] json: {json_path}")
    print(f"[knowledge-tree] html: {html_path}")
    return 0


def _first_heading(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _metadata_value(text: str, label: str) -> str:
    pattern = rf"^-\s+\*\*{re.escape(label)}:\*\*\s*(.+)$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _parse_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[start:end].strip()
    return sections


def _extract_keywords(section_text: str) -> list[str]:
    keywords: list[str] = []
    for line in section_text.splitlines():
        line = line.strip()
        if line.startswith("-"):
            line = line.lstrip("-").strip()
            if line and not line.lower().startswith("not clear"):
                keywords.append(line.rstrip("."))
    if not keywords:
        for part in re.split(r"[,;]", section_text):
            cleaned = part.strip(" \n\t-*.")
            if 2 < len(cleaned) < 80 and "not clear" not in cleaned.lower():
                keywords.append(cleaned)
    return keywords[:40]


def _lab_name(path: Path, labs_root: Path) -> str:
    relative = path.relative_to(labs_root)
    return relative.parts[0]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "paper"


def _append_unique(items: list, value: object) -> None:
    if value and value not in items:
        items.append(value)


def _excerpt(text: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    return compact[:limit].rstrip() + ("..." if len(compact) > limit else "")


def _classification_text(paper: SummaryPaper) -> str:
    if paper.keywords:
        return " ".join(paper.keywords)

    parts = [
        _remove_uncertain_lines(paper.sections.get("Robot System Taxonomy", "")),
        _remove_uncertain_lines(paper.sections.get("Keywords And Features", "")),
        _remove_uncertain_lines(paper.sections.get("Keywords", "")),
        _remove_uncertain_lines(paper.sections.get("Method", "")),
        _remove_uncertain_lines(paper.sections.get("Benchmark And Evaluation", "")),
        _remove_uncertain_lines(paper.sections.get("Embodiment And Generalization", "")),
    ]
    return "\n".join(part for part in parts if part)


def _remove_uncertain_lines(text: str) -> str:
    blocked = ("not clear", "does not establish", "cannot be verified", "require verification", "insufficient")
    lines = [line for line in text.splitlines() if not any(term in line.lower() for term in blocked)]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
