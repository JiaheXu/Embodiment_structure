from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labs.download_paper import (
    DEFAULT_TIMEOUT_SECONDS,
    discover_lab_dirs,
    format_lab_progress,
    safe_filename,
)


DEFAULT_MAX_CHARS = 90_000
SUMMARY_DIR_NAME = "summary"
USER_AGENT = "Mozilla/5.0 (compatible; lab-paper-summarizer/0.1)"
SUMMARY_SOURCE = "pdf"


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
    return selected


def extract_pdf_text(pdf_path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    text = " ".join(result.stdout.split())
    return text[:max_chars]


def build_summary_prompt(paper: dict[str, object], paper_text: str) -> str:
    title = str(paper.get("title", "Unknown title"))
    year = str(paper.get("year", "unknown"))
    pdf_url = str(paper.get("pdf_url", ""))
    page_url = str(paper.get("page_url", ""))
    return f"""
You are preparing a paper-share research note for a robotics / embodied AI lab survey.
Follow the spirit of paper-share-skills: clear, presentation-ready, problem-first,
method/result focused, and useful for later slides or a reading group.

Write Markdown only. Do not invent facts that are not supported by the paper text.
If the text is insufficient for a section, say "Not clear from extracted text."

Paper metadata:
- Title: {title}
- Year: {year}
- Paper URL: {pdf_url}
- Page URL: {page_url}

Required Markdown structure:

# {title}

- **Year:** {year}
- **Paper:** {pdf_url}
- **Page:** {page_url}

## TL;DR
One concise paragraph.

## Problem
What problem does the paper try to solve? Why is it hard?

## Motivation
Why does this problem matter for robotics, embodied AI, autonomy, or perception?

## Method
Explain the core idea, model/system design, algorithm, data, training, and inference flow.

## Results
Summarize the main experiments, baselines, metrics, and quantitative/qualitative outcomes.

## Robot System Taxonomy
Classify where this paper fits in a robot stack: perception / VLA / world model / planner / controller / sensor /
scene graph / 3D reconstruction / teleoperation / data augmentation / benchmark / simulation / safety / deployment.
List primary and secondary categories, and explain why.

## Benchmark And Evaluation
Identify benchmarks, datasets used for training, testing, and validation, simulators, real-robot platforms,
baselines, metrics, protocols, and leaderboard/challenge settings. Say clearly if it is a benchmark/dataset paper.

## Embodiment And Generalization
For VLA, manipulation, planning, or policy papers, specify whether the robot uses a dexterous hand, simple gripper,
mobile manipulator, humanoid, quadruped, drone, or autonomous vehicle. State whether the method supports
cross-embodiment, new environments, new objects, new tasks, long-horizon tasks, sim-to-real, or multi-robot use.

## Implementation Notes For VLA / Robot Systems
Extract practical integration notes for a VLA engineer and robot system engineer: required sensors, inputs/outputs,
action representation, latency/compute assumptions, data requirements, calibration needs, failure modes, and what
would be hard to reproduce on a real robot.

## Contributions
List the main technical or empirical contributions.

## Limitations
List limitations, assumptions, failure cases, missing experiments, or deployment constraints.

## Discussion Notes
Give reading-group notes: surprising findings, possible follow-up questions, and relation to other work.

## Keywords And Features
List paper-specific keywords and features that describe what this paper is about.
Do not force the paper into a fixed knowledge-tree branch. Include concise tags for methods, tasks, embodiments,
benchmarks, datasets, sensors, representations, policies, planners, controllers, evaluation settings, and deployment
conditions when they are supported by the paper.

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

Write Markdown only. Do not invent facts that are not supported by the PDF.
If the PDF is insufficient for a section, say "Not clear from PDF."

Paper metadata:
- Title: {title}
- Year: {year}
- Paper URL: {pdf_url}
- Page URL: {page_url}

Required Markdown structure:

# {title}

- **Year:** {year}
- **Paper:** {pdf_url}
- **Page:** {page_url}

## TL;DR
One concise paragraph.

## Problem
What problem does the paper try to solve? Why is it hard?

## Motivation
Why does this problem matter for robotics, embodied AI, autonomy, or perception?

## Method
Explain the core idea, model/system design, algorithm, data, training, and inference flow.

## Results
Summarize the main experiments, benchmarks, datasets, baselines, metrics, and quantitative/qualitative outcomes.

## Figures And Tables
Summarize important figures, charts, tables, architecture diagrams, and qualitative examples.

## Robot System Taxonomy
Classify where this paper fits in a robot stack: perception / VLA / world model / planner / controller / sensor /
scene graph / 3D reconstruction / teleoperation / data augmentation / benchmark / simulation / safety / deployment.
List primary and secondary categories, and explain why.

## Benchmark And Evaluation
Identify benchmarks, datasets used for training, testing, and validation, simulators, real-robot platforms,
baselines, metrics, protocols, and leaderboard/challenge settings. Say clearly if it is a benchmark/dataset paper.

## Embodiment And Generalization
For VLA, manipulation, planning, or policy papers, specify whether the robot uses a dexterous hand, simple gripper,
mobile manipulator, humanoid, quadruped, drone, or autonomous vehicle. State whether the method supports
cross-embodiment, new environments, new objects, new tasks, long-horizon tasks, sim-to-real, or multi-robot use.

## Implementation Notes For VLA / Robot Systems
Extract practical integration notes for a VLA engineer and robot system engineer: required sensors, inputs/outputs,
action representation, latency/compute assumptions, data requirements, calibration needs, failure modes, and what
would be hard to reproduce on a real robot.

## Contributions
List the main technical or empirical contributions.

## Limitations
List limitations, assumptions, failure cases, missing experiments, or deployment constraints.

## Discussion Notes
Give reading-group notes: surprising findings, possible follow-up questions, and relation to other work.

## Keywords And Features
List paper-specific keywords and features that describe what this paper is about.
Do not force the paper into a fixed knowledge-tree branch. Include concise tags for methods, tasks, embodiments,
benchmarks, datasets, sensors, representations, policies, planners, controllers, evaluation settings, and deployment
conditions when they are supported by the paper.
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
                    "Return Markdown only."
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
                    "Return Markdown only."
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
    with urlopen(request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8", errors="replace"))
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
    with urlopen(request, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8", errors="replace"))
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
            summary = summarize_pdf_with_ai(paper, pdf_path, timeout=timeout)
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            print(f"[summary:fallback] raw PDF summary failed for {paper.get('title')}: {exc}", file=sys.stderr)
            summary = summarize_paper_from_text(paper, pdf_path, timeout=timeout, max_chars=max_chars)
    else:
        summary = summarize_paper_from_text(paper, pdf_path, timeout=timeout, max_chars=max_chars)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary.rstrip() + "\n")
    return summary_path


def summarize_paper_from_text(paper: dict[str, object], pdf_path: Path, timeout: int, max_chars: int) -> str:
    text = extract_pdf_text(pdf_path, max_chars=max_chars)
    if not text.strip():
        raise RuntimeError(f"no text extracted from {pdf_path}")
    prompt = build_summary_prompt(paper, text)
    return summarize_with_ai(prompt, timeout=timeout)


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
