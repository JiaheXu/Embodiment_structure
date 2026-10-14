import json

import pytest

from test_search import indexed, make_app


def test_conflicting_facts_never_satisfy_negative(tmp_path):
    from robotlit.contracts import FacetAssertion, MethodConfig, PaperFactBatch, Predicate
    from robotlit.db import blocks
    from robotlit.facts import evaluate_predicate
    app = indexed(tmp_path)
    block = app.repo.rows(blocks)[0]
    ref = app.evidence.ref(block)
    config = MethodConfig(document_id=block['document_id'], label='main', identity_evidence=[ref])
    values = [FacetAssertion(config_id=config.config_id, facet='camera.extrinsics_supplied_infer', value=v,
                            evidence_refs=[ref], evidence_status='supported') for v in (True, False)]
    app.evidence.publish_facts(PaperFactBatch(configs=[config], assertions=values))
    p = Predicate(id='negative', facet='camera.extrinsics_supplied_infer', operator='eq', value=False)
    assert evaluate_predicate(p, app.repo.config_assertions(config.config_id)).outcome == 'conflicted'


def test_reject_cross_document_assertion_transaction(tmp_path):
    from robotlit.contracts import FacetAssertion, MethodConfig, PaperFactBatch
    from robotlit.db import blocks, configs
    from test_search import write_pdf
    app = indexed(tmp_path)
    write_pdf(app.settings.source_roots['papers'] / 'lab' / 'pdfs' / 'two.pdf', 'Another policy in a different paper')
    app.ingest('papers'); app.work_until_idle()
    a, b = app.repo.rows(blocks)
    config = MethodConfig(document_id=a['document_id'], label='main', identity_evidence=[app.evidence.ref(a)])
    assertion = FacetAssertion(config_id=config.config_id, facet='policy.multiview_input', value=True,
                               evidence_refs=[app.evidence.ref(b)], evidence_status='supported')
    with pytest.raises(ValueError):
        app.evidence.publish_facts(PaperFactBatch(configs=[config], assertions=[assertion]))
    assert app.repo.rows(configs) == []


def test_record_revision_snapshot_retains_unknown_fields(tmp_path):
    from robotlit.contracts import MethodConfig, PaperFactBatch, StructuredRecord
    from robotlit.db import blocks
    app = indexed(tmp_path)
    block = app.repo.rows(blocks)[0]; ref = app.evidence.ref(block)
    config = MethodConfig(document_id=block['document_id'], label='main', identity_evidence=[ref])
    record = StructuredRecord(config_id=config.config_id, record_type='output_stream', fields={
        'phase': {'value': 'inference', 'value_state': 'known', 'evidence_status': 'supported', 'evidence_refs': [ref]},
        'dimension': {'value_state': 'unknown', 'unknown_reason': 'not_found_in_reviewed_scope'}})
    app.evidence.publish_facts(PaperFactBatch(configs=[config], records=[record]))
    snapshot = app.repo.corpus_snapshot()
    app.evidence.correct_record(str(record.record_id), {'dimension': {'value': 7, 'value_state': 'known', 'evidence_status': 'supported', 'evidence_refs': [ref]}}, 'Human reviewed dimensions')
    assert app.repo.config_records(config.config_id, snapshot['assertion_watermark'])[0]['fields']['dimension']['value'] is None
    assert app.repo.config_records(config.config_id)[0]['fields']['dimension']['value'] == 7


def test_record_only_plan_is_verified_against_one_row(tmp_path):
    from robotlit.contracts import MethodConfig, PaperFactBatch, StructuredRecord, SearchRequest, QueryPlan
    from robotlit.db import blocks
    app = indexed(tmp_path); b = app.repo.rows(blocks)[0]; ref = app.evidence.ref(b)
    c = MethodConfig(document_id=b['document_id'], label='main', identity_evidence=[ref])
    def field(value):
        return {'value':value, 'value_state':'known', 'evidence_status':'supported', 'evidence_refs':[ref]}
    r = StructuredRecord(config_id=c.config_id, record_type='artifact_mention', fields={'kind':field('code'), 'availability_state':field('reported_available')})
    app.evidence.publish_facts(PaperFactBatch(configs=[c], records=[r]))
    out = app.run_search(SearchRequest(plan=QueryPlan(search_queries=['policy'], record_requirements=[{'id':'weights','record_type':'artifact_mention','filters':[{'field':'kind','operator':'eq','value':'checkpoint'}]}])))
    assert not out['confirmed'] and not out['discovery_only']
    assert out['unresolved'][0]['configurations'][0]['record_judgments'][0]['outcome'] == 'unknown'


def test_expired_publication_callback_never_runs(tmp_path):
    from robotlit.db import Repository
    from robotlit.jobs import Queue
    now = [1000]
    repo = Repository(f'sqlite:///{tmp_path}/db'); repo.initialize()
    q = Queue(repo, clock=lambda:now[0], lease_seconds=1)
    q.enqueue('index', 'one', {})
    lease = q.claim_job('old', ['index']); now[0] += 2
    published = []
    assert not q.complete_job(lease, {}, lambda c:published.append(True))
    assert published == []


def test_api_ingest_returns_queue_then_progress(tmp_path):
    from fastapi.testclient import TestClient
    from robotlit.api import create_app
    from test_search import write_pdf
    app = make_app(tmp_path)
    write_pdf(app.settings.source_roots['papers'] / 'lab' / 'pdfs' / 'one.pdf', 'A camera policy')
    with TestClient(create_app(app)) as client:
        r = client.post('/v1/ingest', json={'source_root':'papers'})
        assert r.status_code == 202
        rid = r.json()['run_id']
        assert client.get('/v1/ingest/'+rid).json()['state'] == 'queued'
        app.work_until_idle()
        assert client.get('/v1/ingest/'+rid).json()['result']['searchable'] == 1
        assert client.post('/v1/projects', headers={'Origin':'https://evil.invalid'}, json={}).status_code == 403


def test_cli_search_and_export_without_cloud(tmp_path, capsys):
    from robotlit.cli import main
    import yaml
    root = tmp_path / 'labs'; root.mkdir()
    config = tmp_path / 'settings.yaml'
    config.write_text(yaml.safe_dump({'source_roots':{'papers':str(root)}, 'data_dir':str(tmp_path/'data'), 'database_url':f'sqlite:///{tmp_path}/db'}))
    assert main(['--config', str(config), 'search', 'WAM', '--format', 'markdown']) == 0
    text = capsys.readouterr().out
    assert 'world-action model' in text and 'Coverage' in text


def test_cloud_disabled_preserves_memory_and_defers_advice(tmp_path):
    app = make_app(tmp_path)
    p = app.repo.create_project({'goals':['grasp'], 'robot':None})
    r = app.submit_advice('How can I improve grasping?', p['project_id'])
    assert app.status(r)['state'] == 'deferred'


def test_advice_drops_published_claim_without_semantic_support(tmp_path):
    app = indexed(tmp_path)
    from robotlit.db import blocks
    ref = app.evidence.ref(app.repo.rows(blocks)[0])
    def provider(task, packet, limit):
        if task == 'review_advice':
            return {'supported_claim_indices':[]}
        return {'claims':[{'claim_type':'published_finding', 'text':'This policy controls two dexterous hands', 'evidence_refs':[ref]}], 'proposed_experiments':[{'hypothesis':'try another view'}]}
    app.provider = provider
    p = app.repo.create_project({'goals':['grasp']})
    out = app.run_advice('policy', p['project_id'])
    assert not [c for c in out['claims'] if c['claim_type'] == 'published_finding']
    assert out['proposed_experiments'][0]['status'] == 'untested'


def test_gateway_records_actual_usage(tmp_path):
    from robotlit.llm import Gateway
    g = Gateway(provider=lambda *args:{'output':{}, 'usage':{'prompt_tokens':7,'completion_tokens':3}})
    g.generate('task', {'evidence':[]}, 100)
    assert g.usage['provider_input_tokens'] == 7
    assert g.usage['provider_output_tokens'] == 3


def test_backup_restored_citation_resolves(tmp_path):
    from robotlit.backup import backup, restore
    from robotlit.config import Settings
    from robotlit.service import LiteratureSystem
    from robotlit.db import blocks
    app = indexed(tmp_path)
    ref = app.evidence.ref(app.repo.rows(blocks)[0])
    destination = tmp_path / 'backup'
    backup(app, destination)
    target = Settings(source_roots={'papers':app.settings.source_roots['papers']},data_dir=tmp_path/'restored', database_url=f'sqlite:///{tmp_path}/restored/catalog.sqlite')
    restore(destination, target)
    restored = LiteratureSystem(target)
    assert restored.evidence.resolve(ref)['text'] == app.evidence.resolve(ref)['text']
