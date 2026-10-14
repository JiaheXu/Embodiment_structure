from pathlib import Path

import pytest

from test_search import make_app, write_pdf


def test_inventory_rejects_symlink_outside_root(tmp_path):
    app = make_app(tmp_path)
    outside = tmp_path / 'outside.pdf'
    write_pdf(outside, 'Do not ingest this outside source')
    (app.settings.source_roots['papers'] / 'lab' / 'pdfs' / 'link.pdf').symlink_to(outside)
    assert app.ingestor.inventory('papers') == []


def test_corrupt_pdf_keeps_other_document_searchable(tmp_path):
    app = make_app(tmp_path)
    root = app.settings.source_roots['papers'] / 'lab' / 'pdfs'
    (root / 'corrupt.pdf').write_bytes(b'%PDF corrupt data')
    write_pdf(root / 'good.pdf', 'A camera policy with language inputs')
    run = app.ingest('papers')
    app.work_until_idle()
    status = app.status(run)
    assert status['state'] == 'partial'
    assert status['result']['searchable'] == 1
    assert status['result']['failed'] == 1


def test_summary_index_never_creates_pdf_evidence(tmp_path):
    app = make_app(tmp_path)
    summary = app.settings.source_roots['papers'] / 'lab' / 'summary'
    summary.mkdir()
    (summary / 'only.md').write_text('# Policy\nOur bimanual dexterous VLA is magical.')
    assert app.ingestor.index_summaries('papers')['indexed'] == 1
    from robotlit.contracts import SearchRequest
    out = app.run_search(SearchRequest(question='bimanual dexterous VLA'))
    assert not out['confirmed']
    assert out['unresolved'][0]['source_passages'] == []
    assert out['unresolved'][0]['summary_hits'][0]['verified'] is False


def test_failed_generation_keeps_previous_evidence(tmp_path):
    from test_search import indexed
    from robotlit.db import documents
    app = indexed(tmp_path)
    before = app.repo.rows(documents)[0]['active_generation_id']
    doc = app.repo.rows(documents)[0]
    Path(doc['blob_path']).chmod(0o644)
    Path(doc['blob_path']).write_bytes(b'%PDF corrupt')
    with pytest.raises(ValueError):
        app.ingestor.prepare(doc)
    assert app.repo.rows(documents)[0]['active_generation_id'] == before
