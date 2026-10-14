from test_search import make_app, write_pdf


def test_all_root_ingestion_status_and_repeated_index_reuse(tmp_path):
    from fastapi.testclient import TestClient
    from robotlit.api import create_app
    from robotlit.db import generations
    system=make_app(tmp_path)
    root=system.settings.source_roots['papers']
    (root/'second_lab'/'pdfs').mkdir(parents=True)
    for lab in ['lab','second_lab']:
        write_pdf(root/lab/'pdfs'/'one.pdf', f'The {lab} robot policy is unique.')
    with TestClient(create_app(system)) as client:
        request=client.post('/v1/ingest',json={'source_root':'papers'}).json()
        system.work_until_idle()
        result=client.get('/v1/ingest/'+request['run_id']).json()['result']
        assert result['inventoried']==2 and result['searchable']==2 and result['pending']==0
        count=len(system.repo.rows(generations))
        second=client.post('/v1/ingest',json={'source_root':'papers'}).json()
        system.work_until_idle()
        assert client.get('/v1/ingest/'+second['run_id']).json()['state']=='succeeded'
        assert len(system.repo.rows(generations))==count


def test_scanner_failure_remains_failed_when_progress_is_polled(tmp_path):
    from fastapi.testclient import TestClient
    from robotlit.api import create_app
    import shutil
    system=make_app(tmp_path)
    with TestClient(create_app(system)) as client:
        rid=client.post('/v1/ingest',json={'source_root':'papers'}).json()['run_id']
        shutil.rmtree(system.settings.source_roots['papers'])
        assert system.work_once()
        status=client.get('/v1/ingest/'+rid).json()
        assert status['state']=='failed'
        assert 'Source root does not exist' in status['error']


def test_rebuild_retries_failed_indexes(tmp_path, monkeypatch):
    from robotlit.db import jobs
    system=make_app(tmp_path)
    root=system.settings.source_roots['papers']
    write_pdf(root/'lab'/'pdfs'/'one.pdf', 'A robot learns a useful policy.')
    original=system.ingestor.prepare
    def fail(*args, **kwargs):
        raise ValueError('Temporary parser failure')
    monkeypatch.setattr(system.ingestor, 'prepare', fail)
    first=system.ingest('papers')
    system.work_until_idle()
    assert system.status(first)['state']=='partial'
    monkeypatch.setattr(system.ingestor, 'prepare', original)
    second=system.ingest('papers')
    system.work_until_idle()
    assert system.status(second)['state']=='succeeded'
    assert system.status(second)['result']['searchable']==1
    assert len(system.repo.rows(jobs))==1
