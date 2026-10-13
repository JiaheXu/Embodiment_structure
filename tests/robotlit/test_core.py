from pathlib import Path
from uuid import uuid4
import pytest


def test_duplicate_and_changed_source_keeps_snapshot(tmp_path):
    from robotlit.config import Settings
    from robotlit.db import Repository
    from robotlit.ingest import Ingestor
    root = tmp_path / 'labs'; (root / '实验室' / 'pdfs').mkdir(parents=True)
    a = root / '实验室' / 'pdfs' / 'paper with spaces.pdf'; a.write_bytes(b'%PDF-one')
    b = a.with_name('alias.pdf'); b.write_bytes(a.read_bytes())
    repo = Repository(f'sqlite:///{tmp_path}/db.sqlite'); repo.initialize()
    ing = Ingestor(repo, Settings(source_roots={'papers': root}, data_dir=tmp_path/'data'))
    sources = ing.inventory('papers')
    d1 = ing.snapshot(sources[0]); d2 = ing.snapshot(sources[1])
    assert d1.document_id == d2.document_id
    a.write_bytes(b'%PDF-two')
    d3 = ing.snapshot(next(s for s in ing.inventory('papers') if s.path == a))
    assert d3.document_id != d1.document_id
    assert Path(d1.blob_path).read_bytes() == b'%PDF-one'
    assert a.read_bytes() == b'%PDF-two'


def test_expired_worker_cannot_publish(tmp_path):
    from robotlit.db import Repository
    from robotlit.jobs import Queue
    now = [1000.0]
    repo = Repository(f'sqlite:///{tmp_path}/db.sqlite'); repo.initialize()
    queue = Queue(repo, clock=lambda: now[0], lease_seconds=10)
    jid = queue.enqueue('search', 'one', {'x': 1})
    old = queue.claim_job('w1', ['search']); now[0] += 11
    new = queue.claim_job('w2', ['search'])
    assert new.fence > old.fence
    assert not queue.complete_job(old, {'answer': 'stale'})
    assert queue.complete_job(new, {'answer': 'fresh'})
    assert queue.get(jid)['result']['answer'] == 'fresh'


def test_retry_exhaustion_is_visible(tmp_path):
    from robotlit.db import Repository
    from robotlit.jobs import Queue
    repo = Repository(f'sqlite:///{tmp_path}/db.sqlite'); repo.initialize()
    now = [1000.0]; q = Queue(repo, clock=lambda: now[0])
    jid = q.enqueue('parse', 'bad', {})
    for _ in range(3):
        lease = q.claim_job('w', ['parse']); assert lease
        q.fail_job(lease, 'corrupt PDF'); now[0] += 1000
    assert q.claim_job('w', ['parse']) is None
    assert q.get(jid)['state'] == 'failed'


def test_false_requirement_missing_is_unknown():
    from robotlit.contracts import Predicate, FacetAssertion
    from robotlit.facts import evaluate_predicate, classify
    p = Predicate(id='r', facet='camera.extrinsics_supplied_infer', operator='eq', value=False)
    assert evaluate_predicate(p, []).outcome == 'unknown'
    a = FacetAssertion(config_id=uuid4(), facet=p.facet, value=False, evidence_refs=[], evidence_status='insufficient')
    assert evaluate_predicate(p, [a]).outcome == 'unknown'
    assert classify(['satisfied','unknown']) == 'unresolved'
    assert classify(['satisfied','contradicted']) == 'partial'
    assert classify([]) == 'discovery_only'


def test_registry_rejects_invented_fields_and_wrong_types():
    from robotlit.contracts import Predicate, RecordRequirement
    with pytest.raises(ValueError):
        Predicate(id='a', facet='execute.shell', operator='eq', value=True)
    with pytest.raises(ValueError):
        Predicate(id='a', facet='policy.multiview_input', operator='gte', value=True)
    with pytest.raises(ValueError):
        Predicate(id='a', facet='policy.view_count_min', operator='gte', value=True)
    with pytest.raises(ValueError):
        RecordRequirement(id='r', record_type='reported_result', filters=[{'field':'protocol.arbitrary.sql','operator':'eq','value':'x'}])


def test_record_groups_cannot_mix_rows():
    from robotlit.contracts import RecordRequirement
    from robotlit.facts import evaluate_record_requirement
    p = RecordRequirement(id='r', record_type='reported_result', filters=[
        {'field':'protocol.benchmark','operator':'eq','value':'X'},
        {'field':'normalized_value','operator':'gte','value':0.8,'unit':'fraction'}])
    rows = [{'fields': {'protocol.benchmark': {'value':'X','value_state':'known','evidence_status':'supported'}, 'normalized_value': {'value':0.5,'unit':'fraction','value_state':'known','evidence_status':'supported'}}},
            {'fields': {'protocol.benchmark': {'value':'Y','value_state':'known','evidence_status':'supported'}, 'normalized_value': {'value':0.9,'unit':'fraction','value_state':'known','evidence_status':'supported'}}}]
    assert evaluate_record_requirement(p, rows).outcome == 'unknown'
    assert evaluate_record_requirement(p, rows, complete_inventory=True).outcome == 'contradicted'
    assert evaluate_record_requirement(p, []).outcome == 'unknown'


def test_percent_conversion_never_invents_counts():
    from robotlit.facts import normalize_number
    assert normalize_number(85, 'percent', 'fraction') == (0.85, {'formula':'value / 100','from_unit':'percent','to_unit':'fraction'})
    with pytest.raises(ValueError): normalize_number(50, 'demonstrations', 'transitions')


def test_comparison_requires_protocol_and_keeps_mismatches():
    from robotlit.facts import assess_comparison
    a = {'metric_name':'success_rate','unit':'fraction','aggregation':'pooled_trials','protocol': {'benchmark':'X','tasks':['A'],'split':'test','robot':'real','success_definition':'completed','execution':'20 trials'}}
    b = {**a, 'protocol': {**a['protocol'], 'robot':'sim'}}
    assert assess_comparison([a,b])['outcome'] == 'incomparable'
    assert assess_comparison([a,{}])['outcome'] == 'insufficient_context'


def test_project_versions_and_observations_separate(tmp_path):
    from robotlit.db import Repository
    repo = Repository(f'sqlite:///{tmp_path}/db.sqlite'); repo.initialize()
    p = repo.create_project({'goals':['grasp'],'robot':None})
    repo.update_project(p['project_id'], 1, {'goals':['grasp'],'robot':'x'})
    with pytest.raises(ValueError): repo.update_project(p['project_id'], 1, {})
    e = repo.add_experiment({'project_id':p['project_id'],'project_version':1,'observations':'slipped','interpretation':'occlusion','hypothesis':'more views help'})
    assert e['observations'] == 'slipped' and e['interpretation'] == 'occlusion'
    assert repo.project(p['project_id'], 1)['profile']['robot'] is None
