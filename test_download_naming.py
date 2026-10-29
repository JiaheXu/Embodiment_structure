import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import download_paper
from download_paper import PaperCandidate, canonical_paper_name, download_new_papers, filter_new_papers, paper_basename, title_from_first_page


class NamingRuleTests(unittest.TestCase):
    def test_basename_is_year_and_title_slug(self):
        self.assertEqual(paper_basename("Pedipulate: Enabling Manipulation Skills using a Quadruped Robot's Leg", 2024),
                         "2024-pedipulate-enabling-manipulation-skills-using-a-quadruped-robot-s-leg")
        self.assertEqual(paper_basename("", 2023, fallback="arxiv-2301.00001"), "2023-arxiv-2301.00001")
        self.assertEqual(paper_basename("机器人感知重量", 2026), "2026-机器人感知重量")

    def test_title_from_first_page(self):
        text = "arXiv:2402.10837v1 [cs.RO] 16 Feb 2024\n\nPedipulate: Enabling Manipulation Skills\nusing a Quadruped Robot's Leg\nPhilip Arm\nETH Zurich\nAbstract"
        self.assertEqual(title_from_first_page(text), "Pedipulate: Enabling Manipulation Skills using a Quadruped Robot's Leg")

    def test_arxiv_metadata_wins_then_page_then_listing(self):
        paper = PaperCandidate("只靠眼睛不够用！新智具身开源 5000 小时触觉数据", 2026, "https://www.bilibili.com/video/x", "https://arxiv.org/pdf/2608.29601.pdf")
        named = canonical_paper_name(paper, None, 30, arxiv_lookup=lambda url, t: ("N0-Foundation: Towards the Age of Tactile Intelligence", 2026))
        self.assertEqual((named["title_source"], named["filename"]), ("arxiv", "2026-n0-foundation-towards-the-age-of-tactile-intelligence.pdf"))
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "x.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            with patch.object(download_paper, "pdf_first_page_text", return_value="Learning Accurate Whole-body Throwing\nAuthors here\n"):
                named = canonical_paper_name(paper, pdf, 30, arxiv_lookup=lambda url, t: None)
            self.assertEqual(named["title_source"], "pdf_page1")
            self.assertTrue(named["filename"].startswith("2026-learning-accurate-whole-body-throwing"))
        latin = PaperCandidate("Learning Agile Traversal", 2025, "https://scholar.example", "https://example.org/p.pdf")
        named = canonical_paper_name(latin, None, 30, arxiv_lookup=lambda url, t: None)
        self.assertEqual((named["title_source"], named["filename"]), ("listing", "2025-learning-agile-traversal.pdf"))


class DownloadRenameTests(unittest.TestCase):
    def test_downloaded_file_is_renamed_and_listing_kept_in_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp)
            paper = PaperCandidate("视频标题：某篇论文", 2026, "https://www.bilibili.com/video/x", "https://arxiv.org/pdf/2608.29601.pdf")
            with patch.object(download_paper, "download_pdf", side_effect=lambda url, dest, timeout: (dest.parent.mkdir(parents=True, exist_ok=True), dest.write_bytes(b"%PDF-1.4\n"))), \
                 patch.object(download_paper, "resolve_arxiv_metadata", return_value=("A Real Paper Title", 2026)), \
                 patch.object(download_paper, "DOWNLOAD_PDF_DELAY_SECONDS", 0):
                downloaded, manifest = download_new_papers(lab, [paper], timeout=5, dry_run=False, manifest=[])
            self.assertEqual(downloaded, 1)
            record = manifest[0]
            self.assertEqual(record["title"], "A Real Paper Title")
            self.assertEqual(record["source_title"], "视频标题：某篇论文")
            self.assertEqual(record["pdf_path"], "pdfs/2026-a-real-paper-title.pdf")
            self.assertTrue((lab / "pdfs" / "2026-a-real-paper-title.pdf").is_file())
            self.assertFalse((lab / "pdfs" / "2026-视频标题-某篇论文.pdf").exists())
            # a rerun sees the listing title and the stored file name, so it does not download again
            (lab / "papers.json").write_text(json.dumps(manifest))
            self.assertEqual(filter_new_papers(lab, [paper]), [])


if __name__ == "__main__":
    unittest.main()
