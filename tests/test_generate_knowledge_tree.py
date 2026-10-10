import json

from labs.generate_knowledge_tree import (
    build_knowledge_tree,
    classify_branches,
    discover_summary_files,
    normalize_paper_key,
    parse_summary_file,
    write_outputs,
)


def test_discovers_summary_files_from_each_lab(tmp_path):
    labs_root = tmp_path / "labs"
    first = labs_root / "airlab(basti)" / "summary"
    second = labs_root / "GRAIL(lerrel)" / "summary"
    ignored = labs_root / "notes"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    ignored.mkdir(parents=True)
    first_file = first / "2024-first.md"
    second_file = second / "2025-second.md"
    first_file.write_text("# First\n")
    second_file.write_text("# Second\n")
    (ignored / "loose.md").write_text("# Ignored\n")

    assert discover_summary_files(labs_root) == [first_file, second_file]


def test_parse_summary_file_extracts_metadata_sections_and_keywords(tmp_path):
    summary = tmp_path / "labs" / "airlab(basti)" / "summary" / "2024-robot.md"
    summary.parent.mkdir(parents=True)
    summary.write_text(
        """# Robot Learning

- **Year:** 2024
- **Paper:** https://arxiv.org/pdf/2401.01234.pdf
- **Page:** https://example.com/robot

## Robot System Taxonomy

- Perception and VLA policy.

## Keywords And Features

- vision-language-action
- dexterous hand
- benchmark
"""
    )

    paper = parse_summary_file(summary, tmp_path / "labs")

    assert paper.title == "Robot Learning"
    assert paper.year == "2024"
    assert paper.paper_url == "https://arxiv.org/pdf/2401.01234.pdf"
    assert paper.lab == "airlab(basti)"
    assert "vision-language-action" in paper.keywords


def test_normalize_paper_key_prefers_arxiv_id():
    assert normalize_paper_key("https://arxiv.org/pdf/2401.01234.pdf", "Title", "2024") == "arxiv:2401.01234"
    assert normalize_paper_key("", "Robot Learning: Control?", "2024") == "title:2024:robot-learning-control"


def test_classify_branches_uses_keywords_and_summary_text():
    branches = classify_branches(
        "Dexterous VLA Benchmark",
        "This paper evaluates a vision-language-action policy with a dexterous hand benchmark.",
        ["dexterous hand", "benchmark", "vision-language-action"],
    )

    assert branches[:3] == ["Benchmark / Evaluation", "VLA / Robot Foundation Models", "Manipulation"]


def test_build_knowledge_tree_deduplicates_papers_and_merges_labs(tmp_path):
    labs_root = tmp_path / "labs"
    first = labs_root / "airlab(basti)" / "summary"
    second = labs_root / "GRAIL(lerrel)" / "summary"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    content = """# Robot Learning

- **Year:** 2024
- **Paper:** https://arxiv.org/pdf/2401.01234.pdf
- **Page:** https://example.com/robot

## Keywords And Features

- benchmark
- manipulation
"""
    (first / "2024-robot.md").write_text(content)
    (second / "2024-robot-copy.md").write_text(content)

    tree = build_knowledge_tree(labs_root)

    assert len(tree["papers"]) == 1
    paper = tree["papers"][0]
    assert paper["labs"] == ["airlab(basti)", "GRAIL(lerrel)"]
    assert "Benchmark / Evaluation" in tree["branches"]


def test_build_knowledge_tree_does_not_classify_from_template_section_titles(tmp_path):
    labs_root = tmp_path / "labs"
    summary_dir = labs_root / "airlab(basti)" / "summary"
    summary_dir.mkdir(parents=True)
    (summary_dir / "2024-control.md").write_text(
        """# Smooth Robot Control

- **Year:** 2024
- **Paper:** https://example.com/control.pdf
- **Page:** https://example.com/control

## Benchmark And Evaluation

No benchmark dataset or leaderboard is reported.

## System Integration

No system integration details are reported.

## Keywords And Features

- controller
- impedance control
"""
    )

    tree = build_knowledge_tree(labs_root)

    paper = tree["papers"][0]
    assert paper["branches"] == ["Controller"]
    assert "Benchmark / Evaluation" not in tree["branches"]
    assert "System Integration" not in tree["branches"]


def test_write_outputs_creates_json_and_html(tmp_path):
    tree = {
        "branches": {"Benchmark / Evaluation": [{"id": "paper-1", "title": "Robot Benchmark"}]},
        "papers": [
            {
                "id": "paper-1",
                "title": "Robot Benchmark",
                "year": "2024",
                "paper_url": "https://example.com/paper.pdf",
                "page_url": "https://example.com",
                "labs": ["airlab(basti)"],
                "summary_paths": ["airlab(basti)/summary/2024-robot.md"],
                "branches": ["Benchmark / Evaluation"],
                "keywords": ["benchmark"],
                "excerpt": "A benchmark paper.",
            }
        ],
    }

    json_path, html_path = write_outputs(tree, tmp_path)

    assert json.loads(json_path.read_text())["papers"][0]["title"] == "Robot Benchmark"
    html = html_path.read_text()
    assert "Robot Knowledge Tree" in html
    assert "Robot Benchmark" in html
