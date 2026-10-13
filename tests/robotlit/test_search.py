import hashlib
import json
from uuid import uuid4
import pytest


def make_app(tmp_path):
    from robotlit.service import LiteratureSystem
    from robotlit.config import Settings
    root=tmp_path/'labs'; (root/'lab'/'pdfs').mkdir(parents=True)
    return LiteratureSystem(Settings(source_roots={'papers':root},data_dir=tmp_path/'data',database_url=f'sqlite:///{tmp_path}/db.sqlite'))


def write_pdf(path, text):
    # Small valid native PDF, independent of parser implementation.
    escaped=text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
    stream=f'BT /F1 12 Tf 20 150 Td ({escaped}) Tj ET'.encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream']
    data=b'%PDF-1.4\n'; offsets=[0]
    for i,obj in enumerate(objects,1): offsets.append(len(data)); data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(data); data+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    data+=b''.join(f'{o:010} 00000 n \n'.encode() for o in offsets[1:])
    data+=f'trailer << /Root 1 0 R /Size {len(objects)+1} >>\nstartxref\n{xref}\n%%EOF'.encode(); path.write_bytes(data)


def indexed(tmp_path):
    app=make_app(tmp_path); root=app.settings.source_roots['papers']; p=root/'lab'/'pdfs'/'policy.pdf'
    write_pdf(p,'Our multi-view policy uses wrist RGB images without supplied extrinsics for inference.')
    (root/'lab'/'summary').mkdir(); (root/'lab'/'summary'/'policy.md').write_text('# Policy\nA bimanual dexterous VLA with world-action modeling. (unverified summary)')
    run=app.ingest('papers'); app.work_until_idle(); assert app.status(run)['state']=='succeeded'
    return app


def test_ingestion_is_searchable_and_summary_cannot_verify(tmp_path):
    from robotlit.contracts import SearchRequest
    app=indexed(tmp_path)
    out=app.run_search(SearchRequest(question='bimanual dexterous VLA'))
    assert not out['confirmed']
    assert out['unresolved']
    assert out['coverage']['searchable_documents']==1
    assert out['usage']['cloud_calls']==0
    block=out['unresolved'][0]['source_passages'][0]
    assert app.evidence.resolve(block)['text']


def test_grounding_rejects_wrong_page_offsets_and_summary(tmp_path):
    app=indexed(tmp_path)
    from robotlit.db import blocks
    b=app.repo.rows(blocks)[0]; ref={k:b[k] for k in ['document_id','generation_id','block_id','pdf_page','bbox','content_sha256']}
    assert app.evidence.resolve(ref)['text'].startswith('Our')
    for invalid in [{**ref,'pdf_page':2},{**ref,'char_end':999999},{**ref,'content_sha256':'bad'}]:
        with pytest.raises(ValueError): app.evidence.resolve(invalid)


def test_configuration_properties_cannot_be_combined(tmp_path):
    from robotlit.contracts import PaperFactBatch, MethodConfig, FacetAssertion, QueryPlan, Predicate, SearchRequest
    app=indexed(tmp_path)
    from robotlit.db import blocks
    b=app.repo.rows(blocks)[0]; ref=app.evidence.ref(b)
    c1=MethodConfig(document_id=b['document_id'],label='single arm',identity_evidence=[ref]); c2=MethodConfig(document_id=b['document_id'],label='two arms',identity_evidence=[ref])
    batch=PaperFactBatch(configs=[c1,c2],assertions=[FacetAssertion(config_id=c1.config_id,facet='policy.multiview_input',value=True,evidence_refs=[ref],evidence_status='supported'),FacetAssertion(config_id=c2.config_id,facet='camera.extrinsics_supplied_infer',value=False,evidence_refs=[ref],evidence_status='supported')])
    app.evidence.publish_facts(batch)
    plan=QueryPlan(search_queries=['policy'],hard_requirements=[Predicate(id='a',facet='policy.multiview_input',operator='eq',value=True),Predicate(id='b',facet='camera.extrinsics_supplied_infer',operator='eq',value=False)])
    out=app.run_search(SearchRequest(plan=plan)); assert not out['confirmed']
    assert len(out['unresolved'][0]['configurations'])==2


def test_correction_is_append_only_and_old_snapshot_still_resolves(tmp_path):
    from robotlit.contracts import PaperFactBatch, MethodConfig, FacetAssertion
    from robotlit.db import blocks
    app=indexed(tmp_path); b=app.repo.rows(blocks)[0]; ref=app.evidence.ref(b)
    config=MethodConfig(document_id=b['document_id'],label='main',identity_evidence=[ref])
    a=FacetAssertion(config_id=config.config_id,facet='policy.multiview_input',value=True,evidence_refs=[ref],evidence_status='supported')
    app.evidence.publish_facts(PaperFactBatch(configs=[config],assertions=[a])); snap=app.repo.corpus_snapshot()
    app.evidence.correct(str(a.assertion_id),False,[ref],'manual review')
    assert app.repo.config_assertions(config.config_id)[0]['value'] is False
    assert app.repo.config_assertions(config.config_id,snap['assertion_watermark'])[0]['value'] is True


def test_collection_resume_keeps_snapshot(tmp_path):
    from robotlit.contracts import SearchRequest, QueryPlan, Budget
    app=indexed(tmp_path)
    p=app.settings.source_roots['papers']/'lab'/'pdfs'/'other.pdf'; write_pdf(p,'A second multi-view manipulation policy with RGB and depth observations.')
    app.ingest('papers'); app.work_until_idle()
    out=app.run_search(SearchRequest(plan=QueryPlan(mode='collection_review',search_queries=['policy']),mode='collection_review',budgets=Budget(max_documents=1,max_cloud_calls=0)))
    assert out['resume_token'] and out['coverage']['documents_in_snapshot']==2
    p=p.with_name('new.pdf'); write_pdf(p,'A newly added policy is not in the saved review snapshot.')
    app.ingest('papers'); app.work_until_idle()
    resumed=app.run_search(SearchRequest(resume_token=out['resume_token']))
    assert resumed['snapshot']==out['snapshot']
    assert resumed['coverage']['documents_in_snapshot']==2
    assert resumed['coverage']['documents_evaluated']==2


def test_cloud_budget_counts_failed_attempts():
    from robotlit.llm import Gateway, BudgetExceeded
    from robotlit.contracts import Budget
    def fail(*args): raise TimeoutError('uncertain billing')
    g=Gateway(provider=fail,budget=Budget(max_cloud_calls=2))
    for _ in range(2):
        with pytest.raises(TimeoutError): g.generate('task',{'evidence':[]},100)
    with pytest.raises(BudgetExceeded): g.generate('task',{},100)
    assert g.usage['cloud_calls']==2
    assert g.usage['possibly_billed_attempts']==2


def test_api_async_export_source_and_traversal(tmp_path):
    from robotlit.api import create_app
    from fastapi.testclient import TestClient
    app=indexed(tmp_path)
    with TestClient(create_app(app)) as client:
        response=client.post('/v1/search',json={'question':'multi-view policy'})
        assert response.status_code==202
        rid=response.json()['run_id']; app.work_until_idle()
        result=client.get(f'/v1/search/{rid}').json()
        assert result['state']=='succeeded' and result['result']['unresolved']
        events=client.get(f'/v1/search/{rid}/events',headers={'Last-Event-ID':'0'})
        assert 'event: progress' in events.text
        exported=client.get(f'/v1/search/{rid}/export?format=markdown'); assert 'Coverage' in exported.text
        assert client.get('/v1/documents/../../etc/passwd/pdf').status_code==404
        ref=result['result']['unresolved'][0]['source_passages'][0]
        assert client.get(f'/v1/evidence/{ref["block_id"]}').json()['source_url'].endswith('#page=1')
