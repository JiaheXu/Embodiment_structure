from pathlib import Path

from labs.summarize_paper import (
    build_pdf_summary_payload,
    build_pdf_summary_prompt,
    build_summary_prompt,
    main,
    paper_summary_path,
    select_papers_to_summarize,
)


def test_paper_summary_path_uses_lab_summary_dir(tmp_path):
    lab_dir = tmp_path / "airlab(basti)"
    paper = {
        "title": "Robot Learning: Control/Planning?",
        "year": 2024,
        "pdf_path": "pdfs/robot.pdf",
    }

    assert paper_summary_path(lab_dir, paper) == lab_dir / "summary" / "2024-robot-learning-control-planning.md"


def test_select_papers_skips_existing_summaries_unless_forced(tmp_path):
    lab_dir = tmp_path / "airlab(basti)"
    pdf_dir = lab_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "robot.pdf").write_bytes(b"%PDF")
    paper = {
        "title": "Robot Learning",
        "year": 2024,
        "pdf_path": "pdfs/robot.pdf",
    }
    paper_summary_path(lab_dir, paper).parent.mkdir(parents=True)
    paper_summary_path(lab_dir, paper).write_text("# Existing\n")

    assert select_papers_to_summarize(lab_dir, [paper], force=False) == []
    assert select_papers_to_summarize(lab_dir, [paper], force=True) == [paper]


def test_select_papers_sorts_by_summary_filename(tmp_path):
    lab_dir = tmp_path / "airlab(basti)"
    pdf_dir = lab_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    for name in ["zeta.pdf", "alpha.pdf", "beta.pdf"]:
        (pdf_dir / name).write_bytes(b"%PDF")
    papers = [
        {"title": "Zeta Robot Paper", "year": 2025, "pdf_path": "pdfs/zeta.pdf"},
        {"title": "Alpha Robot Paper", "year": 2024, "pdf_path": "pdfs/alpha.pdf"},
        {"title": "Beta Robot Paper", "year": 2024, "pdf_path": "pdfs/beta.pdf"},
    ]

    assert [paper["title"] for paper in select_papers_to_summarize(lab_dir, papers)] == [
        "Alpha Robot Paper",
        "Beta Robot Paper",
        "Zeta Robot Paper",
    ]


def test_main_all_regenerates_existing_summaries(tmp_path, monkeypatch):
    lab_dir = tmp_path / "labs" / "airlab(basti)"
    lab_dir.mkdir(parents=True)
    (lab_dir / "link.txt").write_text("https://example.com\n")
    captured = {}

    def fake_summarize_lab(lab_dir, timeout, max_chars, force, dry_run, limit, source):
        captured["force"] = force
        return (0, 0)

    monkeypatch.setattr("labs.summarize_paper.summarize_lab", fake_summarize_lab)

    exit_code = main(["--labs-root", str(tmp_path / "labs"), "--all"])

    assert exit_code == 0
    assert captured["force"] is True


def test_build_summary_prompt_contains_required_sections():
    paper = {
        "title": "Robot Learning",
        "year": 2024,
        "pdf_url": "https://example.com/robot.pdf",
        "page_url": "https://example.com/robot",
    }

    prompt = build_summary_prompt(paper, "Abstract and method text")

    for section in [
        "Problem",
        "Motivation",
        "Method",
        "Results",
        "Limitations",
        "Contributions",
        "Discussion Notes",
    ]:
        assert section in prompt
    assert "Robot Learning" in prompt
    assert "Abstract and method text" in prompt


def test_summary_prompts_include_robot_engineering_fields():
    paper = {
        "title": "Robot Learning",
        "year": 2024,
        "pdf_url": "https://example.com/robot.pdf",
        "page_url": "https://example.com/robot",
    }

    text_prompt = build_summary_prompt(paper, "Abstract and method text")
    pdf_prompt = build_pdf_summary_prompt(paper)

    for prompt in [text_prompt, pdf_prompt]:
        for phrase in [
            "## Robot System Taxonomy",
            "perception / VLA / world model / planner / controller / sensor",
            "## Benchmark And Evaluation",
            "datasets used for training, testing, and validation",
            "dexterous hand",
            "simple gripper",
            "cross-embodiment",
            "new environments",
            "new objects",
            "## Implementation Notes For VLA / Robot Systems",
        ]:
            assert phrase in prompt


def test_summary_prompts_use_keywords_not_fixed_tree_labels():
    paper = {
        "title": "Robot Learning",
        "year": 2024,
        "pdf_url": "https://example.com/robot.pdf",
        "page_url": "https://example.com/robot",
    }

    for prompt in [build_summary_prompt(paper, "Abstract"), build_pdf_summary_prompt(paper)]:
        assert "## Keywords And Features" in prompt
        assert "paper-specific keywords" in prompt
        assert "Do not force the paper into a fixed knowledge-tree branch" in prompt
        assert "methods" in prompt
        assert "tasks" in prompt
        assert "embodiments" in prompt
        assert "benchmarks" in prompt
        assert "datasets" in prompt
        assert "## Knowledge Tree Labels" not in prompt
        assert "primary_branch:" not in prompt


def test_build_pdf_summary_payload_attaches_raw_pdf(tmp_path):
    pdf_path = tmp_path / "robot.pdf"
    pdf_path.write_bytes(b"%PDF raw bytes")
    paper = {
        "title": "Robot Learning",
        "year": 2024,
        "pdf_url": "https://example.com/robot.pdf",
        "page_url": "https://example.com/robot",
    }

    payload = build_pdf_summary_payload("gpt-test", paper, pdf_path)
    content = payload["messages"][1]["content"]

    assert payload["model"] == "gpt-test"
    assert content[0]["type"] == "text"
    assert "Robot Learning" in content[0]["text"]
    assert content[1]["type"] == "file"
    assert content[1]["file"]["filename"] == "robot.pdf"
    assert content[1]["file"]["file_data"].startswith("data:application/pdf;base64,")
