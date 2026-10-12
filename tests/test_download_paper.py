import json
import os
import ssl
import subprocess
from http.client import IncompleteRead, InvalidURL
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote

import pytest

from labs.download_paper import (
    DEFAULT_HTTP_ATTEMPTS,
    DEFAULT_WORKERS,
    DEFAULT_TIMEOUT_SECONDS,
    PaperCandidate,
    build_bilibili_video_text,
    clean_title,
    collect_lab,
    choose_candidates,
    discover_lab_dirs,
    download_pdf,
    extract_papers_from_video_text_response,
    extract_papers_from_ai_response,
    extract_google_scholar_title_rows,
    fetch_text_with_chrome,
    filter_bilibili_lab_dirs,
    filter_new_papers,
    fetch_bilibili_video_metadata,
    fetch_publication_html,
    fetch_text_from_remote_chrome,
    fetch_google_scholar_text,
    fetch_text,
    format_lab_progress,
    format_year_counts,
    extract_rai_papers,
    is_bilibili_url,
    is_probable_publication_title,
    main,
    parse_publication_page,
    prepare_google_scholar_manual_login,
    run_labs,
    safe_filename,
    search_google_scholar_citation_pages,
    search_arxiv_for_bilibili_video,
    _run_yt_dlp_json,
    _yt_dlp_auth_args,
)
from urllib.error import URLError


def test_discovers_labs_with_link_files(tmp_path):
    labs_root = tmp_path / "labs"
    wanted = labs_root / "airlab"
    ignored = labs_root / "notes"
    wanted.mkdir(parents=True)
    ignored.mkdir()
    (wanted / "link.txt").write_text("https://example.com/publications\n")

    assert discover_lab_dirs(labs_root) == [wanted]


def test_discovers_labs_sorted_by_folder_name_string(tmp_path):
    labs_root = tmp_path / "labs"
    b_lab = labs_root / "B_lab"
    a_lab = labs_root / "a_lab"
    b_lab.mkdir(parents=True)
    a_lab.mkdir()
    (b_lab / "link.txt").write_text("https://example.com/b\n")
    (a_lab / "link.txt").write_text("https://example.com/a\n")

    assert discover_lab_dirs(labs_root) == [a_lab, b_lab]


def test_default_timeout_is_thirty_minutes():
    assert DEFAULT_TIMEOUT_SECONDS == 30 * 60


def test_default_workers_is_two():
    assert DEFAULT_WORKERS == 2


def test_default_http_attempts_is_three():
    assert DEFAULT_HTTP_ATTEMPTS == 3


def test_run_labs_processes_all_labs_with_workers(tmp_path, monkeypatch):
    first_lab = tmp_path / "airlab(basti)"
    second_lab = tmp_path / "ppl(shubham)"
    first_lab.mkdir()
    second_lab.mkdir()
    (first_lab / "link.txt").write_text("https://example.com/airlab\n")
    (second_lab / "link.txt").write_text("https://example.com/ppl\n")
    processed_labs = []

    def fake_collect_lab(lab_dir, min_year, timeout, dry_run, extractor):
        processed_labs.append(lab_dir.name)
        return (1, 0)

    monkeypatch.setattr("labs.download_paper.collect_lab", fake_collect_lab)

    failures = run_labs(
        [first_lab, second_lab],
        min_year=2023,
        timeout=1,
        dry_run=True,
        extractor="static",
        workers=2,
    )

    assert failures == 0
    assert set(processed_labs) == {"airlab(basti)", "ppl(shubham)"}


def test_main_can_process_only_bilibili_labs(tmp_path, monkeypatch):
    labs_root = tmp_path / "labs"
    bilibili_lab = labs_root / "深蓝学院"
    web_lab = labs_root / "airlab(basti)"
    bilibili_lab.mkdir(parents=True)
    web_lab.mkdir()
    (bilibili_lab / "link.txt").write_text("https://space.bilibili.com/320203065/upload/video\n")
    (web_lab / "link.txt").write_text("https://example.com/publications\n")
    captured = {}

    def fake_run_labs(lab_dirs, min_year, timeout, dry_run, extractor, workers):
        captured["lab_dirs"] = lab_dirs
        return 0

    monkeypatch.setattr("labs.download_paper.run_labs", fake_run_labs)

    exit_code = main(["--labs-root", str(labs_root), "--bilibili-only", "--dry-run"])

    assert exit_code == 0
    assert captured["lab_dirs"] == [bilibili_lab]


def test_main_can_process_single_lab_folder(tmp_path, monkeypatch):
    labs_root = tmp_path / "labs"
    goldberg_lab = labs_root / "goldberg"
    airlab = labs_root / "airlab(basti)"
    goldberg_lab.mkdir(parents=True)
    airlab.mkdir()
    (goldberg_lab / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    (airlab / "link.txt").write_text("https://example.com/publications\n")
    captured = {}

    def fake_run_labs(lab_dirs, min_year, timeout, dry_run, extractor, workers):
        captured["lab_dirs"] = lab_dirs
        return 0

    monkeypatch.setattr("labs.download_paper.run_labs", fake_run_labs)

    exit_code = main(["--labs-root", str(labs_root), "--lab", "goldberg", "--dry-run"])

    assert exit_code == 0
    assert captured["lab_dirs"] == [goldberg_lab]


def test_main_sets_bilibili_cookie_browser_arg(tmp_path, monkeypatch):
    labs_root = tmp_path / "labs"
    bilibili_lab = labs_root / "深蓝学院"
    bilibili_lab.mkdir(parents=True)
    (bilibili_lab / "link.txt").write_text("https://space.bilibili.com/320203065/upload/video\n")

    monkeypatch.delenv("BILIBILI_COOKIES", raising=False)
    monkeypatch.delenv("BILIBILI_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.setattr("labs.download_paper.run_labs", lambda *args, **kwargs: 0)

    exit_code = main(
        [
            "--labs-root",
            str(labs_root),
            "--bilibili-only",
            "--bilibili-cookies-from-browser",
            "chrome",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert _yt_dlp_auth_args() == ["--cookies-from-browser", "chrome"]


def test_main_sets_google_scholar_fetcher_env(tmp_path, monkeypatch):
    lab_dir = tmp_path / "labs" / "scholar"
    lab_dir.mkdir(parents=True)
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    captured = {}

    def fake_run_labs(lab_dirs, min_year, timeout, dry_run, extractor, workers):
        captured["fetcher"] = os.environ.get("GOOGLE_SCHOLAR_FETCHER")
        return []

    monkeypatch.delenv("GOOGLE_SCHOLAR_FETCHER", raising=False)
    monkeypatch.setattr("labs.download_paper.run_labs", fake_run_labs)

    assert main(["--labs-root", str(tmp_path / "labs"), "--google-scholar-fetcher", "chrome"]) == 0
    assert captured["fetcher"] == "chrome"


def test_main_does_not_default_google_scholar_links_to_chrome_fetcher(tmp_path, monkeypatch):
    lab_dir = tmp_path / "labs" / "scholar"
    lab_dir.mkdir(parents=True)
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    captured = {}

    def fake_run_labs(lab_dirs, min_year, timeout, dry_run, extractor, workers):
        captured["fetcher"] = os.environ.get("GOOGLE_SCHOLAR_FETCHER")
        return []

    monkeypatch.delenv("GOOGLE_SCHOLAR_FETCHER", raising=False)
    monkeypatch.setattr("labs.download_paper.run_labs", fake_run_labs)

    assert main(["--labs-root", str(tmp_path / "labs")]) == 0
    assert captured["fetcher"] is None


def test_fetch_text_with_chrome_uses_headless_dump_dom(monkeypatch):
    captured = {}

    def fake_run(command, capture_output, text, timeout, check):
        captured["command"] = command
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(command, 0, stdout="<html>ok</html>", stderr="")

    monkeypatch.setattr("labs.download_paper.subprocess.run", fake_run)

    assert fetch_text_with_chrome("https://scholar.google.com/citations?user=abc", timeout=12) == "<html>ok</html>"
    assert captured["command"][0] == "google-chrome"
    assert "--headless=new" in captured["command"]
    assert "--dump-dom" in captured["command"]
    assert captured["command"][-1] == "https://scholar.google.com/citations?user=abc"
    assert captured["timeout"] == 12


def test_fetch_text_with_chrome_uses_profile_directory(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, capture_output, text, timeout, check):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="<html>ok</html>", stderr="")

    monkeypatch.setenv("GOOGLE_CHROME_USER_DATA_DIR", str(tmp_path / "chrome-profile"))
    monkeypatch.setenv("GOOGLE_CHROME_PROFILE_DIRECTORY", "Default")
    monkeypatch.setattr("labs.download_paper.subprocess.run", fake_run)

    assert fetch_text_with_chrome("https://scholar.google.com/citations?user=abc", timeout=12) == "<html>ok</html>"
    assert f"--user-data-dir={tmp_path / 'chrome-profile'}" in captured["command"]
    assert "--profile-directory=Default" in captured["command"]


def test_main_manual_google_scholar_login_sets_profile_and_waits(tmp_path, monkeypatch):
    lab_dir = tmp_path / "labs" / "scholar"
    profile_dir = tmp_path / "manual-chrome-profile"
    lab_dir.mkdir(parents=True)
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    captured = {}

    def fake_prepare(url, timeout):
        captured["manual_url"] = url
        captured["profile"] = os.environ.get("GOOGLE_CHROME_USER_DATA_DIR")

    def fake_run_labs(lab_dirs, min_year, timeout, dry_run, extractor, workers):
        captured["fetcher"] = os.environ.get("GOOGLE_SCHOLAR_FETCHER")
        captured["profile_after_prepare"] = os.environ.get("GOOGLE_CHROME_USER_DATA_DIR")
        captured["remote_port_after_prepare"] = os.environ.get("GOOGLE_CHROME_REMOTE_DEBUGGING_PORT")
        captured["use_remote_after_prepare"] = os.environ.get("GOOGLE_SCHOLAR_USE_REMOTE_CHROME")
        return []

    monkeypatch.delenv("GOOGLE_SCHOLAR_FETCHER", raising=False)
    monkeypatch.delenv("GOOGLE_CHROME_USER_DATA_DIR", raising=False)
    monkeypatch.setattr("labs.download_paper.prepare_google_scholar_manual_login", fake_prepare)
    monkeypatch.setattr("labs.download_paper.run_labs", fake_run_labs)

    assert main(
        [
            "--labs-root",
            str(tmp_path / "labs"),
            "--google-scholar-manual-login",
            "--google-scholar-user-data-dir",
            str(profile_dir),
        ]
    ) == 0
    assert captured == {
        "manual_url": "https://scholar.google.com/citations?user=abc&pagesize=100&cstart=0",
        "profile": str(profile_dir),
        "fetcher": "chrome",
        "profile_after_prepare": str(profile_dir),
        "remote_port_after_prepare": "9222",
        "use_remote_after_prepare": "1",
    }


def test_prepare_google_scholar_manual_login_keeps_browser_open(monkeypatch):
    captured = {}

    class FakeProcess:
        def terminate(self):
            captured["terminated"] = True

        def wait(self, timeout):
            captured["waited"] = timeout

    def fake_popen(command):
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr("labs.download_paper.subprocess.Popen", fake_popen)
    monkeypatch.setattr("builtins.input", lambda prompt: captured.setdefault("prompt", prompt))

    prepare_google_scholar_manual_login("https://scholar.google.com/citations?user=abc", timeout=12)

    assert "--remote-debugging-port=9222" in captured["command"]
    assert captured["command"][-1] == "https://scholar.google.com/citations?user=abc"
    assert "publication rows" in captured["prompt"]
    assert "terminated" not in captured
    assert "waited" not in captured


def test_fetch_google_scholar_text_uses_remote_chrome_when_manual_login(monkeypatch):
    captured = {}

    def fake_remote_fetch(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return "<html>remote</html>"

    monkeypatch.setenv("GOOGLE_SCHOLAR_FETCHER", "chrome")
    monkeypatch.setenv("GOOGLE_SCHOLAR_USE_REMOTE_CHROME", "1")
    monkeypatch.setattr("labs.download_paper.fetch_text_from_remote_chrome", fake_remote_fetch)

    assert fetch_google_scholar_text("https://scholar.google.com/citations?user=abc", timeout=12) == "<html>remote</html>"
    assert captured == {"url": "https://scholar.google.com/citations?user=abc", "timeout": 12}


def test_fetch_text_from_remote_chrome_uses_cdp_url(monkeypatch):
    calls = []

    def fake_fetch_text(url, timeout):
        calls.append((url, timeout))
        return json.dumps(
            [
                {
                    "url": "https://scholar.google.com/citations?user=abc",
                    "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/page/1",
                }
            ]
        )

    monkeypatch.setenv("GOOGLE_CHROME_CDP_URL", "http://127.0.0.1:9223")
    monkeypatch.setattr("labs.download_paper.fetch_text", fake_fetch_text)
    monkeypatch.setattr("labs.download_paper._chrome_devtools_evaluate", lambda websocket_url, expression, timeout: "<html>cdp</html>")

    assert fetch_text_from_remote_chrome("https://scholar.google.com/citations?user=abc", timeout=12) == "<html>cdp</html>"
    assert calls == [("http://127.0.0.1:9223/json/list", 12)]


@pytest.mark.parametrize("open_url", ["about:blank", "https://scholar.google.com/citations?user=other", "https://scholar.google.com/citations?user=abc&cstart=0"])
def test_remote_chrome_opens_requested_profile_and_page(monkeypatch, open_url):
    requested_url = "https://scholar.google.com/citations?user=abc&cstart=100"
    calls = []
    monkeypatch.setenv("GOOGLE_CHROME_CDP_URL", "http://127.0.0.1:9223")

    def fake_fetch(url, timeout):
        calls.append(url)
        if url.endswith("/json/list"):
            return json.dumps([{"url": open_url, "webSocketDebuggerUrl": "ws://wrong-tab"}])
        assert url == "http://127.0.0.1:9223/json/close/new-tab"
        return "Target is closing"

    def fake_read(request, timeout, attempts):
        assert request.get_method() == "PUT"
        assert request.full_url == "http://127.0.0.1:9223/json/new?" + quote(requested_url, safe="")
        assert attempts == 1
        return json.dumps({"id": "new-tab", "webSocketDebuggerUrl": "ws://new-tab"}).encode(), None

    results = iter([None, "<html>requested profile, page 2</html>"])

    def fake_evaluate(websocket_url, expression, timeout):
        assert websocket_url == "ws://new-tab"
        assert "document.readyState" in expression
        return next(results)

    monkeypatch.setattr("labs.download_paper.fetch_text", fake_fetch)
    monkeypatch.setattr("labs.download_paper.read_url_with_retries", fake_read)
    monkeypatch.setattr("labs.download_paper._chrome_devtools_evaluate", fake_evaluate)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda _: None)

    assert fetch_text_from_remote_chrome(requested_url, timeout=12) == "<html>requested profile, page 2</html>"
    assert calls == ["http://127.0.0.1:9223/json/list", "http://127.0.0.1:9223/json/close/new-tab"]


def test_remote_chrome_closes_created_tab_on_evaluation_failure(monkeypatch):
    calls = []
    monkeypatch.setenv("GOOGLE_CHROME_CDP_URL", "http://127.0.0.1:9223")
    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: calls.append(url) or "[]")
    monkeypatch.setattr("labs.download_paper.read_url_with_retries", lambda request, timeout, attempts: (b'{"id":"new-tab","webSocketDebuggerUrl":"ws://new-tab"}', None))

    def fail_evaluation(*args, **kwargs):
        raise RuntimeError("evaluation failed")

    monkeypatch.setattr("labs.download_paper._chrome_devtools_evaluate", fail_evaluation)
    with pytest.raises(RuntimeError, match="evaluation failed"):
        fetch_text_from_remote_chrome("https://scholar.google.com/citations?user=abc", timeout=12)
    assert calls[-1] == "http://127.0.0.1:9223/json/close/new-tab"


@pytest.mark.parametrize("solved", [True, False])
def test_remote_chrome_waits_for_manual_scholar_challenge(monkeypatch, capsys, solved):
    calls = []
    clock = [0.0]
    challenge = '<html><form id="captcha-form">Our systems have detected unusual traffic</form></html>'
    results = iter([challenge, challenge, "<html>Scholar publications</html>"])
    monkeypatch.setenv("GOOGLE_CHROME_CDP_URL", "http://127.0.0.1:9223")
    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: calls.append(url) or "[]")
    monkeypatch.setattr("labs.download_paper.read_url_with_retries", lambda request, timeout, attempts: (b'{"id":"new-tab","webSocketDebuggerUrl":"ws://new-tab"}', None))
    monkeypatch.setattr("labs.download_paper._chrome_devtools_evaluate", lambda *args, **kwargs: next(results))
    monkeypatch.setattr("labs.download_paper.time.monotonic", lambda: clock[0])

    def advance_clock(seconds):
        clock[0] += seconds if solved else 1801

    monkeypatch.setattr("labs.download_paper.time.sleep", advance_clock)
    url = "https://scholar.google.com/citations?user=abc"
    if solved:
        assert fetch_text_from_remote_chrome(url, timeout=1) == "<html>Scholar publications</html>"
        assert calls[-1].endswith("/json/close/new-tab")
        assert clock[0] >= 2
    else:
        with pytest.raises(TimeoutError, match="challenge.*tab left open"):
            fetch_text_from_remote_chrome(url, timeout=1)
        assert calls == ["http://127.0.0.1:9223/json/list"]
    assert capsys.readouterr().err.count("Solve the check in Chrome") == 1


def test_main_google_scholar_cdp_url_uses_remote_without_manual_login(tmp_path, monkeypatch):
    lab_dir = tmp_path / "labs" / "scholar"
    lab_dir.mkdir(parents=True)
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    captured = {}

    def fake_prepare(url, timeout):
        raise AssertionError("manual Chrome should not be opened when --google-scholar-cdp-url is used")

    def fake_run_labs(lab_dirs, min_year, timeout, dry_run, extractor, workers):
        captured["fetcher"] = os.environ.get("GOOGLE_SCHOLAR_FETCHER")
        captured["use_remote"] = os.environ.get("GOOGLE_SCHOLAR_USE_REMOTE_CHROME")
        captured["cdp_url"] = os.environ.get("GOOGLE_CHROME_CDP_URL")
        return []

    monkeypatch.delenv("GOOGLE_SCHOLAR_FETCHER", raising=False)
    monkeypatch.delenv("GOOGLE_SCHOLAR_USE_REMOTE_CHROME", raising=False)
    monkeypatch.delenv("GOOGLE_CHROME_CDP_URL", raising=False)
    monkeypatch.setattr("labs.download_paper.prepare_google_scholar_manual_login", fake_prepare)
    monkeypatch.setattr("labs.download_paper.run_labs", fake_run_labs)

    assert main(["--labs-root", str(tmp_path / "labs"), "--google-scholar-cdp-url", "http://127.0.0.1:9222"]) == 0
    assert captured == {
        "fetcher": "chrome",
        "use_remote": "1",
        "cdp_url": "http://127.0.0.1:9222",
    }


def test_google_scholar_citation_page_search_can_be_limited(monkeypatch):
    rows = "\n".join(
        f"""
        <tr class="gsc_a_tr">
          <td class="gsc_a_t">
            <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper{index}" class="gsc_a_at">
              Robot Learning Paper {index}
            </a>
            <div class="gs_gray">Conference on Robot Learning, 2026</div>
          </td>
          <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
        </tr>
        """
        for index in range(3)
    )
    calls = []

    def fake_fetch(url, timeout, attempts=1):
        calls.append(url)
        return ""

    monkeypatch.setenv("GOOGLE_SCHOLAR_CITATION_LIMIT", "1")
    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)

    papers = search_google_scholar_citation_pages(
        f"<table><tbody>{rows}</tbody></table>",
        "https://scholar.google.com/citations?user=abc",
        [],
        min_year=2023,
        timeout=30,
    )

    assert papers == []
    assert len(calls) == 1


def test_google_scholar_citation_page_search_streams_each_resolved_candidate(monkeypatch):
    rows = "\n".join(
        f"""
        <tr class="gsc_a_tr">
          <td class="gsc_a_t">
            <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper{index}" class="gsc_a_at">
              Robot Learning Paper {index}
            </a>
            <div class="gs_gray">Conference on Robot Learning, 2026</div>
          </td>
          <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
        </tr>
        """
        for index in range(2)
    )
    events = []

    def fake_fetch(url, timeout, attempts=1):
        events.append(f"fetch:{url.rsplit(':', 1)[-1]}")
        arxiv_id = "2601.00001" if url.endswith("paper0") else "2601.00002"
        return f'<a href="https://arxiv.org/pdf/{arxiv_id}.pdf">PDF</a>'

    def on_candidate(paper):
        events.append(f"candidate:{paper.title}")

    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)

    papers = search_google_scholar_citation_pages(
        f"<table><tbody>{rows}</tbody></table>",
        "https://scholar.google.com/citations?user=abc",
        [],
        min_year=2023,
        timeout=30,
        on_candidate=on_candidate,
    )

    assert [paper.title for paper in papers] == ["Robot Learning Paper 0", "Robot Learning Paper 1"]
    assert events == [
        "fetch:paper0",
        "candidate:Robot Learning Paper 0",
        "fetch:paper1",
        "candidate:Robot Learning Paper 1",
    ]


def test_clean_title_preserves_acronym_prefix_before_colon():
    assert clean_title("LDA-1B: Scaling Latent Dynamics Action Model via Universal Embodied Data Ingestion") == (
        "LDA-1B: Scaling Latent Dynamics Action Model via Universal Embodied Data Ingestion"
    )


def test_main_defaults_bilibili_only_to_chrome_cookies(tmp_path, monkeypatch):
    labs_root = tmp_path / "labs"
    bilibili_lab = labs_root / "深蓝学院"
    bilibili_lab.mkdir(parents=True)
    (bilibili_lab / "link.txt").write_text("https://space.bilibili.com/320203065/upload/video\n")

    monkeypatch.delenv("BILIBILI_COOKIES", raising=False)
    monkeypatch.delenv("BILIBILI_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.setattr("labs.download_paper.run_labs", lambda *args, **kwargs: 0)

    exit_code = main(["--labs-root", str(labs_root), "--bilibili-only", "--dry-run"])

    assert exit_code == 0
    assert _yt_dlp_auth_args() == ["--cookies-from-browser", "chrome"]


def test_filter_bilibili_lab_dirs_keeps_only_bilibili_links(tmp_path):
    bilibili_lab = tmp_path / "具身智能之心"
    web_lab = tmp_path / "airlab(basti)"
    bilibili_lab.mkdir()
    web_lab.mkdir()
    (bilibili_lab / "link.txt").write_text("https://space.bilibili.com/1961034195/upload/video\n")
    (web_lab / "link.txt").write_text("https://example.com/publications\n")

    assert filter_bilibili_lab_dirs([web_lab, bilibili_lab]) == [bilibili_lab]


def test_format_lab_progress_shows_lab_founder_and_waiting_count():
    lab_dir = Path("labs/iamlab(oliver)")

    assert format_lab_progress(lab_dir, current=3, total=18, phase="start") == (
        "[lab 3/18] start: iamlab(oliver) | waiting: 15"
    )
    assert format_lab_progress(lab_dir, current=3, total=18, phase="done") == (
        "[lab 3/18] done: iamlab(oliver) | waiting: 15"
    )


def test_format_year_counts_lists_since_min_year_in_order():
    papers = [
        PaperCandidate("A", 2025, "https://example.com/a", "https://example.com/a.pdf"),
        PaperCandidate("B", 2023, "https://example.com/b", "https://example.com/b.pdf"),
        PaperCandidate("C", 2025, "https://example.com/c", "https://example.com/c.pdf"),
    ]

    assert format_year_counts(papers, min_year=2023) == "2023=1, 2024=0, 2025=2"


def test_parse_publication_page_finds_recent_pdf_links():
    html = """
    <html><body>
      <article>
        <h2>Robot Learning in the Wild</h2>
        <span>CoRL 2024</span>
        <a href="/papers/wild.pdf">PDF</a>
      </article>
      <article>
        <h2>Old Robot Paper</h2>
        <span>RSS 2022</span>
        <a href="/papers/old.pdf">PDF</a>
      </article>
    </body></html>
    """

    papers = parse_publication_page(html, "https://example.com/publications/", min_year=2023)

    assert papers == [
        PaperCandidate(
            title="Robot Learning in the Wild",
            year=2024,
            page_url="https://example.com/publications/",
            pdf_url="https://example.com/papers/wild.pdf",
        )
    ]


def test_parse_publication_page_prefers_article_title_markup():
    html = """
    <div class="media-body">
      <div class="section-subheading article-title mb-0 mt-0">
        <a href="https://arxiv.org/abs/2409.12192">
          DynaMo: In-Domain Dynamics Pretraining for Visuo-Motor Control
        </a>
      </div>
      <div class="stream-meta article-metadata">
        <span>Zichen Jeff Cui</span>, <span>Hengkai Pan</span>
        <div class="article-style">In NeurIPS 2024</div>
      </div>
      <a href="https://arxiv.org/abs/2409.12192">PDF</a>
    </div>
    """

    papers = parse_publication_page(html, "https://www.lerrelpinto.com/", min_year=2023)

    assert papers[0].title == "DynaMo: In-Domain Dynamics Pretraining for Visuo-Motor Control"
    assert papers[0].pdf_url == "https://arxiv.org/pdf/2409.12192.pdf"


def test_parse_publication_page_extracts_google_scholar_arxiv_rows():
    html = """
    <table><tbody id="gsc_a_b">
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a href="/citations?view_op=view_citation&amp;citation_for_view=abc" class="gsc_a_at">
            EyeRobot 2.0: Active Gaze for Precise Manipulation without Wrist Cameras
          </a>
          <div class="gs_gray">K Hari, J Kerr, K Goldberg</div>
          <div class="gs_gray">arXiv preprint arXiv:2610.03710<span class="gs_oph">, 2026</span></div>
        </td>
        <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
      </tr>
    </tbody></table>
    """

    papers = parse_publication_page(html, "https://scholar.google.com/citations?user=abc", min_year=2023)

    assert papers == [
        PaperCandidate(
            title="EyeRobot 2.0: Active Gaze for Precise Manipulation without Wrist Cameras",
            year=2026,
            page_url="https://scholar.google.com/citations?user=abc",
            pdf_url="https://arxiv.org/pdf/2610.03710.pdf",
        )
    ]


def test_parse_publication_page_extracts_airlab_bibtex_entries():
    html = """
    <h1 id="2025">2025</h1>
    <ol class="bibliography"><li><div class="text-justify">
      <span id="zhao2025resilient">
        <div class="csl-title"><b>Resilient Odometry via Hierarchical Adaptation</b>.</div>
        <div class="csl-event">In <i>Science Robotics</i>, 2025.</div>
      </span>
      <a href="https://arxiv.org/abs/2501.12345" aria-label="pdf link for paper">
        <input type="button" class="button4" value="link" />
      </a>
    </div>
    <div id="azhao2025resilient" style="display:none"><pre>@article{zhao2025resilient,
      title = {Resilient Odometry via Hierarchical Adaptation},
      author = {Zhao, Shibo and Scherer, Sebastian},
      year = {2025},
      journal = {Science Robotics},
      url = {https://arxiv.org/abs/2501.12345}
    }</pre></div></li></ol>
    """

    papers = parse_publication_page(html, "https://theairlab.org/publications/", min_year=2023)

    assert papers == [
        PaperCandidate(
            title="Resilient Odometry via Hierarchical Adaptation",
            year=2025,
            page_url="https://theairlab.org/publications/",
            pdf_url="https://arxiv.org/pdf/2501.12345.pdf",
        )
    ]


def test_extract_rai_papers_searches_arxiv_from_resource_cards(monkeypatch):
    html = """
    <article class="wpgb-card">
      <time datetime="2026-04-06T14:25:20-04:00">Apr 6, 2026</time>
      <h3 class="wpgb-block-1">
        <a href="https://rai-inst.com/resources/papers/planning-guided-diffusion-policy-learning-for-contact-rich-bimanual-object-reorientation/">
          Planning-Guided Diffusion Policy Learning for Contact-Rich Bimanual Object Reorientation
        </a>
      </h3>
    </article>
    """
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Planning-Guided Diffusion Policy Learning for Contact-Rich Bimanual Object Reorientation</title>
        <id>https://arxiv.org/abs/2603.12345</id>
        <published>2026-03-30T00:00:00Z</published>
      </entry>
    </feed>
    """
    requested_urls = []

    def fake_fetch_text(url, timeout):
        requested_urls.append(url)
        return atom

    monkeypatch.setattr("labs.download_paper.fetch_text", fake_fetch_text)

    papers = extract_rai_papers(html, "https://rai-inst.com/resources/?_type=papers", min_year=2023, timeout=1)

    assert papers == [
        PaperCandidate(
            title="Planning-Guided Diffusion Policy Learning for Contact-Rich Bimanual Object Reorientation",
            year=2026,
            page_url="https://rai-inst.com/resources/papers/planning-guided-diffusion-policy-learning-for-contact-rich-bimanual-object-reorientation/",
            pdf_url="https://arxiv.org/pdf/2603.12345.pdf",
        )
    ]
    assert requested_urls


def test_extract_rai_papers_rejects_low_similarity_arxiv_results(monkeypatch):
    html = """
    <article class="wpgb-card">
      <time datetime="2026-09-29T17:12:15-04:00">Sep 29, 2026</time>
      <h3><a href="/resources/papers/test-time-spatial-reasoning-for-robot-manipulation-using-generative-real-to-sim/">
        Test-Time Spatial Reasoning for Robot Manipulation Using Generative Real-to-Sim
      </a></h3>
    </article>
    """
    atom = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Unrelated Robot Paper</title>
        <id>https://arxiv.org/abs/2601.00001</id>
        <published>2026-01-01T00:00:00Z</published>
      </entry>
    </feed>
    """

    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: atom)

    assert extract_rai_papers(html, "https://rai-inst.com/resources/?_type=papers", min_year=2023, timeout=1) == []


def test_extract_rai_papers_fetches_load_more_cards(monkeypatch):
    first_page = """
    <article class="wpgb-card">
      <time datetime="2026-09-29T17:12:15-04:00">Sep 29, 2026</time>
      <h3><a href="/resources/papers/test-time-spatial-reasoning-for-robot-manipulation-using-generative-real-to-sim/">
        Test-Time Spatial Reasoning for Robot Manipulation Using Generative Real-to-Sim
      </a></h3>
    </article>
    """
    second_page = """
    <article class="wpgb-card">
      <time datetime="2026-03-30T15:48:10-04:00">Mar 30, 2026</time>
      <h3><a href="/resources/papers/judo-a-user-friendly-open-source-package-forsampling-based-model-predictive-control/">
        Judo: A User-Friendly Open-Source Package forSampling-Based Model Predictive Control
      </a></h3>
    </article>
    """
    offsets = []

    def fake_fetch_rai_wpgb_posts(base_url, offset, timeout):
        offsets.append(offset)
        return second_page if offset == 12 else ""

    def fake_search(title, page_url, min_year, timeout):
        return PaperCandidate(title, 2026, page_url, f"https://arxiv.org/pdf/{safe_filename(title)}.pdf")

    monkeypatch.setattr("labs.download_paper.fetch_rai_wpgb_posts", fake_fetch_rai_wpgb_posts, raising=False)
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", fake_search)

    papers = extract_rai_papers(first_page, "https://rai-inst.com/resources/?_type=papers", min_year=2023, timeout=1)

    assert [paper.title for paper in papers] == [
        "Test-Time Spatial Reasoning for Robot Manipulation Using Generative Real-to-Sim",
        "Judo: A User-Friendly Open-Source Package forSampling-Based Model Predictive Control",
    ]
    assert offsets == [12, 24]


def test_parse_publication_page_normalizes_arxiv_pdf_urls_without_suffix():
    html = """
    <pre>@inproceedings{radseg2026,
      title = {RADSeg: Unleashing Parameter and Compute Efficient Segmentation},
      year = {2026},
      url = {https://arxiv.org/pdf/2511.18174}
    }</pre>
    """

    papers = parse_publication_page(html, "https://theairlab.org/publications/", min_year=2023)

    assert papers[0].pdf_url == "https://arxiv.org/pdf/2511.18174.pdf"


def test_extract_papers_from_ai_response_skips_malformed_arxiv_pdf_urls():
    response = """
    [
      {
        "title": "Flow3R",
        "year": 2026,
        "url": "https://example.com/project",
        "pdf_url": "https://arxiv.org/pdf/2604.055 flow3r.pdf"
      }
    ]
    """

    papers = extract_papers_from_ai_response(response, "https://example.com/publications/", min_year=2023)

    assert papers == []


def test_extract_papers_from_ai_response_skips_malformed_arxiv_pdf_urls_with_short_id_and_title():
    response = """
    [
      {
        "title": "SOP",
        "year": 2026,
        "url": "https://example.com/project",
        "pdf_url": "https://arxiv.org/pdf/2603.030 SOP.pdf"
      }
    ]
    """

    papers = extract_papers_from_ai_response(response, "https://example.com/publications/", min_year=2023)

    assert papers == []


def test_extract_papers_from_ai_response_normalizes_links_and_filters_year():
    response = """
    Here are the papers:
    [
      {
        "title": "Learning Robot Skills",
        "year": 2024,
        "url": "https://example.com/project",
        "pdf_url": "https://arxiv.org/abs/2401.01234"
      },
      {
        "title": "Old Robot Skills",
        "year": 2022,
        "url": "https://example.com/old",
        "pdf_url": "https://example.com/old.pdf"
      }
    ]
    """

    papers = extract_papers_from_ai_response(response, "https://example.com/publications/", min_year=2023)

    assert papers == [
        PaperCandidate(
            title="Learning Robot Skills",
            year=2024,
            page_url="https://example.com/project",
            pdf_url="https://arxiv.org/pdf/2401.01234.pdf",
        )
    ]


def test_extract_papers_from_ai_response_ignores_malformed_json():
    response = """
    Here is malformed JSON:
    [
      {"title": "Broken Paper", "year": 2024, "pdf_url": "https://arxiv.org/abs/2401.01234"
      {"title": "Missing comma", "year": 2024}
    ]
    """

    papers = extract_papers_from_ai_response(response, "https://example.com/publications/", min_year=2023)

    assert papers == []


def test_hybrid_extractor_continues_when_ai_json_is_malformed(monkeypatch):
    static_paper = PaperCandidate(
        "Static Paper",
        2024,
        "https://example.com/static",
        "https://example.com/static.pdf",
    )

    monkeypatch.setattr(
        "labs.download_paper.extract_papers_with_ai",
        lambda html, base_url, min_year, timeout: extract_papers_from_ai_response("[{broken json]", base_url, min_year),
    )
    monkeypatch.setattr("labs.download_paper.parse_publication_page", lambda html, base_url, min_year: [static_paper])

    papers = choose_candidates("<html></html>", "https://example.com", min_year=2023, timeout=1, extractor="hybrid")

    assert papers == [static_paper]


def test_hybrid_extractor_merges_ai_and_static_candidates(monkeypatch):
    ai_paper = PaperCandidate("AI Paper", 2025, "https://example.com/ai", "https://example.com/ai.pdf")
    static_paper = PaperCandidate(
        "Static Paper",
        2023,
        "https://example.com/static",
        "https://example.com/static.pdf",
    )
    duplicate_static = PaperCandidate("AI Paper", 2025, "https://example.com/ai2", "https://example.com/ai.pdf")

    monkeypatch.setattr("labs.download_paper.extract_papers_with_ai", lambda html, base_url, min_year, timeout: [ai_paper])
    monkeypatch.setattr(
        "labs.download_paper.parse_publication_page",
        lambda html, base_url, min_year: [duplicate_static, static_paper],
    )

    papers = choose_candidates("<html></html>", "https://example.com", min_year=2023, timeout=1, extractor="hybrid")

    assert papers == [ai_paper, static_paper]


def test_detects_bilibili_channel_urls():
    assert is_bilibili_url("https://space.bilibili.com/320203065/upload/video")
    assert is_bilibili_url("https://www.bilibili.com/video/BV123")
    assert not is_bilibili_url("https://example.com/publications")


def test_build_bilibili_video_text_includes_recent_metadata():
    metadata = [
        {
            "title": "Paper sharing: Learning Robot Skills",
            "webpage_url": "https://www.bilibili.com/video/BV1",
            "description": "arXiv: https://arxiv.org/abs/2401.01234",
            "upload_date": "20240131",
        },
        {
            "title": "Second video",
            "url": "https://www.bilibili.com/video/BV2",
            "description": "",
        },
    ]

    text = build_bilibili_video_text(metadata)

    assert "Video 1" in text
    assert "Paper sharing: Learning Robot Skills" in text
    assert "https://arxiv.org/abs/2401.01234" in text
    assert "Video 2" in text
    assert "https://www.bilibili.com/video/BV2" in text


def test_extract_papers_from_video_text_response_normalizes_arxiv_links():
    response = """
    [
      {
        "title": "Learning Robot Skills from Video",
        "year": 2024,
        "video_url": "https://www.bilibili.com/video/BV1",
        "arxiv_url": "https://arxiv.org/abs/2401.01234"
      }
    ]
    """

    papers = extract_papers_from_video_text_response(
        response,
        "https://space.bilibili.com/320203065/upload/video",
        min_year=2023,
    )

    assert papers == [
        PaperCandidate(
            title="Learning Robot Skills from Video",
            year=2024,
            page_url="https://www.bilibili.com/video/BV1",
            pdf_url="https://arxiv.org/pdf/2401.01234.pdf",
        )
    ]


def test_collect_lab_uses_bilibili_video_ai_extraction(tmp_path, monkeypatch):
    lab_dir = tmp_path / "深蓝学院"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://space.bilibili.com/320203065/upload/video\n")
    paper = PaperCandidate(
        "Learning Robot Skills from Video",
        2024,
        "https://www.bilibili.com/video/BV1",
        "https://arxiv.org/pdf/2401.01234.pdf",
    )

    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(
        "labs.download_paper.fetch_bilibili_video_metadata",
        lambda url, timeout, limit: [{"title": "video"}],
    )
    monkeypatch.setattr("labs.download_paper.extract_papers_from_bilibili_videos", lambda text, base_url, min_year, timeout: [paper])

    found, new = collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=True, extractor="hybrid")

    assert (found, new) == (1, 1)


def test_collect_lab_fetches_current_google_scholar_page(tmp_path, monkeypatch):
    lab_dir = tmp_path / "goldberg"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text(
        "https://scholar.google.com/citations?hl=en&user=abc&view_op=list_works&sortby=pubdate\n"
    )
    calls = []

    def scholar_row(title, arxiv_id, year):
        return f"""
        <tr class="gsc_a_tr">
          <td class="gsc_a_t">
            <a href="/citations?view_op=view_citation&amp;citation_for_view=abc" class="gsc_a_at">{title}</a>
            <div class="gs_gray">arXiv preprint arXiv:{arxiv_id}<span class="gs_oph">, {year}</span></div>
          </td>
          <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">{year}</span></td>
        </tr>
        """

    pages = [
        "<table>" + scholar_row("Robot Policy Learning One", "2601.00001", 2026) + "</table>",
        "<table>"
        + scholar_row("Robot Policy Learning Two", "2301.00002", 2023)
        + scholar_row("Old Robot Policy Learning", "2201.00003", 2022)
        + "</table>",
    ]

    def fake_fetch_text(url, timeout):
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr("labs.download_paper.fetch_text", fake_fetch_text)

    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", lambda *args, **kwargs: None)
    monkeypatch.setattr("labs.download_paper.resolve_google_scholar_row_pdf", lambda *args, **kwargs: None)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=True, extractor="static")

    assert (found, new) == (1, 0)
    assert len(calls) == 1
    assert "pagesize=100" in calls[0]
    assert "cstart=0" in calls[0]


def test_fetch_publication_html_stops_google_scholar_pages_when_page_has_no_rows(monkeypatch):
    calls = []
    pages = [
        """
        <table><tbody id="gsc_a_b">
          <tr class="gsc_a_tr">
            <td class="gsc_a_t">
              <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
                Robot Policy Learning One
              </a>
            </td>
            <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
          </tr>
        </tbody></table>
        """,
        "<html><body>No articles here, but noisy footer says 2026 and 2025.</body></html>",
    ]

    def fake_fetch(url, timeout):
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)

    html = fetch_publication_html("https://scholar.google.com/citations?user=abc", min_year=2023, timeout=1)

    assert "Robot Policy Learning One" in html
    assert len(calls) == 2
    assert "cstart=0" in calls[0]
    assert "cstart=100" in calls[1]


def test_collect_lab_resolves_current_google_scholar_page_for_download(tmp_path, monkeypatch, capsys):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    events = []

    def list_row(title, paper_id, year):
        return f"""
        <tr class="gsc_a_tr">
          <td class="gsc_a_t">
            <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:{paper_id}" class="gsc_a_at">
              {title}
            </a>
          </td>
          <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">{year}</span></td>
        </tr>
        """

    def fake_fetch(url, timeout, attempts=3):
        if "view_citation" in url:
            paper_id = url.rsplit(":", 1)[-1]
            events.append(f"citation:{paper_id}")
            return f'<a href="https://arxiv.org/pdf/2601.{paper_id[-5:]}.pdf">PDF</a>'
        if "cstart=100" in url:
            events.append("list:100")
            return "<html><body>No more publication rows in 2026.</body></html>"
        events.append("list:0")
        return "<table><tbody>" + list_row("Streaming Scholar Paper One", "paper00001", 2026) + "</tbody></table>"

    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", lambda title, page_url, min_year, timeout: None)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=True, extractor="static")
    output = capsys.readouterr().out

    assert (found, new) == (1, 1)
    assert events == ["list:0", "citation:paper00001"]
    assert "[google-scholar-paper 1] 2026 | Streaming Scholar Paper One" in output
    assert (lab_dir / "scholar.html").exists()
    assert "Streaming Scholar Paper One" in (lab_dir / "scholar.html").read_text()


def test_collect_lab_reports_google_scholar_captcha_page(tmp_path, monkeypatch, capsys):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")

    def fake_fetch(url, timeout, attempts=3):
        return """
        <html><body>
          <form id="captcha-form">
            Our systems have detected unusual traffic from your computer network.
            <div class="g-recaptcha"></div>
          </form>
        </body></html>
        """

    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=True, extractor="static")
    captured = capsys.readouterr()

    assert (found, new) == (0, 0)
    assert "Google Scholar returned a CAPTCHA/unusual-traffic page" in captured.err


def test_collect_lab_saves_google_scholar_http_error_body(tmp_path, monkeypatch, capsys):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    error_body = b"<html><body>Too Many Requests</body></html>"

    class ErrorBody:
        def read(self):
            return error_body

        def close(self):
            return None

    def fake_fetch(url, timeout, attempts=3):
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=ErrorBody())

    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=True, extractor="static")
    captured = capsys.readouterr()

    assert (found, new) == (0, 0)
    assert "Google Scholar returned HTTP 429" in captured.err
    assert (lab_dir / "scholar.html").read_text() == error_body.decode()


def test_collect_lab_searches_arxiv_for_google_scholar_title_rows_without_pdf(tmp_path, monkeypatch):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text(
        "https://scholar.google.com/citations?hl=en&user=abc&view_op=list_works&sortby=pubdate\n"
    )
    html = """
    <table><tbody id="gsc_a_b">
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
            FoldNet++: a Large-Scale Synthetic Dataset for Robotic T-Shirt Folding and Unfolding
          </a>
          <div class="gs_gray">H Wang, Example Author</div>
          <div class="gs_gray">Conference on Robot Learning</div>
        </td>
        <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
      </tr>
    </tbody></table>
    """
    calls = []

    def fake_search(title, page_url, min_year, timeout):
        calls.append((title, page_url, min_year, timeout))
        return PaperCandidate(
            title=title,
            year=2026,
            page_url=page_url,
            pdf_url="https://arxiv.org/pdf/2601.00001.pdf",
        )

    def fake_fetch_publication_html(link, min_year, timeout, cache_path=None, on_page=None):
        if on_page is not None:
            on_page(html)
        return html

    monkeypatch.setattr("labs.download_paper.fetch_publication_html", fake_fetch_publication_html)
    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", lambda url, timeout, attempts=3: "")
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", fake_search)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=True, extractor="static")

    assert (found, new) == (1, 1)
    assert calls == [(
        "FoldNet++: a Large-Scale Synthetic Dataset for Robotic T-Shirt Folding and Unfolding",
        "https://scholar.google.com/citations?view_op=view_citation&citation_for_view=abc:paper1",
        2023,
        10,
    )]


def test_collect_lab_fetches_google_scholar_citation_page_pdf_links(tmp_path, monkeypatch):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text(
        "https://scholar.google.com/citations?hl=en&user=abc&view_op=list_works&sortby=pubdate\n"
    )
    list_html = """
    <table><tbody id="gsc_a_b">
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
            FoldNet++: a Large-Scale Synthetic Dataset for Robotic T-Shirt Folding and Unfolding
          </a>
          <div class="gs_gray">H Wang, Example Author</div>
          <div class="gs_gray">Conference on Robot Learning</div>
        </td>
        <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
      </tr>
    </tbody></table>
    """
    citation_html = """
    <html><body>
      <div id="gsc_oci_title">
        <a href="https://arxiv.org/abs/2609.12433">FoldNet++: a Large-Scale Synthetic Dataset</a>
      </div>
      <div class="gsc_oci_merged_snippet">
        <a href="https://arxiv.org/pdf/2609.12433">[PDF]</a> from arxiv.org
      </div>
    </body></html>
    """

    def fake_fetch_publication_html(link, min_year, timeout, cache_path=None, on_page=None):
        if on_page is not None:
            on_page(list_html)
        return list_html

    monkeypatch.setattr("labs.download_paper.fetch_publication_html", fake_fetch_publication_html)
    monkeypatch.setattr("labs.download_paper.fetch_text_once", lambda url, timeout: citation_html)
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", lambda title, page_url, min_year, timeout: None)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=True, extractor="static")

    assert (found, new) == (1, 1)


def test_collect_lab_enters_google_scholar_paper_pages_even_when_list_has_arxiv_id(tmp_path, monkeypatch):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    list_html = """
    <table><tbody id="gsc_a_b">
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
            LDA-1B: Scaling Latent Dynamics Action Model via Universal Embodied Data Ingestion
          </a>
          <div class="gs_gray">arXiv preprint arXiv:2601.00001, 2026</div>
        </td>
        <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
      </tr>
    </tbody></table>
    """
    citation_calls = []

    def fake_fetch_scholar(url, timeout, attempts=1):
        citation_calls.append(url)
        return '<a href="https://arxiv.org/pdf/2601.00001.pdf">PDF</a>'

    def fake_fetch_publication_html(link, min_year, timeout, cache_path=None, on_page=None):
        if on_page is not None:
            on_page(list_html)
        return list_html

    monkeypatch.setattr("labs.download_paper.fetch_publication_html", fake_fetch_publication_html)
    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch_scholar)
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", lambda *args, **kwargs: None)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=True, extractor="static")

    assert (found, new) == (1, 1)
    assert citation_calls == ["https://scholar.google.com/citations?view_op=view_citation&citation_for_view=abc:paper1"]


def test_collect_lab_uses_cached_google_scholar_html_when_present(tmp_path, monkeypatch):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    (lab_dir / "scholar.html").write_text(
        """
        <table><tbody id="gsc_a_b">
          <tr class="gsc_a_tr">
            <td class="gsc_a_t">
              <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
                Cached Scholar Paper for Robot Learning
              </a>
              <div class="gs_gray">arXiv preprint arXiv:2601.00001, 2026</div>
            </td>
            <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
          </tr>
        </tbody></table>
        """
    )

    def fail_fetch(link, min_year, timeout, cache_path=None, on_page=None):
        raise AssertionError("network fetch should not run when scholar.html exists")

    monkeypatch.setattr("labs.download_paper.fetch_publication_html", fail_fetch)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=True, extractor="static")

    assert (found, new) == (1, 0)


@pytest.mark.parametrize("cached", [True, False])
def test_collect_lab_downloads_google_scholar_rows_one_by_one(tmp_path, monkeypatch, cached):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    html = (
        """
        <table><tbody id="gsc_a_b">
          <tr class="gsc_a_tr">
            <td class="gsc_a_t">
              <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
                Cached Scholar Paper One
              </a>
            </td>
            <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
          </tr>
          <tr class="gsc_a_tr">
            <td class="gsc_a_t">
              <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper2" class="gsc_a_at">
                Cached Scholar Paper Two
              </a>
            </td>
            <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2025</span></td>
          </tr>
        </tbody></table>
        """
    )
    if cached:
        (lab_dir / "scholar.html").write_text(html)
    else:
        def fake_fetch_publication_html(link, min_year, timeout, cache_path=None, on_page=None):
            if on_page is not None:
                on_page(html)
            return html

        monkeypatch.setattr("labs.download_paper.fetch_publication_html", fake_fetch_publication_html)
    events = []

    def fake_search(title, page_url, min_year, timeout):
        events.append(f"arxiv:{title}")
        return None

    def fake_fetch(url, timeout, attempts=1):
        paper_id = url.rsplit(":", 1)[-1]
        events.append(f"citation:{paper_id}")
        return f'<a href="https://arxiv.org/pdf/2601.{paper_id[-1] * 5}.pdf">PDF</a>'

    def fake_download(url, destination, timeout):
        events.append(f"download:{destination.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"pdf")

    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", fake_search)
    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)
    monkeypatch.setattr("labs.download_paper.download_pdf", fake_download)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda seconds: events.append(f"sleep:{seconds}"))

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=False, extractor="static")

    assert (found, new) == (2, 2)
    assert events == [
        "arxiv:Cached Scholar Paper One",
        "citation:paper1",
        "download:2026-cached-scholar-paper-one.pdf",
        "sleep:1.0",
        "arxiv:Cached Scholar Paper Two",
        "citation:paper2",
        "download:2025-cached-scholar-paper-two.pdf",
        "sleep:1.0",
    ]


def test_collect_lab_searches_arxiv_when_cached_google_scholar_row_has_no_pdf(tmp_path, monkeypatch, capsys):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    (lab_dir / "scholar.html").write_text(
        """
        <table><tbody id="gsc_a_b">
          <tr class="gsc_a_tr">
            <td class="gsc_a_t">
              <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
                Cached Scholar Paper With Arxiv Match
              </a>
            </td>
            <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
          </tr>
        </tbody></table>
        """
    )
    events = []

    def fake_fetch(url, timeout, attempts=1):
        events.append("citation")
        raise AssertionError("citation page should not be fetched when arXiv search succeeds")

    def fake_search(title, page_url, min_year, timeout):
        events.append(f"arxiv:{title}")
        return PaperCandidate(title, 2026, page_url, "https://arxiv.org/pdf/2601.12345.pdf")

    def fake_download(url, destination, timeout):
        events.append(f"download:{url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"pdf")

    monkeypatch.setattr("labs.download_paper.fetch_google_scholar_text", fake_fetch)
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", fake_search)
    monkeypatch.setattr("labs.download_paper.download_pdf", fake_download)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=30, dry_run=False, extractor="static")
    output = capsys.readouterr().out

    assert (found, new) == (1, 1)
    assert "[google-scholar-download 1/1] resolving: Cached Scholar Paper With Arxiv Match" in output
    assert events == [
        "arxiv:Cached Scholar Paper With Arxiv Match",
        "download:https://arxiv.org/pdf/2601.12345.pdf",
    ]


def test_collect_lab_stops_google_scholar_citation_page_search_after_rate_limit(tmp_path, monkeypatch):
    lab_dir = tmp_path / "hewang"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://scholar.google.com/citations?user=abc\n")
    rows = "\n".join(
        f"""
        <tr class="gsc_a_tr">
          <td class="gsc_a_t">
            <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper{index}" class="gsc_a_at">
              Cached Scholar Robot Learning Paper {index}
            </a>
            <div class="gs_gray">Conference on Robot Learning</div>
          </td>
          <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
        </tr>
        """
        for index in range(2)
    )
    (lab_dir / "scholar.html").write_text(f"<table><tbody id=\"gsc_a_b\">{rows}</tbody></table>")
    calls = []

    def rate_limited_fetch(url, timeout):
        calls.append(url)
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)

    monkeypatch.setattr("labs.download_paper.fetch_text_once", rate_limited_fetch)
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_title", lambda title, page_url, min_year, timeout: None)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=True, extractor="static")

    assert (found, new) == (2, 0)
    assert len(calls) == 2


def test_google_scholar_extraction_ignores_aggregate_saved_html_blocks():
    html = """
    <table><tbody id="gsc_a_b">
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
            Real Robot Learning Paper One
          </a>
          <div class="gs_gray">CoRL 2026</div>
        </td>
        <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
      </tr>
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper2" class="gsc_a_at">
            Real Robot Learning Paper Two
          </a>
          <div class="gs_gray">CoRL 2025</div>
        </td>
        <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2025</span></td>
      </tr>
    </tbody></table>
    <div>
      <a class="gsc_a_at" href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1">
        Real Robot Learning Paper One
      </a>
      <a class="gsc_a_at" href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper2">
        Real Robot Learning Paper Two
      </a>
      citation chart style noise 2089
    </div>
    """

    rows = extract_google_scholar_title_rows(html, "https://scholar.google.com/citations?user=abc", min_year=1900)

    assert [(title, year) for title, year, _ in rows] == [
        ("Real Robot Learning Paper One", 2026),
        ("Real Robot Learning Paper Two", 2025),
    ]


def test_google_scholar_extraction_uses_year_cell_not_page_range():
    html = """
    <table><tbody id="gsc_a_b">
      <tr class="gsc_a_tr">
        <td class="gsc_a_t">
          <a href="/citations?view_op=view_citation&amp;citation_for_view=abc:paper1" class="gsc_a_at">
            Unleashing Humanoid Reaching Potential via Real-world-Ready Skill Space
          </a>
          <div class="gs_gray">IEEE Robotics and Automation Letters 11 (2), 2082 - 2089</div>
          <div class="gs_gray">, 2026</div>
        </td>
        <td class="gsc_a_y"><span class="gsc_a_h gsc_a_hc gs_ibl">2026</span></td>
      </tr>
    </tbody></table>
    """

    rows = extract_google_scholar_title_rows(html, "https://scholar.google.com/citations?user=abc", min_year=1900)

    assert rows[0][1] == 2026


@pytest.mark.parametrize("entry_count", [10, 60])
def test_fetch_bilibili_video_metadata_defaults_to_fifty_videos(monkeypatch, entry_count):
    calls = []

    def fake_run_yt_dlp_json(args, timeout):
        calls.append(args)
        if "--flat-playlist" in args:
            return {
                "entries": [{"id": f"BV{index}"} for index in range(entry_count)]
            }
        return {"title": args[-1], "webpage_url": args[-1]}

    monkeypatch.setattr("labs.download_paper._run_yt_dlp_json", fake_run_yt_dlp_json)

    metadata = fetch_bilibili_video_metadata("https://space.bilibili.com/1/upload/video", timeout=1)

    assert calls[0] == [
        "--flat-playlist",
        "--dump-single-json",
        "--playlist-end",
        "50",
        "--no-warnings",
        "https://space.bilibili.com/1/upload/video",
    ]
    assert len(metadata) == min(entry_count, 50)
    assert len(calls) == 1 + min(entry_count, 50)


def test_collect_lab_searches_arxiv_before_recording_unmatched_bilibili_video(tmp_path, monkeypatch):
    lab_dir = tmp_path / "深蓝学院"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://space.bilibili.com/320203065/upload/video\n")
    metadata = [
        {
            "title": "Video mentions enough metadata for a paper",
            "webpage_url": "https://www.bilibili.com/video/BVfound",
            "description": "robot foundation model manipulation",
        },
        {
            "title": "Ambiguous weekly discussion",
            "webpage_url": "https://www.bilibili.com/video/BVmanual",
            "description": "",
        },
    ]
    found_paper = PaperCandidate(
        "Robot Foundation Models for Manipulation",
        2024,
        "https://www.bilibili.com/video/BVfound",
        "https://arxiv.org/pdf/2401.01234.pdf",
    )

    monkeypatch.setattr("labs.download_paper.fetch_bilibili_video_metadata", lambda url, timeout, limit: metadata)
    monkeypatch.setattr("labs.download_paper.search_arxiv_for_bilibili_video", lambda item, min_year, timeout: found_paper if item["webpage_url"].endswith("BVfound") else None)
    monkeypatch.setattr("labs.download_paper.download_pdf", lambda url, destination, timeout: None)

    found, new = collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=False, extractor="static")

    assert (found, new) == (1, 1)
    assert json.loads((lab_dir / "papers.json").read_text())[0]["title"] == "Robot Foundation Models for Manipulation"
    assert (lab_dir / "failed.txt").read_text() == "https://www.bilibili.com/video/BVmanual\n"


def test_search_arxiv_for_bilibili_video_parses_first_recent_result(monkeypatch):
    atom = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/2401.01234</id>
        <title>Robot Foundation Models for Manipulation</title>
        <published>2024-01-31T00:00:00Z</published>
      </entry>
    </feed>
    """

    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: atom)

    paper = search_arxiv_for_bilibili_video(
        {
            "title": "Video: robot foundation model manipulation",
            "webpage_url": "https://www.bilibili.com/video/BVfound",
            "description": "",
        },
        min_year=2023,
        timeout=1,
    )

    assert paper == PaperCandidate(
        "Robot Foundation Models for Manipulation",
        2024,
        "https://www.bilibili.com/video/BVfound",
        "https://arxiv.org/pdf/2401.01234.pdf",
    )


def test_fetch_text_retries_transient_ssl_errors(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ssl.SSLError("DECRYPTION_FAILED_OR_BAD_RECORD_MAC")
        return FakeResponse()

    monkeypatch.setattr("labs.download_paper.urlopen", fake_urlopen)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda seconds: None)

    assert fetch_text("https://example.com", timeout=1) == "ok"
    assert calls["count"] == 2


def test_download_pdf_retries_transient_ssl_errors(tmp_path, monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"%PDF"

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ssl.SSLError("DECRYPTION_FAILED_OR_BAD_RECORD_MAC")
        return FakeResponse()

    monkeypatch.setattr("labs.download_paper.urlopen", fake_urlopen)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda seconds: None)

    destination = tmp_path / "paper.pdf"
    download_pdf("https://example.com/paper.pdf", destination, timeout=1)

    assert destination.read_bytes() == b"%PDF"
    assert calls["count"] == 2


def test_download_pdf_logs_retry_attempts(tmp_path, monkeypatch, capsys):
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"%PDF"

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ssl.SSLError("DECRYPTION_FAILED_OR_BAD_RECORD_MAC")
        return FakeResponse()

    monkeypatch.setattr("labs.download_paper.urlopen", fake_urlopen)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda seconds: None)

    download_pdf("https://example.com/paper.pdf", tmp_path / "paper.pdf", timeout=1)

    assert "attempt 1/4 failed" in capsys.readouterr().err


def test_download_pdf_retries_failed_http_downloads_three_times(tmp_path, monkeypatch, capsys):
    calls = {"count": 0}
    events = []

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        events.append("attempt")
        raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr("labs.download_paper.urlopen", fake_urlopen)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda seconds: events.append(("sleep", seconds)))

    try:
        download_pdf("https://example.com/missing.pdf", tmp_path / "missing.pdf", timeout=1)
    except HTTPError:
        pass
    else:
        raise AssertionError("expected HTTPError")

    stderr = capsys.readouterr().err
    assert calls["count"] == 4
    assert events == ["attempt", ("sleep", 0.5), "attempt", ("sleep", 0.5), "attempt", ("sleep", 0.5), "attempt"]
    assert not (tmp_path / "missing.pdf").exists()
    assert stderr.count("[download:failed]") == 4
    assert "attempt 4/4 failed" in stderr


def test_download_pdf_retries_ssl_errors_during_read(tmp_path, monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, should_fail):
            self.should_fail = should_fail

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            if self.should_fail:
                raise ssl.SSLError("DECRYPTION_FAILED_OR_BAD_RECORD_MAC")
            return b"%PDF"

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        return FakeResponse(should_fail=calls["count"] == 1)

    monkeypatch.setattr("labs.download_paper.urlopen", fake_urlopen)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda seconds: None)

    destination = tmp_path / "paper.pdf"
    download_pdf("https://example.com/paper.pdf", destination, timeout=1)

    assert destination.read_bytes() == b"%PDF"
    assert calls["count"] == 2


def test_fetch_text_attempts_three_times_before_raising(monkeypatch):
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        raise ssl.SSLError("DECRYPTION_FAILED_OR_BAD_RECORD_MAC")

    monkeypatch.setattr("labs.download_paper.urlopen", fake_urlopen)
    monkeypatch.setattr("labs.download_paper.time.sleep", lambda seconds: None)

    try:
        fetch_text("https://example.com", timeout=1)
    except ssl.SSLError:
        pass
    else:
        raise AssertionError("expected ssl.SSLError")

    assert calls["count"] == 3


def test_yt_dlp_json_uses_bilibili_cookie_env(monkeypatch):
    captured = {}

    def fake_run(command, capture_output, text, timeout, check):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setenv("BILIBILI_COOKIES", "/tmp/bilibili-cookies.txt")
    monkeypatch.setattr("labs.download_paper.subprocess.run", fake_run)

    assert _run_yt_dlp_json(["--dump-single-json", "https://example.com/video"], timeout=1) == {"ok": True}
    assert captured["command"][:3] == ["yt-dlp", "--cookies", "/tmp/bilibili-cookies.txt"]


@pytest.mark.parametrize("extra_args", [[], ["--limit", "1"]])
def test_main_skips_bilibili_labs_by_default(tmp_path, monkeypatch, extra_args):
    labs_root = tmp_path / "labs"
    bilibili_lab = labs_root / "bilibili"
    web_lab = labs_root / "web"
    bilibili_lab.mkdir(parents=True)
    web_lab.mkdir()
    (bilibili_lab / "link.txt").write_text("https://space.bilibili.com/483478083/upload/video\n")
    (web_lab / "link.txt").write_text("https://example.com/publications\n")
    captured = {}

    def fake_run_labs(lab_dirs, min_year, timeout, dry_run, extractor, workers):
        captured["cookie_browser"] = os.environ.get("BILIBILI_COOKIES_FROM_BROWSER")
        captured["labs"] = [lab_dir.name for lab_dir in lab_dirs]
        return 0

    monkeypatch.delenv("BILIBILI_COOKIES", raising=False)
    monkeypatch.delenv("BILIBILI_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.setattr("labs.download_paper.run_labs", fake_run_labs)

    assert main(["--labs-root", str(labs_root), *extra_args]) == 0
    assert captured == {"cookie_browser": None, "labs": ["web"]}


def test_yt_dlp_json_explains_bilibili_412(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        raise subprocess.CalledProcessError(
            1,
            command,
            stderr="ERROR: Request is blocked by server (412), please wait and try later.",
        )

    monkeypatch.setattr("labs.download_paper.subprocess.run", fake_run)

    try:
        _run_yt_dlp_json(["--dump-single-json", "https://space.bilibili.com/1/upload/video"], timeout=1)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert "--bilibili-cookies-from-browser chrome" in message


def test_filter_new_papers_skips_manifest_and_existing_pdf(tmp_path):
    lab_dir = tmp_path / "lab"
    pdf_dir = lab_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "already-here.pdf").write_bytes(b"%PDF")
    (lab_dir / "papers.json").write_text(
        json.dumps(
            [
                {
                    "title": "Already Manifested",
                    "year": 2024,
                    "pdf_url": "https://example.com/already.pdf",
                    "pdf_path": "pdfs/already.pdf",
                }
            ]
        )
    )
    candidates = [
        PaperCandidate("Already Manifested", 2024, "https://example.com/a", "https://example.com/already.pdf"),
        PaperCandidate("Already Here", 2024, "https://example.com/b", "https://example.com/already-here.pdf"),
        PaperCandidate("New Paper", 2025, "https://example.com/c", "https://example.com/new.pdf"),
    ]

    assert filter_new_papers(lab_dir, candidates) == [candidates[-1]]


def test_filter_new_papers_sorts_by_output_filename(tmp_path):
    lab_dir = tmp_path / "lab"
    lab_dir.mkdir()
    candidates = [
        PaperCandidate("Zeta Robot Paper", 2025, "https://example.com/z", "https://example.com/z.pdf"),
        PaperCandidate("Alpha Robot Paper", 2024, "https://example.com/a", "https://example.com/a.pdf"),
        PaperCandidate("Beta Robot Paper", 2024, "https://example.com/b", "https://example.com/b.pdf"),
    ]

    assert [paper.title for paper in filter_new_papers(lab_dir, candidates)] == [
        "Alpha Robot Paper",
        "Beta Robot Paper",
        "Zeta Robot Paper",
    ]


def test_collect_lab_records_failed_download_titles(tmp_path, monkeypatch):
    lab_dir = tmp_path / "airlab(basti)"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://example.com/publications/\n")
    html = """
    <article>
      <h2>Robot Learning in the Wild</h2>
      <span>CoRL 2024</span>
      <a href="/papers/wild.pdf">PDF</a>
    </article>
    """

    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: html)

    def fail_download(url, destination, timeout):
        raise URLError("network down")

    monkeypatch.setattr("labs.download_paper.download_pdf", fail_download)

    collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=False, extractor="static")

    assert (lab_dir / "failed.txt").read_text() == "Robot Learning in the Wild\n"


def test_collect_lab_does_not_duplicate_failed_titles(tmp_path, monkeypatch):
    lab_dir = tmp_path / "airlab(basti)"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://example.com/publications/\n")
    (lab_dir / "failed.txt").write_text("Robot Learning in the Wild\n")
    html = """
    <article>
      <h2>Robot Learning in the Wild</h2>
      <span>CoRL 2024</span>
      <a href="/papers/wild.pdf">PDF</a>
    </article>
    """

    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: html)
    monkeypatch.setattr(
        "labs.download_paper.download_pdf",
        lambda url, destination, timeout: (_ for _ in ()).throw(URLError("network down")),
    )

    collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=False, extractor="static")

    assert (lab_dir / "failed.txt").read_text() == "Robot Learning in the Wild\n"


def test_collect_lab_continues_after_incomplete_read(tmp_path, monkeypatch):
    lab_dir = tmp_path / "ppl(shubham)"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://example.com/publications/\n")
    html = """
    <article>
      <h2>AerialMegaDepth: Learning Aerial-Ground Reconstruction and View Synthesis</h2>
      <span>CVPR 2025</span>
      <a href="/papers/aerialmegadepth.pdf">PDF</a>
    </article>
    """

    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: html)
    monkeypatch.setattr(
        "labs.download_paper.download_pdf",
        lambda url, destination, timeout: (_ for _ in ()).throw(IncompleteRead(b"partial", 10)),
    )

    collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=False, extractor="static")

    assert (lab_dir / "failed.txt").read_text() == (
        "AerialMegaDepth: Learning Aerial-Ground Reconstruction and View Synthesis\n"
    )


def test_collect_lab_continues_after_invalid_url(tmp_path, monkeypatch):
    lab_dir = tmp_path / "bad-url"
    lab_dir.mkdir()
    (lab_dir / "link.txt").write_text("https://example.com/publications/\n")
    paper = PaperCandidate("Bad URL Paper", 2026, "https://example.com/project", "https://example.com/bad url.pdf")

    monkeypatch.setattr("labs.download_paper.fetch_text", lambda url, timeout: "<html></html>")
    monkeypatch.setattr("labs.download_paper.choose_candidates", lambda html, link, min_year, timeout, extractor: [paper])
    monkeypatch.setattr(
        "labs.download_paper.download_pdf",
        lambda url, destination, timeout: (_ for _ in ()).throw(InvalidURL("bad url")),
    )

    collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=False, extractor="static")

    assert (lab_dir / "failed.txt").read_text() == "Bad URL Paper\n"


def test_safe_filename_keeps_names_portable():
    assert safe_filename("RoboT: Learning/Control? 2024!") == "robot-learning-control-2024"


def test_generic_section_headings_are_not_papers():
    assert not is_probable_publication_title("Selected Research and Publications")
    assert not is_probable_publication_title("Industry")
    assert is_probable_publication_title("Robot Utility Models: General Policies for Zero-Shot Deployment")


def test_clean_title_trims_author_and_venue_tail():
    title = clean_title(
        "AnySkin: Plug-and-play Skin Sensing for Robotic Touch "
        "Raunaq Bhirangi , Venkatesh Pattabiraman In ICRA"
    )

    assert title == "AnySkin: Plug-and-play Skin Sensing for Robotic Touch"


def test_clean_title_keeps_capitalized_title_endings():
    assert (
        clean_title("Robot Utility Models: General Policies for Zero-Shot Deployment in New Environments")
        == "Robot Utility Models: General Policies for Zero-Shot Deployment in New Environments"
    )
