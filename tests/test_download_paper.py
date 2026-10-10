import json
import ssl
import subprocess
from http.client import IncompleteRead, InvalidURL
from pathlib import Path

from labs.download_paper import (
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
    filter_bilibili_lab_dirs,
    filter_new_papers,
    fetch_bilibili_video_metadata,
    fetch_text,
    format_lab_progress,
    format_year_counts,
    is_bilibili_url,
    is_probable_publication_title,
    main,
    parse_publication_page,
    run_labs,
    safe_filename,
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


def test_default_timeout_is_thirty_minutes():
    assert DEFAULT_TIMEOUT_SECONDS == 30 * 60


def test_default_workers_is_two():
    assert DEFAULT_WORKERS == 2


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


def test_collect_lab_fetches_google_scholar_pages_until_min_year(tmp_path, monkeypatch):
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

    found, new = collect_lab(lab_dir, min_year=2023, timeout=1, dry_run=True, extractor="static")

    assert (found, new) == (2, 2)
    assert len(calls) == 2
    assert "pagesize=100" in calls[0]
    assert "cstart=0" in calls[0]
    assert "cstart=100" in calls[1]


def test_fetch_bilibili_video_metadata_limits_playlist_to_latest_first_page(monkeypatch):
    calls = []

    def fake_run_yt_dlp_json(args, timeout):
        calls.append(args)
        if "--flat-playlist" in args:
            return {
                "entries": [
                    {"id": "BV1"},
                    {"id": "BV2"},
                ]
            }
        return {"title": args[-1], "webpage_url": args[-1]}

    monkeypatch.setattr("labs.download_paper._run_yt_dlp_json", fake_run_yt_dlp_json)

    metadata = fetch_bilibili_video_metadata("https://space.bilibili.com/1/upload/video", timeout=1, limit=30)

    assert calls[0] == [
        "--flat-playlist",
        "--dump-single-json",
        "--playlist-end",
        "30",
        "--no-warnings",
        "https://space.bilibili.com/1/upload/video",
    ]
    assert len(metadata) == 2


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


def test_fetch_text_retries_ssl_errors_three_times_before_raising(monkeypatch):
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

    assert calls["count"] == 4


def test_yt_dlp_json_uses_bilibili_cookie_env(monkeypatch):
    captured = {}

    def fake_run(command, capture_output, text, timeout, check):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setenv("BILIBILI_COOKIES", "/tmp/bilibili-cookies.txt")
    monkeypatch.setattr("labs.download_paper.subprocess.run", fake_run)

    assert _run_yt_dlp_json(["--dump-single-json", "https://example.com/video"], timeout=1) == {"ok": True}
    assert captured["command"][:3] == ["yt-dlp", "--cookies", "/tmp/bilibili-cookies.txt"]


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
