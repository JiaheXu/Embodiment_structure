from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labs.download_paper import (
    DEFAULT_TIMEOUT_SECONDS,
    discover_lab_dirs,
    format_lab_progress,
    is_retryable_network_error,
    read_url_with_retries,
    safe_filename,
)


DEFAULT_MAX_CHARS = 90_000
DEFAULT_SUMMARY_ATTEMPTS = 4  # Initial request plus three retries.
SUMMARY_DIR_NAME = "summary"
SUMMARY_JSON_DIR_NAME = "summary_json"
USER_AGENT = "Mozilla/5.0 (compatible; lab-paper-summarizer/0.1)"
SUMMARY_SOURCE = "pdf"
SUMMARY_SCHEMA_VERSION = 1


def load_papers(lab_dir: Path) -> list[dict[str, object]]:
    manifest = lab_dir / "papers.json"
    if not manifest.exists():
        return []
    data = json.loads(manifest.read_text())
    return data if isinstance(data, list) else []


def paper_summary_path(lab_dir: Path, paper: dict[str, object]) -> Path:
    year = str(paper.get("year", "unknown"))
    title = str(paper.get("title", "paper"))
    return lab_dir / SUMMARY_DIR_NAME / f"{year}-{safe_filename(title)}.md"


def paper_summary_json_path(lab_dir: Path, paper: dict[str, object]) -> Path:
    year = str(paper.get("year", "unknown"))
    title = str(paper.get("title", "paper"))
    return lab_dir / SUMMARY_JSON_DIR_NAME / f"{year}-{safe_filename(title)}.json"


def select_papers_to_summarize(
    lab_dir: Path,
    papers: list[dict[str, object]],
    force: bool = False,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for paper in papers:
        pdf_path = lab_dir / str(paper.get("pdf_path", ""))
        if not pdf_path.is_file():
            continue
        if not force and paper_summary_path(lab_dir, paper).exists():
            continue
        selected.append(paper)
    return sorted(selected, key=lambda paper: paper_summary_path(lab_dir, paper).name.casefold())


def extract_pdf_text(pdf_path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    text = " ".join(result.stdout.split())
    return text[:max_chars]


def _summary_json_schema_prompt(missing_phrase: str) -> str:
    return f"""
Return JSON only. Do not return Markdown, code fences, comments, or extra prose.
Do not invent facts that are not supported by the source. If the source is insufficient for a field, use "{missing_phrase}".

The JSON will be rendered into Markdown sections named:
## Abstract
## TL;DR
## Problem
## Motivation
## Method
## Results
## Figures And Tables
## Robot System Taxonomy
## Benchmark And Evaluation
## Embodiment And Generalization
## Evidence Strength
## Data And Training Setup
## Deployment Practicality
## Implementation Notes For VLA / Robot Systems
## Contributions
## Limitations
## Comparison Summary
## Failure Modes
## Discussion Notes
## Index Tags
## Keywords And Features

Use this exact top-level JSON object shape:
{{
  "summary_schema_version": {SUMMARY_SCHEMA_VERSION},
  "abstract": "paper abstract or a faithful abstract-style summary from the source, useful for indexing and retrieval",
  "tldr": "one concise paragraph",
  "problem": "what problem the paper solves and why it is hard",
  "motivation": "why it matters for robotics, embodied AI, autonomy, or perception",
  "method": "core idea, system design, algorithm, data, training, and inference flow",
  "results": "main experiments, baselines, metrics, and quantitative/qualitative outcomes",
  "figures_and_tables": "important figures, charts, tables, architecture diagrams, and qualitative examples",
  "robot_system_taxonomy": "primary and secondary stack categories and why; consider perception / VLA / world model / planner / controller / sensor / scene graph / 3D reconstruction / teleoperation / data augmentation / benchmark / simulation / safety / deployment",
  "benchmark_and_evaluation": {{
    "summary": "benchmarks, datasets used for training, testing, and validation, simulators, real-robot platforms, protocols, leaderboard/challenge settings",
    "task_suite": ["Evaluation task suite: task names, task categories, horizon length, object set, environment set, train/test split"],
    "baselines_compared_against": ["baselines compared against: baseline names, model/policy types, oracle variants, human/expert references, prior SOTA"],
    "task_performance": [
      {{
        "task_name": "tested task name",
        "task_setup": "objects, environment, horizon, embodiment, train/test split, and protocol",
        "paper_performance": "per-task performance: score, success rate, completion rate, reward, error, or qualitative result",
        "baseline_performance": "baseline score on the same task when reported",
        "relative_result": "win/loss/tie or improvement amount",
        "notes": "failure criteria, trial count, variance, or caveats"
      }}
    ],
    "metrics_and_success_rates": ["per-task performance and overall performance: success rates, aggregate score, mean/std or standard deviation, trials, confidence intervals, failure criteria"],
    "overall_performance": "overall performance across all tested tasks, including aggregate success rate or score and strongest baseline comparison",
    "ablations": ["component changed, what it tests, quantitative effect"]
  }},
  "embodiment_and_generalization": "dexterous hand/simple gripper/mobile manipulator/humanoid/etc.; cross-embodiment, new environments, new objects, new tasks, long horizon, sim-to-real, multi-robot",
  "evidence_strength": {{
    "real_robot_evidence": "Real robot evidence: yes/no, robot platform, trials, task count, object count, environment count",
    "simulation_only": "Simulation-only: yes/no, simulator name, sim task count, sim-to-real evidence",
    "baseline_strength": "Baseline strength: weak/fair/strong with reason",
    "statistical_reliability": "seeds, trials, mean/std, confidence intervals, significance tests",
    "reproducibility": "code, data, model weights, benchmark scripts, hardware details, availability"
  }},
  "data_and_training_setup": {{
    "training_data_source": "Training data source: real robot, teleoperation, human videos, internet videos, simulation, synthetic data, scripted expert, mixed",
    "dataset_size": "trajectories, episodes, hours, images, videos, scenes, objects, tasks, tokens",
    "data_collection_cost": "Data collection cost: hardware, operators, time, annotation, reset burden",
    "training_setup": "pretraining, fine-tuning, policy learning, RL, imitation learning, offline/online data",
    "labels_annotations": "language, action, segmentation, pose, depth, force/contact, task labels"
  }},
  "deployment_practicality": {{
    "hardware_required": "robot, hand/gripper, cameras, tactile sensors, force sensors, compute",
    "real_time_capable": "Real-time capable: yes/no/unclear, latency, inference rate, Control frequency",
    "calibration_burden": "camera, hand-eye, tactile, object models, environment setup",
    "safety_constraints": "collision handling, force limits, reset procedure, supervision",
    "engineering_difficulty": "hardest parts to reproduce"
  }},
  "implementation_notes": {{
    "summary": "practical integration notes for VLA and robot system engineers",
    "required_inputs": ["required inputs: RGB / RGB-D / depth / point cloud / tactile / proprioception / language / robot state / object pose / calibration / maps / demonstrations / mixed"],
    "input_constraints": ["input constraints: exact camera positions, fixed viewpoints, camera intrinsics/extrinsics, object models, known poses, synced sensor data, temporal history, action chunk length, robot morphology, workspace assumptions"],
    "camera_sensor_setup": "camera/sensor setup: number and placement of cameras, wrist/external cameras, tactile/force sensors, depth sensors, calibration status, whether exact camera positions are required",
    "synchronization_requirements": "synced sensor data requirements: whether RGB/depth/tactile/proprioception/action streams must be time-aligned and at what frequency",
    "calibration_requirements": "calibration requirements: camera intrinsics/extrinsics, hand-eye calibration, robot kinematics, tactile calibration, object frames, world frame",
    "system_input_modality": "RGB / RGB-D / depth / point cloud / tactile / proprioception / language / mixed; include views, temporal history, state inputs, simulated or real",
    "system_output_action_representation": "system output action representation: end-effector pose, joint positions, joint velocities/torques, gripper command, waypoint, 3D/4D trajectory, contact/force target, affordance/heatmap, plan, code, or other"
  }},
  "contributions": ["main technical or empirical contribution"],
  "limitations": ["limitations, assumptions, failure cases, missing experiments, deployment constraints"],
  "comparison_summary": {{
    "main_baseline": "strongest or most relevant baseline",
    "improvement_over_strongest_baseline": "Improvement over strongest baseline: reported improvement",
    "best_reported_metric": "best metric",
    "weakest_reported_metric": "weakest metric",
    "tasks_where_it_wins": ["Tasks where it wins"],
    "tasks_where_it_loses": ["task"],
    "generalization_tested": ["objects", "scenes", "embodiments", "language", "long horizon", "sim-to-real"]
  }},
  "failure_modes": {{
    "common_failure_cases": ["Common failure cases"],
    "out_of_distribution_failures": ["failure"],
    "perception_failures": ["failure"],
    "control_contact_failures": ["failure"],
    "language_planning_failures": ["failure"],
    "hardware_specific_failures": ["failure"]
  }},
  "discussion_notes": "surprising findings, follow-up questions, relation to other work",
  "index_tags": {{
    "input": ["machine-friendly input tags"],
    "output": ["machine-friendly output tags"],
    "robot": ["machine-friendly robot tags"],
    "task": ["machine-friendly task tags"],
    "evaluation": ["machine-friendly evaluation tags"],
    "generalization": ["machine-friendly generalization tags"],
    "assets": ["machine-friendly dataset/code/benchmark tags"]
  }},
  "keywords_and_features": ["paper-provided keywords only: copy explicit author/paper keywords exactly when present; use an empty list if the paper does not provide explicit keywords"]
}}

Do not infer, invent, or generate keywords for "keywords_and_features".
Do not force the paper into a fixed knowledge-tree branch. The knowledge graph will derive groups later from
"keywords_and_features", "index_tags", title, abstract, and summary text.
""".strip()


def build_summary_prompt(paper: dict[str, object], paper_text: str) -> str:
    title = str(paper.get("title", "Unknown title"))
    year = str(paper.get("year", "unknown"))
    pdf_url = str(paper.get("pdf_url", ""))
    page_url = str(paper.get("page_url", ""))
    return f"""
You are preparing a paper-share research note for a robotics / embodied AI lab survey.
Follow the spirit of paper-share-skills: clear, presentation-ready, problem-first,
method/result focused, and useful for later slides or a reading group.

{_summary_json_schema_prompt("Not clear from extracted text")}

Paper metadata:
- Title: {title}
- Year: {year}
- Paper URL: {pdf_url}
- Page URL: {page_url}

Extracted paper text:
{paper_text}
""".strip()


def build_pdf_summary_prompt(paper: dict[str, object]) -> str:
    title = str(paper.get("title", "Unknown title"))
    year = str(paper.get("year", "unknown"))
    pdf_url = str(paper.get("pdf_url", ""))
    page_url = str(paper.get("page_url", ""))
    return f"""
You are preparing a paper-share research note for a robotics / embodied AI lab survey.
Use the attached PDF as the source of truth, including figures, charts, tables,
architecture diagrams, benchmarks, datasets, qualitative results, and appendices
when available.

{_summary_json_schema_prompt("Not clear from PDF")}

Paper metadata:
- Title: {title}
- Year: {year}
- Paper URL: {pdf_url}
- Page URL: {page_url}
""".strip()


def build_pdf_summary_payload(model: str, paper: dict[str, object], pdf_path: Path) -> dict[str, object]:
    encoded_pdf = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write accurate, source-grounded academic paper summaries. "
                    "Return JSON only using the requested schema."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_pdf_summary_prompt(paper)},
                    {
                        "type": "file",
                        "file": {
                            "filename": pdf_path.name,
                            "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                        },
                    },
                ],
            },
        ],
        "temperature": 0,
    }


def summarize_with_ai(prompt: str, timeout: int) -> str:
    ai_url = os.environ.get("AI_BASE_URL") or os.environ.get("OPENAI_URL")
    ai_key = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    ai_model = os.environ.get("AI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-6-astra"
    if not ai_url:
        raise RuntimeError("AI_BASE_URL or OPENAI_URL is required")

    payload = {
        "model": ai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write accurate, source-grounded academic paper summaries. "
                    "Return JSON only using the requested schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if ai_key:
        headers["Authorization"] = f"Bearer {ai_key}"
    request = Request(
        ai_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    data, _ = read_url_with_retries(request, timeout=timeout, attempts=DEFAULT_SUMMARY_ATTEMPTS)
    raw = json.loads(data.decode("utf-8", errors="replace"))
    return _extract_chat_content(raw)


def summarize_pdf_with_ai(paper: dict[str, object], pdf_path: Path, timeout: int) -> str:
    ai_url = os.environ.get("AI_BASE_URL") or os.environ.get("OPENAI_URL")
    ai_key = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    ai_model = os.environ.get("AI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-6-astra"
    if not ai_url:
        raise RuntimeError("AI_BASE_URL or OPENAI_URL is required")

    payload = build_pdf_summary_payload(ai_model, paper, pdf_path)
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if ai_key:
        headers["Authorization"] = f"Bearer {ai_key}"
    request = Request(
        ai_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    data, _ = read_url_with_retries(request, timeout=timeout, attempts=DEFAULT_SUMMARY_ATTEMPTS)
    raw = json.loads(data.decode("utf-8", errors="replace"))
    return _extract_chat_content(raw)


def summarize_paper(
    lab_dir: Path,
    paper: dict[str, object],
    timeout: int,
    max_chars: int,
    source: str = SUMMARY_SOURCE,
    dry_run: bool = False,
) -> Path | None:
    summary_path = paper_summary_path(lab_dir, paper)
    pdf_path = lab_dir / str(paper.get("pdf_path", ""))
    if dry_run:
        print(f"[dry-run] summarize {paper.get('title')} -> {summary_path}")
        return summary_path

    if source == "pdf":
        try:
            raw_summary = summarize_pdf_with_ai(paper, pdf_path, timeout=timeout)
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            if is_retryable_network_error(exc):
                raise
            print(f"[summary:fallback] raw PDF summary failed for {paper.get('title')}: {exc}", file=sys.stderr)
            raw_summary = summarize_paper_from_text(paper, pdf_path, timeout=timeout, max_chars=max_chars)
    else:
        raw_summary = summarize_paper_from_text(paper, pdf_path, timeout=timeout, max_chars=max_chars)
    summary_data = parse_summary_json_response(raw_summary)
    summary = render_summary_markdown(summary_data, paper) if summary_data is not None else raw_summary
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary.rstrip() + "\n")
    if summary_data is not None:
        json_path = paper_summary_json_path(lab_dir, paper)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return summary_path


def summarize_paper_from_text(paper: dict[str, object], pdf_path: Path, timeout: int, max_chars: int) -> str:
    text = extract_pdf_text(pdf_path, max_chars=max_chars)
    if not text.strip():
        raise RuntimeError(f"no text extracted from {pdf_path}")
    prompt = build_summary_prompt(paper, text)
    return summarize_with_ai(prompt, timeout=timeout)


def parse_summary_json_response(response_text: str) -> dict[str, object] | None:
    text = response_text.strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def render_summary_markdown(summary: dict[str, object], paper: dict[str, object]) -> str:
    title = str(paper.get("title", "Unknown title"))
    year = str(paper.get("year", "unknown"))
    pdf_url = str(paper.get("pdf_url", ""))
    page_url = str(paper.get("page_url", ""))
    lines = [
        f"# {title}",
        "",
        f"- **Year:** {year}",
        f"- **Paper:** {pdf_url}",
        f"- **Page:** {page_url}",
        "",
    ]
    sections: list[tuple[str, object]] = [
        ("Abstract", summary.get("abstract")),
        ("TL;DR", summary.get("tldr")),
        ("Problem", summary.get("problem")),
        ("Motivation", summary.get("motivation")),
        ("Method", summary.get("method")),
        ("Results", summary.get("results")),
        ("Figures And Tables", summary.get("figures_and_tables")),
        ("Robot System Taxonomy", summary.get("robot_system_taxonomy")),
        ("Benchmark And Evaluation", summary.get("benchmark_and_evaluation")),
        ("Embodiment And Generalization", summary.get("embodiment_and_generalization")),
        ("Evidence Strength", summary.get("evidence_strength")),
        ("Data And Training Setup", summary.get("data_and_training_setup")),
        ("Deployment Practicality", summary.get("deployment_practicality")),
        ("Implementation Notes For VLA / Robot Systems", summary.get("implementation_notes")),
        ("Contributions", summary.get("contributions")),
        ("Limitations", summary.get("limitations")),
        ("Comparison Summary", summary.get("comparison_summary")),
        ("Failure Modes", summary.get("failure_modes")),
        ("Discussion Notes", summary.get("discussion_notes")),
        ("Index Tags", summary.get("index_tags")),
        ("Keywords And Features", summary.get("keywords_and_features")),
    ]
    for heading, value in sections:
        lines.append(f"## {heading}")
        lines.extend(_render_markdown_value(value))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown_value(value: object) -> list[str]:
    if value is None or value == "":
        return ["Not reported."]
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return _render_markdown_list(value)
    if isinstance(value, dict):
        return _render_markdown_dict(value)
    return [str(value)]


def _render_markdown_list(values: list[object], indent: int = 0) -> list[str]:
    if not values:
        return ["Not reported."]
    lines: list[str] = []
    prefix = "  " * indent
    for value in values:
        if isinstance(value, dict):
            compact = ", ".join(f"{_humanize_key(str(key))}: {_compact_markdown_value(item)}" for key, item in value.items())
            lines.append(f"{prefix}- {compact}")
        elif isinstance(value, list):
            lines.append(f"{prefix}-")
            lines.extend(_render_markdown_list(value, indent + 1))
        else:
            lines.append(f"{prefix}- {value}")
    return lines


def _render_markdown_dict(values: dict[object, object]) -> list[str]:
    if not values:
        return ["Not reported."]
    lines: list[str] = []
    for key, value in values.items():
        label = _humanize_key(str(key))
        if isinstance(value, list):
            lines.append(f"- {label}: {_compact_markdown_value(value)}")
        elif isinstance(value, dict):
            lines.append(f"- {label}:")
            for child_key, child_value in value.items():
                child_label = _humanize_key(str(child_key))
                lines.append(f"  - {child_label}: {_compact_markdown_value(child_value)}")
        else:
            lines.append(f"- {label}: {_compact_markdown_value(value)}")
    return lines


def _compact_markdown_value(value: object) -> str:
    if value is None or value == "":
        return "Not reported."
    if isinstance(value, list):
        return ", ".join(_compact_markdown_value(item) for item in value) if value else "Not reported."
    if isinstance(value, dict):
        return "; ".join(f"{_humanize_key(str(key))}: {_compact_markdown_value(item)}" for key, item in value.items())
    return str(value)


def _humanize_key(key: str) -> str:
    return key.replace("_", " ")


def summarize_lab(
    lab_dir: Path,
    timeout: int,
    max_chars: int,
    force: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    source: str = SUMMARY_SOURCE,
) -> tuple[int, int]:
    papers = load_papers(lab_dir)
    selected = select_papers_to_summarize(lab_dir, papers, force=force)
    if limit is not None:
        selected = selected[:limit]
    print(f"[summary:scan] {lab_dir.name}: {len(papers)} papers, {len(selected)} pending")

    done = 0
    for index, paper in enumerate(selected, start=1):
        title = str(paper.get("title", "Unknown title"))
        print(f"[summary:paper {index}/{len(selected)}] start: {title}")
        try:
            output_path = summarize_paper(
                lab_dir,
                paper,
                timeout=timeout,
                max_chars=max_chars,
                source=source,
                dry_run=dry_run,
            )
        except (subprocess.CalledProcessError, HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            print(f"[summary:error] {title}: {exc}", file=sys.stderr)
            continue
        done += 1
        print(f"[summary:paper {index}/{len(selected)}] done: {output_path}")
    return (len(selected), done)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize downloaded lab papers into Markdown files.")
    parser.add_argument("--labs-root", type=Path, default=Path("labs"))
    parser.add_argument("--lab", default=None, help="Only summarize one lab folder name.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate existing summaries. By default, papers with summary files are skipped.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Summarize all papers, including papers that already have summary files.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=("pdf", "text"), default=SUMMARY_SOURCE, help="Send the raw PDF when supported, or extracted text.")
    parser.add_argument("--limit", type=int, default=None, help="Limit papers per lab.")
    parser.add_argument("--lab-limit", type=int, default=None, help="Limit number of labs.")
    args = parser.parse_args(argv)

    lab_dirs = discover_lab_dirs(args.labs_root)
    if args.lab:
        lab_dirs = [path for path in lab_dirs if path.name == args.lab]
    if args.lab_limit is not None:
        lab_dirs = lab_dirs[: args.lab_limit]
    if not lab_dirs:
        print(f"No lab directories found under {args.labs_root}", file=sys.stderr)
        return 1

    failures = 0
    total_labs = len(lab_dirs)
    print(f"[summary:progress] queued {total_labs} labs")
    for index, lab_dir in enumerate(lab_dirs, start=1):
        print(format_lab_progress(lab_dir, index, total_labs, "summary-start"))
        pending, done = summarize_lab(
            lab_dir,
            timeout=args.timeout,
            max_chars=args.max_chars,
            force=args.force or args.all,
            dry_run=args.dry_run,
            limit=args.limit,
            source=args.source,
        )
        if pending != done:
            failures += 1
        print(
            f"{format_lab_progress(lab_dir, index, total_labs, 'summary-done')} | "
            f"pending: {pending}, done: {done}"
        )
    print(f"[summary:progress] finished {total_labs - failures}/{total_labs} labs; failed: {failures}")
    return 1 if failures else 0


def _extract_chat_content(raw: object) -> str:
    if not isinstance(raw, dict):
        return ""
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
    output = raw.get("output_text")
    return output if isinstance(output, str) else ""


if __name__ == "__main__":
    raise SystemExit(main())
