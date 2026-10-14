import json
import hashlib
from threading import Barrier, Event, Lock
from unittest.mock import patch

import pytest

from labs import summarize_paper as summarizer


def make_lab(root, name, title="Shared Paper", year=2025):
    lab = root / name
    lab.mkdir()
    (lab / "link.txt").write_text("https://example.com/lab")
    paper = {"title": title, "year": year, "pdf_path": "paper.pdf", "pdf_url": f"https://example.com/{name}.pdf"}
    (lab / "paper.pdf").write_bytes(b"PDF fixture; extraction is mocked")
    (lab / "papers.json").write_text(json.dumps([paper]))
    return lab, paper


def test_reuses_summary_across_labs_and_runs(tmp_path):
    first, paper = make_lab(tmp_path, "first")
    second, duplicate = make_lab(tmp_path, "second", "  SHARED   Paper  ", year=2026)
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "An overview.", "abstract": "An abstract."})):
        summarizer.summarize_paper(first, paper, timeout=1, max_chars=100)
    with patch.object(summarizer, "summarize_paper_from_text", side_effect=AssertionError("Duplicate AI call")):
        output = summarizer.summarize_paper(second, duplicate, timeout=1, max_chars=100)
    markdown = output.read_text()
    assert "An overview." in markdown
    assert "https://example.com/second.pdf" in markdown
    assert "https://example.com/first.pdf" not in markdown
    assert json.loads(summarizer.paper_summary_json_path(second, duplicate).read_text())["abstract"] == "An abstract."
    assert len(list((tmp_path / ".summary_cache").glob("*.json"))) == 1


def test_force_refreshes_unique_title_once_across_labs(tmp_path):
    first, paper = make_lab(tmp_path, "first")
    second, duplicate = make_lab(tmp_path, "second")
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "Old overview."})):
        summarizer.summarize_paper(first, paper, timeout=1, max_chars=100)
    refreshed = set()
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "New overview."})):
        summarizer.summarize_lab(first, timeout=1, max_chars=100, force=True, refreshed_titles=refreshed)
    with patch.object(summarizer, "summarize_paper_from_text", side_effect=AssertionError("Duplicate forced AI call")):
        summarizer.summarize_lab(second, timeout=1, max_chars=100, force=True, refreshed_titles=refreshed)
    assert "New overview." in summarizer.paper_summary_path(first, paper).read_text()
    assert "New overview." in summarizer.paper_summary_path(second, duplicate).read_text()


def test_damaged_cache_is_regenerated(tmp_path):
    lab, paper = make_lab(tmp_path, "first")
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "Initial overview."})):
        summarizer.summarize_paper(lab, paper, timeout=1, max_chars=100)
    cached = next((tmp_path / ".summary_cache").glob("*.json"))
    cached.write_text("{broken JSON")
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "Recovered overview."})):
        output = summarizer.summarize_paper(lab, paper, timeout=1, max_chars=100)
    assert "Recovered overview." in output.read_text()
    assert json.loads(cached.read_text())["summary"]["paper_summary"] == "Recovered overview."


def test_different_titles_are_processed_separately(tmp_path):
    first, paper = make_lab(tmp_path, "first", "Paper A")
    second, other = make_lab(tmp_path, "second", "Paper B")
    for lab, metadata, overview in [(first, paper, "Overview A."), (second, other, "Overview B.")]:
        with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": overview})):
            output = summarizer.summarize_paper(lab, metadata, timeout=1, max_chars=100)
        assert overview in output.read_text()
    assert len(list((tmp_path / ".summary_cache").glob("*.json"))) == 2


def test_dry_run_does_not_create_cache(tmp_path):
    lab, paper = make_lab(tmp_path, "first")
    summarizer.summarize_paper(lab, paper, timeout=1, max_chars=100, dry_run=True)
    assert not (tmp_path / ".summary_cache").exists()
    assert not (tmp_path / "summarized_papers.json").exists()


@pytest.mark.parametrize("response", ["", "{}", "This is not JSON."])
def test_invalid_response_does_not_mark_paper_processed(tmp_path, response):
    lab, paper = make_lab(tmp_path, "first")
    with patch.object(summarizer, "summarize_paper_from_text", return_value=response):
        with pytest.raises(RuntimeError, match="no usable summary JSON"):
            summarizer.summarize_paper(lab, paper, timeout=1, max_chars=100)
    assert not (tmp_path / ".summary_cache").exists()
    assert not (lab / "summary").exists()


def test_missing_titles_do_not_share_cache(tmp_path):
    for name, overview in [("first", "Overview A."), ("second", "Overview B.")]:
        lab, paper = make_lab(tmp_path, name, title="")
        with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": overview})):
            output = summarizer.summarize_paper(lab, paper, timeout=1, max_chars=100)
        assert overview in output.read_text()
    assert not (tmp_path / ".summary_cache").exists()


def test_registry_updated_after_each_success_and_reused_on_restart(tmp_path):
    first, paper = make_lab(tmp_path, "first", "Paper A")
    second, other = make_lab(tmp_path, "second", "Paper B")
    registry_path = tmp_path / "summarized_papers.json"
    key_a = hashlib.sha256(b"paper a").hexdigest()
    key_b = hashlib.sha256(b"paper b").hexdigest()
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "Overview A."})):
        summarizer.summarize_paper(first, paper, timeout=1, max_chars=100)
    assert json.loads(registry_path.read_text()) == {key_a: "paper a"}
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "Overview B."})):
        summarizer.summarize_paper(second, other, timeout=1, max_chars=100)
    assert json.loads(registry_path.read_text()) == {key_a: "paper a", key_b: "paper b"}
    third, duplicate = make_lab(tmp_path, "third", "PAPER A")
    with patch.object(summarizer, "summarize_paper_from_text", side_effect=AssertionError("Already processed paper sent to proxy")):
        assert summarizer.main(["--labs-root", str(tmp_path), "--lab", "third"]) == 0
    assert "Overview A." in summarizer.paper_summary_path(third, duplicate).read_text()


def test_failed_paper_does_not_enter_registry(tmp_path):
    first, paper = make_lab(tmp_path, "first")
    with patch.object(summarizer, "summarize_paper_from_text", side_effect=RuntimeError("Request failed")):
        assert summarizer.summarize_lab(first, timeout=1, max_chars=100) == (1, 0)
    assert not (tmp_path / "summarized_papers.json").exists()


def test_damaged_registry_recovers_from_cache_without_ai(tmp_path):
    first, paper = make_lab(tmp_path, "first")
    with patch.object(summarizer, "summarize_paper_from_text", return_value=json.dumps({"paper_summary": "Saved overview."})):
        summarizer.summarize_paper(first, paper, timeout=1, max_chars=100)
    registry_path = tmp_path / "summarized_papers.json"
    registry_path.write_text("{broken")
    second, duplicate = make_lab(tmp_path, "second")
    with patch.object(summarizer, "summarize_paper_from_text", side_effect=AssertionError("Cached paper sent to proxy")):
        assert summarizer.main(["--labs-root", str(tmp_path), "--lab", "second"]) == 0
    assert "Saved overview." in summarizer.paper_summary_path(second, duplicate).read_text()
    assert list(json.loads(registry_path.read_text()).values()) == ["shared paper"]


def test_four_workers_overlap_across_labs_and_keep_all_registry_entries(tmp_path):
    labs = [make_lab(tmp_path, f"lab{i}", title=f"Paper {i}") for i in range(4)]
    barrier = Barrier(4, timeout=5)

    def summarize(paper, *args, **kwargs):
        barrier.wait()
        return json.dumps({"paper_summary": f"Overview of {paper['title']}."})

    with patch.object(summarizer, "summarize_paper_from_text", side_effect=summarize):
        assert summarizer.main(["--labs-root", str(tmp_path)]) == 0
    registry = json.loads((tmp_path / "summarized_papers.json").read_text())
    assert set(registry.values()) == {"paper 0", "paper 1", "paper 2", "paper 3"}
    for lab, paper in labs:
        assert f"Overview of {paper['title']}." in summarizer.paper_summary_path(lab, paper).read_text()


def test_parallel_force_deduplicates_titles(tmp_path):
    labs = [make_lab(tmp_path, f"lab{i}") for i in range(4)]
    calls = 0
    lock = Lock()

    def summarize(*args, **kwargs):
        nonlocal calls
        with lock:
            calls += 1
            if calls > 1:
                raise AssertionError("Duplicate title sent to proxy")
        Event().wait(0.05)  # Keep the request in flight while duplicate workers start.
        return json.dumps({"paper_summary": "One shared overview."})

    with patch.object(summarizer, "summarize_paper_from_text", side_effect=summarize):
        assert summarizer.main(["--labs-root", str(tmp_path), "--force"]) == 0
    for lab, paper in labs:
        assert "One shared overview." in summarizer.paper_summary_path(lab, paper).read_text()


def test_invalid_worker_count_is_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        summarizer.main(["--labs-root", str(tmp_path), "--workers", "0"])
    assert exc.value.code == 2


def test_single_worker_continues_after_failed_paper(tmp_path):
    first, failed = make_lab(tmp_path, "first", title="Failed paper")
    second, successful = make_lab(tmp_path, "second", title="Successful paper")

    def summarize(paper, *args, **kwargs):
        if paper["title"] == "Failed paper":
            raise RuntimeError("Proxy request failed")
        return json.dumps({"paper_summary": "Successful overview."})

    with patch.object(summarizer, "summarize_paper_from_text", side_effect=summarize):
        assert summarizer.main(["--labs-root", str(tmp_path), "--workers", "1"]) == 1
    assert not summarizer.paper_summary_path(first, failed).exists()
    assert "Successful overview." in summarizer.paper_summary_path(second, successful).read_text()
    assert list(json.loads((tmp_path / "summarized_papers.json").read_text()).values()) == ["successful paper"]


def test_canonical_paper_title_preserves_existing_summary_paths(tmp_path):
    lab, paper = make_lab(tmp_path, 'video', 'Video caption')
    old_md = summarizer.paper_summary_path(lab, paper)
    old_json = summarizer.paper_summary_json_path(lab, paper)
    paper.update(paper_title='GR00T N1: An Open Foundation Model for Generalist Humanoid Robots',
                 summary_path=str(old_md.relative_to(lab)), summary_json_path=str(old_json.relative_to(lab)))
    (lab/'papers.json').write_text(json.dumps([paper]))
    loaded = summarizer.load_papers(lab)[0]
    assert loaded['title'] == paper['paper_title']
    assert summarizer.normalized_paper_title(paper) == paper['paper_title'].casefold()
    assert summarizer.paper_summary_path(lab, loaded) == old_md
    assert summarizer.paper_summary_json_path(lab, loaded) == old_json
