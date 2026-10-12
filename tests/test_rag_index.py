import json

from labs.build_rag_index import build_rag_index, main, search_index


def _write_paper(labs_root, lab_name, title, keywords, method):
    lab_dir = labs_root / lab_name
    (lab_dir / "summary_json").mkdir(parents=True)
    (lab_dir / "papers.json").write_text(
        json.dumps(
            [
                {
                    "title": title,
                    "year": 2025,
                    "pdf_url": "https://arxiv.org/pdf/2501.01234.pdf",
                    "page_url": "https://example.com/project",
                    "pdf_path": "pdfs/paper.pdf",
                }
            ]
        )
    )
    (lab_dir / "summary_json" / "2025-robot-paper.json").write_text(
        json.dumps(
            {
                "abstract": "A robot policy paper about manipulation.",
                "method": method,
                "benchmark_and_evaluation": {"summary": "Real robot manipulation tasks."},
                "implementation_notes": {
                    "required_inputs": ["RGB-D", "language"],
                    "system_output_action_representation": "end-effector pose",
                },
                "keywords_and_features": keywords,
                "index_tags": {"input": ["rgb-d"], "task": ["manipulation"], "robot": ["mobile manipulator"]},
            }
        )
    )


def test_build_rag_index_writes_papers_chunks_and_embeddings(tmp_path):
    labs_root = tmp_path / "labs"
    output_dir = tmp_path / "rag_index"
    _write_paper(labs_root, "airlab", "Robot Paper", ["grasping"], "Uses RGB-D observations.")

    stats = build_rag_index(labs_root, output_dir)

    assert stats == {"papers": 1, "chunks": 4}
    assert (output_dir / "papers.jsonl").is_file()
    assert (output_dir / "chunks.jsonl").is_file()
    assert (output_dir / "embeddings.jsonl").is_file()
    assert (output_dir / "paper_embeddings.jsonl").is_file()

    paper = json.loads((output_dir / "papers.jsonl").read_text().splitlines()[0])
    paper_embedding = json.loads((output_dir / "paper_embeddings.jsonl").read_text().splitlines()[0])
    assert paper["title"] == "Robot Paper"
    assert paper["paper_keywords"] == ["grasping"]
    assert paper["lab"] == "airlab"
    assert paper_embedding["paper_id"] == paper["paper_id"]
    assert len(paper_embedding["embedding"]) == 384


def test_search_index_uses_keywords_and_requirement_text(tmp_path):
    labs_root = tmp_path / "labs"
    output_dir = tmp_path / "rag_index"
    _write_paper(
        labs_root,
        "airlab",
        "Dexterous Grasping",
        ["dexterous grasping"],
        "A policy for dexterous grasping from RGB-D and language.",
    )
    build_rag_index(labs_root, output_dir)

    keyword_results = search_index(output_dir, keyword="dexterous grasping", top_k=1)
    query_results = search_index(output_dir, query="I need RGB-D language manipulation papers", top_k=1)

    assert keyword_results[0]["title"] == "Dexterous Grasping"
    assert keyword_results[0]["score"] >= 1.0
    assert keyword_results[0]["abstract"] == "A robot policy paper about manipulation."
    assert keyword_results[0]["paper_keywords"] == ["dexterous grasping"]
    assert keyword_results[0]["supporting_chunks"]
    assert "chunk_id" in keyword_results[0]["supporting_chunks"][0]
    assert query_results[0]["title"] == "Dexterous Grasping"


def test_main_stops_after_building_index_even_when_query_is_present(tmp_path, capsys):
    labs_root = tmp_path / "labs"
    output_dir = tmp_path / "rag_index"
    _write_paper(labs_root, "airlab", "Dexterous Grasping", ["dexterous grasping"], "Uses RGB-D.")

    exit_code = main(["--labs-root", str(labs_root), "--output-dir", str(output_dir), "--query", "RGB-D"])

    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "[rag:index]" in captured
    assert '"title": "Dexterous Grasping"' not in captured
