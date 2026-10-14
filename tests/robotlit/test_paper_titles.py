import json
from test_search import make_app, write_pdf


def test_video_caption_is_replaced_and_existing_index_titles_refresh(tmp_path):
    from robotlit.db import papers, chunks, summaries
    system=make_app(tmp_path)
    root=system.settings.source_roots['papers']
    pdf=root/'lab'/'pdfs'/'2023-affordance-diffusion-synthesizing-hand-object-interactions.pdf'
    title='Affordance Diffusion: Synthesizing Hand-Object Interactions'
    write_pdf(pdf, title)
    (root/'lab'/'papers.json').write_text(json.dumps([{'pdf_path':'pdfs/'+pdf.name,'title':'中文视频标题','page_url':'https://www.bilibili.com/video/test','pdf_url':'https://arxiv.org/pdf/2303.12538.pdf'}]))
    summary=root/'lab'/'summary';summary.mkdir()
    (summary/(pdf.stem+'.md')).write_text('# 中文视频标题\n\nSummary of hand-object interactions.')
    source=system.ingestor.inventory('papers')[0]
    assert source.title==title
    run=system.ingest('papers');system.work_until_idle()
    assert system.status(run)['state']=='succeeded'
    with system.repo.write() as conn:
        conn.execute(papers.update().values(title='中文视频标题'))
        conn.execute(chunks.update().values(title='中文视频标题'))
    again=system.ingest('papers');system.work_until_idle()
    assert system.status(again)['state']=='succeeded'
    assert {r['title'] for r in system.repo.rows(papers)}=={title}
    assert {r['title'] for r in system.repo.rows(chunks)}=={title}
    assert {r['title'] for r in system.repo.rows(summaries)}=={title}


def test_title_key_ignores_year_punctuation_and_case():
    from robotlit.titles import paper_key
    expected='affordance-diffusion-synthesizing-hand-object-interactions'
    assert paper_key('Affordance Diffusion: Synthesizing Hand-Object Interactions')==expected
    assert paper_key(expected)==expected


def test_running_search_sees_ingestion_and_reloaded_catalog(tmp_path):
    from robotlit.contracts import QueryPlan
    system=make_app(tmp_path)
    assert not system.repo.corpus_snapshot()['documents']
    pdf=system.settings.source_roots['papers']/'lab'/'pdfs'/'policy.pdf'
    write_pdf(pdf,'A unique robot policy involving a wrist camera.')
    run=system.ingest('papers');system.work_until_idle()
    assert system.status(run)['state']=='succeeded'
    catalog=json.loads((system.settings.data_dir/'catalog.json').read_text())
    assert catalog['documents'][0]['paper_key']=='policy'
    assert system.retriever.retrieve(QueryPlan(search_queries=['wrist']),system.repo.corpus_snapshot())


def test_pdf_title_skips_rotated_arxiv_stamp_and_joins_title_lines(monkeypatch):
    from robotlit.titles import pdf_title
    from types import SimpleNamespace
    xml=b'''<html><page width="600" height="800">
    <word xMin="18" xMax="36" yMin="120" yMax="190">[cs.RO]</word>
    <word xMin="60" xMax="240" yMin="80" yMax="100">Affordance Diffusion:</word>
    <word xMin="60" xMax="350" yMin="104" yMax="124">Synthesizing Hand-Object Interactions</word>
    <word xMin="60" xMax="150" yMin="140" yMax="150">First Author</word>
    </page></html>'''
    monkeypatch.setattr('robotlit.titles.subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=xml))
    assert pdf_title('paper.pdf')=='Affordance Diffusion: Synthesizing Hand-Object Interactions'


def test_matching_paper_record_overrides_video_caption_and_filename(tmp_path):
    system=make_app(tmp_path)
    root=system.settings.source_roots['papers']
    (root/'academic').mkdir()
    title='Affordance Diffusion: Synthesizing Hand-Object Interactions'
    (root/'academic'/'papers.json').write_text(json.dumps([{'pdf_path':'pdfs/paper.pdf','title':title,'pdf_url':'https://arxiv.org/pdf/2303.12538v3.pdf'}]))
    pdf=root/'lab'/'pdfs'/'2023-video-caption.pdf';write_pdf(pdf,'Anonymous document text without a real title.')
    (root/'lab'/'papers.json').write_text(json.dumps([{'pdf_path':'pdfs/'+pdf.name,'title':'视频介绍','page_url':'https://bilibili.com/video/test','pdf_url':'https://arxiv.org/pdf/2303.12538.pdf'}]))
    assert system.ingestor.inventory('papers')[0].title==title


def test_filename_alias_cannot_replace_canonical_title(tmp_path):
    from robotlit.db import papers, chunks
    system=make_app(tmp_path)
    root=system.settings.source_roots['papers']
    pdf=root/'lab'/'pdfs'/'paper.pdf';write_pdf(pdf,'Robot paper contents.')
    (root/'lab'/'papers.json').write_text(json.dumps([{'pdf_path':'pdfs/paper.pdf','title':'Accurate Robotic Paper Title'}]))
    system.ingest('papers');system.work_until_idle()
    (pdf.parent/'z-backup.pdf').write_bytes(pdf.read_bytes())
    system.ingest('papers');system.work_until_idle()
    assert {row['title'] for row in system.repo.rows(papers)}=={'Accurate Robotic Paper Title'}
    assert {row['title'] for row in system.repo.rows(chunks)}=={'Accurate Robotic Paper Title'}


def test_catalog_failure_does_not_stop_worker_and_status_retries(tmp_path):
    system=make_app(tmp_path)
    pdf=system.settings.source_roots['papers']/'lab'/'pdfs'/'policy.pdf'
    write_pdf(pdf,'A robot policy is published.')
    catalog=system.settings.data_dir/'catalog.json';catalog.mkdir()
    run=system.ingest('papers');system.work_until_idle()
    failed_reload=system.status(run)
    assert failed_reload['state']=='succeeded'
    assert failed_reload['result']['reload_error']
    catalog.rmdir()
    recovered=system.status(run)
    assert 'reload_error' not in recovered['result']
    assert catalog.is_file()


def test_reviewed_paper_title_overrides_video_caption_and_pdf_heading(tmp_path):
    system = make_app(tmp_path)
    root = system.settings.source_roots['papers']
    pdf = root/'lab'/'pdfs'/'palm-e.pdf'
    write_pdf(pdf, 'A misleading figure heading')
    canonical = 'PaLM-E: An Embodied Multimodal Language Model'
    (root/'lab'/'papers.json').write_text(json.dumps([{
        'title': 'Video caption', 'paper_title': canonical,
        'page_url': 'https://www.bilibili.com/video/BVtest',
        'pdf_path': 'pdfs/palm-e.pdf', 'pdf_url': 'https://arxiv.org/pdf/2303.03378.pdf',
    }]))
    assert system.ingestor.inventory('papers')[0].title == canonical
