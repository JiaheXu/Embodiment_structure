import hashlib
import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import unquote
from unittest.mock import patch

import prepare_llmwiki
from prepare_llmwiki import import_labs


def pdf_bytes(text='example'):
    stream = f'BT /F1 12 Tf 20 100 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    data = b'%PDF-1.4\n'
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{number} 0 obj\n'.encode() + body + b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return data + b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(start).encode() + b'\n%%EOF\n'


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.labs = self.root / 'labs'
        self.dest = self.root / 'research'
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def paper(self, lab, stem, url, pdf=pdf_bytes(), summary='## Method\nA method.'):
        folder = self.labs / lab
        for name in ('pdfs', 'summary', 'summary_json'):
            (folder / name).mkdir(parents=True, exist_ok=True)
        if pdf is not None:
            (folder / 'pdfs' / (stem + '.pdf')).write_bytes(pdf)
        if summary is not None:
            (folder / 'summary' / (stem + '.md')).write_text('# A Paper\n\n- **Paper:** ' + url + '\n\n' + summary)
        row = {'title': 'A Paper', 'year': 2025, 'pdf_url': url, 'pdf_path': 'pdfs/' + stem + '.pdf', 'page_url': 'https://example.org/project'}
        manifest = folder / 'papers.json'
        rows = json.loads(manifest.read_text()) if manifest.exists() else []
        manifest.write_text(json.dumps(rows + [row]))
        return folder

    def snapshot(self):
        return {str(p.relative_to(self.labs)): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.labs.rglob('*') if p.is_file()}

    def test_export_uses_original_pdf_and_markdown_filenames(self):
        self.paper('A', '2025-cvpr-26-physx-anything-3d', 'https://arxiv.org/pdf/2501.12345')
        import_labs(self.labs, self.dest)
        folder = self.dest / 'sources/papers/2025-cvpr-26-physx-anything-3d'
        self.assertTrue((folder / '2025-cvpr-26-physx-anything-3d.pdf').is_file())
        self.assertTrue((folder / '2025-cvpr-26-physx-anything-3d.md').is_file())

    def test_only_flags_select_output_type_and_can_switch_back_to_both(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        for mode, suffix, excluded in [('pdf_only', '.pdf', '.md'), ('md_only', '.md', '.pdf')]:
            with self.subTest(mode=mode):
                dest = self.root / mode
                report = import_labs(self.labs, dest, **{mode: True})
                self.assertTrue(list((dest / 'sources').rglob('*' + suffix)))
                self.assertFalse(list((dest / 'sources').rglob('*' + excluded)))
                self.assertEqual(report['summary_files' if mode == 'pdf_only' else 'pdf_files'], 0)
                if mode == 'md_only':
                    self.assertEqual(report['pdf_bytes_to_copy'], 0)
                    self.assertNotIn('](one.pdf)', (dest / 'sources/papers/one/one.md').read_text())
                self.assertEqual(import_labs(self.labs, dest, **{mode: True})['files_written'], 0)
                import_labs(self.labs, dest)
                excluded_file = dest / ('sources/papers/one/one' + excluded)
                before = excluded_file.read_bytes(), excluded_file.stat().st_mtime_ns
                (folder / 'summary/one.md').write_text('# Updated summary')
                import_labs(self.labs, dest, **{mode: True})
                self.assertEqual((excluded_file.read_bytes(), excluded_file.stat().st_mtime_ns), before)
                import_labs(self.labs, dest)
                self.assertTrue(list((dest / 'sources').rglob('*.pdf')))
                self.assertTrue(list((dest / 'sources').rglob('*.md')))

    def test_only_flags_are_mutually_exclusive(self):
        self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            import_labs(self.labs, self.dest, pdf_only=True, md_only=True)
        self.assertFalse(self.dest.exists())

    def test_distinct_papers_with_same_original_name_get_separate_directories(self):
        self.paper('A', 'shared-name', 'https://arxiv.org/pdf/2608.21031')
        import_labs(self.labs, self.dest)
        first = self.dest / 'sources/papers/shared-name/shared-name.pdf'
        inode = first.stat().st_ino
        self.paper('B', 'shared-name', 'https://arxiv.org/pdf/2608.29769', pdf=pdf_bytes('other'))
        self.paper('C', 'shared-name--arxiv-2608.29769', 'https://arxiv.org/pdf/2609.11111', pdf=pdf_bytes('third'))
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 3)
        self.assertEqual(first.stat().st_ino, inode)
        second = self.dest / 'sources/papers/shared-name--arxiv-2608.29769/shared-name.pdf'
        self.assertEqual(second.read_bytes(), pdf_bytes('other'))
        self.assertEqual(len(list((self.dest / 'sources/papers').glob('*/'))), 3)
        for summary in (self.dest / 'sources/papers').rglob('*.md'):
            for link in re.findall(r'\]\(([^)]+\.pdf)\)', summary.read_text()):
                self.assertTrue((summary.parent / unquote(link)).is_file(), link)
        self.assertEqual(import_labs(self.labs, self.dest)['files_written'], 0)
        for mode in ('pdf_only', 'md_only'):
            dest = self.root / mode
            import_labs(self.labs, dest, **{mode: True})
            suffix = '*.pdf' if mode == 'pdf_only' else '*.md'
            self.assertEqual(len(list((dest / 'sources/papers').rglob(suffix))), 3)

    def test_generic_source_name_uses_descriptive_title_for_directory(self):
        folder = self.paper('A', '2026-paper', 'https://arxiv.org/pdf/2608.29769')
        (folder / 'summary/2026-paper.md').write_text('# Learning Agile Perceptive Traversal\n\nA summary.')
        import_labs(self.labs, self.dest)
        self.assertTrue((self.dest / 'sources/papers/2026-learning-agile-perceptive-traversal/2026-paper.pdf').is_file())
        self.assertFalse(list((self.dest / 'sources/papers').glob('2026-paper*')))

    def test_downloader_preserves_chinese_titles_in_filenames(self):
        from download_paper import safe_filename
        self.assertEqual(safe_filename('机器人感知重量'), '机器人感知重量')
        self.assertNotEqual(safe_filename('机器人感知重量'), safe_filename('人形机器人攀爬'))
        self.assertLessEqual(len(safe_filename('机器人' * 100).encode('utf-8')), 120)
        self.assertEqual(safe_filename('Learning Agile Traversal!'), 'learning-agile-traversal')

    def test_legacy_filenames_migrate_without_recopying_pdf(self):
        self.paper('A', 'original-paper', 'https://arxiv.org/pdf/2501.12345')
        import_labs(self.labs, self.dest)
        state = self.dest / '.llmwiki-import/catalog.json'
        catalog = json.loads(state.read_text())
        paper = catalog['papers']['arxiv-2501.12345']
        for field, extension in [('pdf_files', '.pdf'), ('summary_files', '-summary.md')]:
            relative = paper[field][0]
            legacy = 'sources/papers/arxiv-2501.12345/arxiv-2501.12345-a-paper' + extension
            (self.dest / legacy).parent.mkdir(parents=True, exist_ok=True)
            (self.dest / relative).rename(self.dest / legacy)
            catalog['outputs'][legacy] = catalog['outputs'].pop(relative)
            paper[field][0] = legacy
            if extension == '-summary.md':
                paper['primary_summary_file'] = legacy
        state.write_text(json.dumps(catalog))
        legacy_pdf = self.dest / paper['pdf_files'][0]
        inode = legacy_pdf.stat().st_ino
        real_rename = prepare_llmwiki.rename_outputs

        def interrupted_rename(destination, renames):
            real_rename(destination, dict(list(renames.items())[:1]))
            raise OSError('Simulated interruption after one rename')

        with patch('prepare_llmwiki.rename_outputs', side_effect=interrupted_rename):
            with self.assertRaisesRegex(OSError, 'Simulated interruption'):
                import_labs(self.labs, self.dest)
        report = import_labs(self.labs, self.dest)
        renamed = self.dest / 'sources/papers/original-paper/original-paper.pdf'
        self.assertTrue(renamed.is_file())
        self.assertEqual(renamed.stat().st_ino, inode)
        self.assertFalse(legacy_pdf.exists())
        self.assertEqual(report['files_renamed'], 1)
        final_catalog = json.loads(state.read_text())
        self.assertEqual(len(final_catalog['renamed_files']), 2)
        self.assertEqual(final_catalog['retained_files'], [])
        summary = (renamed.parent / 'original-paper.md').read_text()
        self.assertIn('](original-paper.pdf)', summary)
        self.assertEqual(import_labs(self.labs, self.dest)['files_written'], 0)

    def test_duplicate_original_names_keep_all_versions_and_working_pdf_links(self):
        self.paper('A', 'original', 'https://arxiv.org/pdf/2501.12345v1')
        self.paper('B', 'original', 'https://arxiv.org/pdf/2501.12345v2', pdf=pdf_bytes('updated'), summary='An alternative account')
        import_labs(self.labs, self.dest)
        paper = self.dest / 'sources/papers/original'
        self.assertEqual([p.name for p in paper.rglob('*.pdf')], ['original.pdf', 'original.pdf'])
        summaries = list(paper.rglob('*.md'))
        self.assertEqual([p.name for p in summaries], ['original.md', 'original.md'])
        for summary in summaries:
            for link in re.findall(r'\]\(([^)]+\.pdf)\)', summary.read_text()):
                self.assertTrue((summary.parent / unquote(link)).is_file(), link)

    def test_summary_updated_after_read_does_not_block_snapshot_import(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        summary = folder / 'summary/one.md'
        original = summary.read_text()
        real_check = prepare_llmwiki.pdf_issue

        def concurrent_summary_update(path):
            summary.write_text('# A newer summary\n\nWritten by the existing summarizer.')
            return real_check(path)

        with patch('prepare_llmwiki.pdf_issue', side_effect=concurrent_summary_update):
            report = import_labs(self.labs, self.dest)
        generated = self.dest / 'sources/papers/one/one.md'
        self.assertIn(original.rstrip(), generated.read_text())
        self.assertIn('Written by the existing summarizer.', summary.read_text())
        self.assertTrue(any('snapshot' in warning for warning in report['warnings']))

    def test_deduplicates_ids_keeps_versions_and_originals(self):
        self.paper('Lab-A', 'first', 'https://arxiv.org/pdf/2501.12345v1.pdf')
        self.paper('Channel-B', 'renamed', 'https://arxiv.org/abs/2501.12345v2', pdf=pdf_bytes('updated'), summary='## Method\nA different account.')
        before = self.snapshot()
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 1)
        paper = self.dest / 'sources/papers/renamed'
        self.assertEqual(len(list(paper.rglob('*.pdf'))), 2)
        self.assertEqual(len(list(paper.rglob('*.md'))), 2)
        summary = (paper / 'renamed.md').read_text()
        self.assertIn('Channel-B', summary)
        self.assertIn('Lab-A', summary)
        catalog = json.loads((self.dest / '.llmwiki-import/catalog.json').read_text())
        self.assertEqual(len(catalog['papers']['arxiv-2501.12345']['occurrences']), 2)
        self.assertEqual(before, self.snapshot())
        self.assertNotEqual((paper / 'renamed.pdf').stat().st_ino, (self.labs / 'Channel-B/pdfs/renamed.pdf').stat().st_ino)

    def test_checksum_matches_unidentified_paper_to_identified_copy(self):
        self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        self.paper('B', 'two', 'https://example.org/download/paper.pdf')
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 1)
        self.assertEqual(len(list((self.dest / 'sources').rglob('*.pdf'))), 1)

    def test_dry_run_makes_no_destination_and_does_not_touch_sources(self):
        self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        before = self.snapshot()
        report = import_labs(self.labs, self.dest, dry_run=True)
        self.assertEqual(report['papers'], 1)
        self.assertFalse(self.dest.exists())
        self.assertEqual(before, self.snapshot())

    def test_rerun_is_idempotent_and_preserves_wiki_and_local_edits(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        import_labs(self.labs, self.dest)
        wiki = self.dest / 'wiki/overview.md'
        wiki.parent.mkdir()
        wiki.write_text('User wiki')
        summary = self.dest / 'sources/papers/one/one.md'
        old_mtime = summary.stat().st_mtime_ns
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['files_written'], 0)
        self.assertEqual(summary.stat().st_mtime_ns, old_mtime)
        summary.write_text('User edit')
        (folder / 'summary/one.md').write_text('Upstream change')
        with self.assertRaisesRegex(ValueError, 'modified|conflict'):
            import_labs(self.labs, self.dest)
        self.assertEqual(summary.read_text(), 'User edit')
        self.assertEqual(wiki.read_text(), 'User wiki')

    def test_orphan_markdown_and_missing_pdf_are_preserved_and_reported(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345', pdf=None)
        (folder / 'summary/orphan.md').write_text('# Orphan\n\nAn independent note.')
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 2)
        self.assertTrue(report['warnings'])
        self.assertEqual(len(list((self.dest / 'sources/papers').glob('*/*.md'))), 2)

    def test_metadata_cannot_escape_source_root_or_overwrite_through_symlink(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        (folder / 'papers.json').write_text(json.dumps([{'pdf_path': '../../outside.pdf'}]))
        with self.assertRaisesRegex(ValueError, 'outside|escape'):
            import_labs(self.labs, self.dest)
        (folder / 'papers.json').write_text('[]')
        outside = self.root / 'outside'
        outside.mkdir()
        self.dest.mkdir()
        (self.dest / 'sources').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink|outside|escape'):
            import_labs(self.labs, self.dest)
        self.assertEqual(list(outside.iterdir()), [])

    def test_destination_cannot_overlap_original_archive(self):
        self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        with self.assertRaisesRegex(ValueError, 'overlap|source'):
            import_labs(self.labs, self.labs / 'output')

    def test_identifier_mismatch_is_flagged_in_sources_and_report(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        (folder / 'summary/one.md').write_text('# Wrong identity\n\n- **Paper:** https://arxiv.org/pdf/2501.99999\n')
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers_needing_review'], 1)
        self.assertIn('Identity needs review', (self.dest / 'sources/papers/one/one.md').read_text())

    def test_json_only_summary_is_rendered_and_non_arxiv_pdfs_are_not_lost(self):
        folder = self.paper('A', 'one', 'https://doi.org/10.1234/Example', summary=None)
        (folder / 'summary_json/one.json').write_text(json.dumps({'method': 'A structured-only summary', 'index_tags': {'task': ['navigation']}}))
        (folder / 'pdfs/unlisted.pdf').write_bytes(pdf_bytes('unlisted'))
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 2)
        self.assertEqual(report['pdf_files'], 2)
        summaries = [p.read_text() for p in (self.dest / 'sources/papers').glob('*/*.md')]
        self.assertTrue(any('A structured-only summary' in s and 'navigation' in s for s in summaries))
        self.assertEqual(report['papers_without_summary'], 1)

    def test_changed_source_updates_only_importer_owned_output(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        import_labs(self.labs, self.dest)
        (folder / 'summary/one.md').write_text('# Updated\n\nAn updated method.')
        import_labs(self.labs, self.dest)
        self.assertIn('An updated method.', (self.dest / 'sources/papers/one/one.md').read_text())

    def test_partial_import_cannot_discard_existing_catalog_entries(self):
        self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        self.paper('B', 'two', 'https://arxiv.org/pdf/2501.99999', pdf=pdf_bytes('other'))
        import_labs(self.labs, self.dest)
        before = (self.dest / '.llmwiki-import/catalog.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Partial import'):
            import_labs(self.labs, self.dest, lab_names=['A'])
        self.assertEqual((self.dest / '.llmwiki-import/catalog.json').read_bytes(), before)

    def test_unreadable_pdf_and_its_summary_are_ignored(self):
        self.paper('A', 'broken', 'https://arxiv.org/pdf/2501.12345', pdf=b'not a PDF')
        self.paper('A', 'empty', 'https://arxiv.org/pdf/2501.99999', pdf=pdf_bytes(''))
        self.paper('B', 'valid', 'https://arxiv.org/pdf/2501.11111')
        before = self.snapshot()
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 1)
        self.assertEqual(report['ignored_pdf_files'], 2)
        self.assertEqual(len(list((self.dest / 'sources/papers').rglob('*.pdf'))), 1)
        self.assertEqual(before, self.snapshot())

    def test_valid_version_survives_an_unreadable_duplicate(self):
        self.paper('A', 'broken', 'https://arxiv.org/pdf/2501.12345v2', pdf=b'not a PDF')
        self.paper('B', 'valid', 'https://arxiv.org/pdf/2501.12345v1')
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 1)
        self.assertEqual(report['pdf_files'], 1)
        self.assertEqual(report['ignored_pdf_files'], 1)

    def test_previously_imported_unreadable_record_is_hidden_without_deletion(self):
        folder = self.paper('A', 'one', 'https://arxiv.org/pdf/2501.12345')
        import_labs(self.labs, self.dest)
        generated = self.dest / 'sources/papers/one/one.pdf'
        original_copy = generated.read_bytes()
        (folder / 'pdfs/one.pdf').write_bytes(b'corrupt replacement')
        report = import_labs(self.labs, self.dest)
        self.assertEqual(report['papers'], 0)
        self.assertFalse(generated.exists())
        hidden = list((self.dest / '.llmwiki-import/ignored').rglob('*.pdf'))
        self.assertEqual(len(hidden), 1)
        self.assertEqual(hidden[0].read_bytes(), original_copy)
        self.assertEqual((folder / 'pdfs/one.pdf').read_bytes(), b'corrupt replacement')


if __name__ == '__main__':
    unittest.main()
