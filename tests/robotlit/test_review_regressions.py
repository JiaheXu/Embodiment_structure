import json
from pathlib import Path

import pytest

from test_search import indexed, make_app


def test_expired_search_run_recovers_terminal_status(tmp_path):
    from robotlit.contracts import SearchRequest
    from robotlit.db import jobs
    app = make_app(tmp_path)
    rid = app.submit_search(SearchRequest(question='policy'))
    with app.repo.write() as conn:
        conn.execute(jobs.update().where(jobs.c.key == rid).values(state='running', attempt=3, lease_until=0))
    app.work_once()
    assert app.status(rid)['state'] == 'failed'


def test_expired_ingest_cannot_publish_child_jobs_or_run(tmp_path):
    from robotlit.db import jobs
    from test_search import write_pdf
    app = make_app(tmp_path)
    write_pdf(app.settings.source_roots['papers']/'lab'/'pdfs'/'one.pdf','A camera policy')
    rid = app.submit_ingest('papers')
    now = [1000.0]; app.queue.clock = lambda:now[0]
    original = app.ingestor.snapshot
    def expire(source):
        result = original(source); now[0] += 1000
        return result
    app.ingestor.snapshot = expire
    app.work_once()
    assert not app.repo.rows(jobs, jobs.c.stage == 'index')
    assert app.repo.one(__import__('robotlit.db',fromlist=['runs']).runs, __import__('robotlit.db',fromlist=['runs']).runs.c.run_id==rid)['state'] == 'queued'


def test_cloud_budget_is_durable_across_gateway_restarts(tmp_path):
    from robotlit.llm import Gateway, BudgetExceeded
    from robotlit.contracts import Budget
    app = make_app(tmp_path)
    def timeout(*args):
        raise TimeoutError('uncertain billing')
    budget = Budget(max_cloud_calls=1)
    first = Gateway(provider=timeout,budget=budget,repo=app.repo,scope_key='job-test')
    with pytest.raises(TimeoutError): first.generate('extract', {'evidence':[]},100)
    restarted = Gateway(provider=timeout,budget=budget,repo=app.repo,scope_key='job-test')
    with pytest.raises(BudgetExceeded): restarted.generate('extract', {'evidence':[]},100)
    assert restarted.usage['possibly_billed_attempts']==1


def test_unseen_suffix_cannot_be_cited_when_end_is_omitted(tmp_path):
    from robotlit.db import blocks
    from robotlit.contracts import Budget
    app = indexed(tmp_path); block=app.repo.rows(blocks)[0]
    long_text = 'Visible introduction. ' * 900 + 'UNSEEN SUFFIX'
    import hashlib
    with app.repo.write() as conn:
        conn.execute(blocks.update().where(blocks.c.block_id == block['block_id']).values(text=long_text,content_sha256=hashlib.sha256(long_text.encode()).hexdigest()))
    def provider(task,packet,limit):
        if task=='extract':
            ref={k:v for k,v in packet['untrusted_evidence'][0].items() if k in __import__('robotlit.contracts',fromlist=['EvidenceRef']).EvidenceRef.model_fields}
            ref['char_end']=None
            return {'configs':[{'document_id':block['document_id'],'label':'main','identity_evidence':[ref]}]}
        return packet['batch']
    app.provider=provider
    with pytest.raises(ValueError,match='uninspected'):
        app.prepare_enrichment(block['document_id'],Budget(max_input_tokens=200000))


def test_benchmark_version_difference_is_incomparable():
    from robotlit.facts import assess_comparison
    a={'metric_name':'success','unit':'fraction','aggregation':'pooled_trials','protocol':{'benchmark':'X','version':'1','tasks':['A'],'split':'test','robot':'real','success_definition':'complete','execution':'20 trials'}}
    b={**a,'protocol':{**a['protocol'],'version':'2'}}
    assert assess_comparison([a,b])['outcome']=='incomparable'


def test_advice_cloud_packet_has_only_relevant_allowlisted_context(tmp_path):
    app=indexed(tmp_path)
    p=app.repo.create_project({'goals':['grasp'],'robot':'arm','local_path':'/private/project','unrelated_secret':'secret'})
    app.repo.add_experiment({'project_id':p['project_id'],'project_version':1,'observations':'camera occlusion','interpretation':'view blocked','artifact_refs':['/private/run.png']})
    app.repo.add_experiment({'project_id':p['project_id'],'project_version':1,'observations':'UNRELATED walking','artifact_refs':['/private/unrelated']})
    captured=[]
    def provider(task,packet,limit):
        captured.append(packet)
        return {'claims':[],'proposed_experiments':[]}
    app.provider=provider
    app.run_advice('camera occlusion policy',p['project_id'])
    packet=json.dumps(captured)
    assert '/private/' not in packet
    assert 'UNRELATED' not in packet
    assert 'camera occlusion' in packet
    assert 'unrelated_secret' not in packet


def test_cli_restore_does_not_initialize_target_first(tmp_path,capsys):
    from robotlit.backup import backup
    from robotlit.cli import main
    import yaml
    app=indexed(tmp_path)
    backup(app,tmp_path/'backup')
    config=tmp_path/'target.yaml'
    config.write_text(yaml.safe_dump({'source_roots':{'papers':str(app.settings.source_roots['papers'])},'data_dir':str(tmp_path/'restored'),'database_url':f'sqlite:///{tmp_path}/restored/catalog.sqlite'}))
    assert main(['--config',str(config),'restore','--directory',str(tmp_path/'backup')])==0


def test_database_cannot_write_into_readonly_source_root(tmp_path):
    from robotlit.config import Settings
    root=tmp_path/'labs';root.mkdir()
    with pytest.raises(ValueError,match='source'):
        Settings(source_roots={'papers':root},data_dir=tmp_path/'data',database_url=f'sqlite:///{root}/catalog.sqlite')


def test_restored_pending_ingestion_uses_restored_blob_path(tmp_path):
    from robotlit.backup import backup,restore
    from robotlit.service import LiteratureSystem
    from robotlit.config import Settings
    from test_search import write_pdf
    import shutil
    app=make_app(tmp_path)
    write_pdf(app.settings.source_roots['papers']/'lab'/'pdfs'/'one.pdf','A camera policy')
    rid=app.ingest('papers')
    backup(app,tmp_path/'backup')
    target=Settings(source_roots=app.settings.source_roots,data_dir=tmp_path/'restored',database_url=f'sqlite:///{tmp_path}/restored/catalog.sqlite')
    restore(tmp_path/'backup',target)
    shutil.rmtree(app.settings.data_dir)
    restored=LiteratureSystem(target);restored.work_until_idle()
    assert restored.status(rid)['state']=='succeeded'


def test_api_rejects_dns_rebinding_host(tmp_path):
    from fastapi.testclient import TestClient
    from robotlit.api import create_app
    app=make_app(tmp_path)
    with TestClient(create_app(app)) as client:
        r=client.post('/v1/projects',headers={'Host':'evil.example','Origin':'http://evil.example'},json={})
        assert r.status_code==400


def test_comparison_obeys_config_selection(tmp_path):
    from robotlit.contracts import MethodConfig,PaperFactBatch,StructuredRecord,QueryPlan,SearchRequest
    from robotlit.db import blocks
    app=indexed(tmp_path);b=app.repo.rows(blocks)[0];ref=app.evidence.ref(b)
    c1=MethodConfig(document_id=b['document_id'],label='selected',identity_evidence=[ref])
    c2=MethodConfig(document_id=b['document_id'],label='unselected',identity_evidence=[ref])
    def field(v):return {'value':v,'value_state':'known','evidence_status':'supported','evidence_refs':[ref]}
    records=[StructuredRecord(config_id=c.config_id,record_type='reported_result',fields={'metric_name':field('success_rate')}) for c in [c1,c2]]
    app.evidence.publish_facts(PaperFactBatch(configs=[c1,c2],records=records))
    out=app.run_search(SearchRequest(plan=QueryPlan(search_queries=['policy'],comparison_request={'config_ids':[str(c1.config_id)]})))
    assert len(out['comparison']['results'])==1
    assert out['comparison']['results'][0]['config_id']==str(c1.config_id)


def test_embedding_revision_mismatch_rejected_before_model_load(tmp_path):
    from robotlit.contracts import QueryPlan
    app=indexed(tmp_path)
    app.settings.retrieval='bge';app.settings.embedding_revision='a'*40
    with pytest.raises(ValueError,match='revision mismatch'):
        app.retriever.retrieve(QueryPlan(search_queries=['policy']),app.repo.corpus_snapshot())


def test_reranker_score_controls_document_selection(tmp_path):
    from robotlit.contracts import SearchRequest,QueryPlan,Budget
    from robotlit.db import documents
    from test_search import write_pdf
    app=indexed(tmp_path)
    write_pdf(app.settings.source_roots['papers']/'lab'/'pdfs'/'second.pdf','A second robot policy')
    app.ingest('papers');app.work_until_idle()
    first,second=app.repo.rows(documents)
    app.retriever.retrieve=lambda plan,snapshot:[{'channel':'pdf','document_id':first['document_id'],'rrf_score':100,'reranker_score':-5,'channels':[],'spans':[]},
                                              {'channel':'pdf','document_id':second['document_id'],'rrf_score':1,'reranker_score':5,'channels':[],'spans':[]}]
    out=app.run_search(SearchRequest(plan=QueryPlan(search_queries=['policy']),budgets=Budget(max_documents=1)))
    assert out['discovery_only'][0]['document_id']==second['document_id']


def test_known_metric_definition_mismatch_is_incomparable():
    from robotlit.facts import assess_comparison
    a={'metric_name':'score','metric_definition':'mean task success','unit':'fraction','aggregation':'pooled_trials','protocol':{'benchmark':'X','tasks':['A'],'split':'test','robot':'real','success_definition':'complete','execution':'20 trials'}}
    b={**a,'metric_definition':'maximum task success'}
    assert assess_comparison([a,b])['outcome']=='incomparable'


def test_nested_local_paths_are_redacted_in_cloud_context(tmp_path):
    app=indexed(tmp_path)
    p=app.repo.create_project({'goals':['grasp'],'observations':{'notes':'camera logs are /home/me/private/log.csv'}})
    packets=[]
    app.provider=lambda task,packet,limit:(packets.append(packet) or {'claims':[],'proposed_experiments':[]})
    app.run_advice('policy',p['project_id'])
    assert '/home/me/' not in json.dumps(packets)
