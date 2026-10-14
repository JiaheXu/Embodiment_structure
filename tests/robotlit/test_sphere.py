from test_search import indexed


def test_sphere_catalog_preserves_source_identity_and_summary_status(tmp_path):
    from robotlit.sphere import build_sphere
    app = indexed(tmp_path)
    graph = build_sphere(app.repo)
    assert graph['nodes'] and graph['groups']
    assert graph['clustering']['verified'] is False
    ids = [n['id'] for n in graph['nodes']]
    assert len(ids) == len(set(ids))
    paper = next(n for n in graph['nodes'] if n['document_id'])
    assert paper['source_url'].startswith('/v1/documents/')
    assert paper['summary_verified'] is False
    assert paper['group_id'] in {g['id'] for g in graph['groups']}
    assert 'path' not in paper and 'blob_path' not in paper
    assert build_sphere(app.repo) == graph


def test_related_titles_share_topic_and_summary_only_nodes_are_available(tmp_path):
    from robotlit.sphere import build_sphere
    from robotlit.db import summaries
    app = indexed(tmp_path)
    with app.repo.write() as conn:
        for name in ['Dexterous tactile hand policy', 'Tactile dexterous manipulation']:
            conn.execute(summaries.insert().values(path=name,title=name,text=name,sha256=name,root_id='papers'))
    graph = build_sphere(app.repo)
    tactile = [n for n in graph['nodes'] if n['title'].startswith(('Dexterous tactile','Tactile dexterous'))]
    assert len(tactile) == 2
    assert tactile[0]['group_id'] == tactile[1]['group_id']
    assert all(n['document_id'] is None and n['source_url'] is None for n in tactile)


def test_sphere_page_api_and_old_workspace_redirect(tmp_path):
    from fastapi.testclient import TestClient
    from robotlit.api import create_app
    app = indexed(tmp_path)
    with TestClient(create_app(app)) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert 'paper-sphere' in page.text and 'results' in page.text
        assert client.get('/sphere').status_code == 200
        redirect = client.get('/workspace', follow_redirects=False)
        assert redirect.status_code == 307 and redirect.headers['location'] == '/'
        graph = client.get('/v1/sphere').json()
        assert graph['nodes']
        assert client.get('/assets/sphere.js').status_code == 200
        assert client.get('/assets/../../etc/passwd').status_code == 404


def test_unindexed_pdf_is_visible_without_claiming_pdf_evidence(tmp_path):
    from robotlit.sphere import build_sphere
    from test_search import write_pdf
    app = indexed(tmp_path)
    write_pdf(app.settings.source_roots['papers']/'lab'/'pdfs'/'tactile-new.pdf', 'A tactile policy')
    graph = build_sphere(app.repo, app.ingestor.inventory('papers'))
    paper = next(n for n in graph['nodes'] if n['title'] == 'tactile-new')
    assert paper['document_id'] is None
    assert paper['source_url'].startswith('/v1/source-files/')
    assert not paper['search_ready']


def test_missing_source_root_keeps_retained_sphere_available(tmp_path):
    from fastapi.testclient import TestClient
    from robotlit.api import create_app
    import shutil
    app = indexed(tmp_path)
    shutil.rmtree(app.settings.source_roots['papers'])
    with TestClient(create_app(app)) as client:
        response = client.get('/v1/sphere')
        assert response.status_code == 200
        graph = response.json()
        assert graph['nodes'] and graph['inventory_warnings']
        assert graph['nodes'][0]['document_id']


def test_changed_source_is_pending_and_old_snapshot_stays_visible(tmp_path):
    from robotlit.sphere import build_sphere
    from test_search import write_pdf
    app = indexed(tmp_path)
    path = app.settings.source_roots['papers']/'lab'/'pdfs'/'policy.pdf'
    write_pdf(path, 'A newer and different camera policy source version')
    sources = [s.model_copy(update={'title':'Replaced paper'}) for s in app.ingestor.inventory('papers')]
    graph = build_sphere(app.repo, sources)
    assert any(n['document_id'] for n in graph['nodes'])
    new = next(n for n in graph['nodes'] if n['title'] == 'Replaced paper')
    assert new['document_id'] is None and not new['search_ready']


def test_unindexed_pdf_link_opens_file_and_rejects_unknown_sources(tmp_path):
    from fastapi.testclient import TestClient
    from robotlit.api import create_app
    from robotlit.sphere import source_pdf_url
    from test_search import write_pdf
    app = indexed(tmp_path)
    root = app.settings.source_roots['papers']
    path = root/'lab'/'pdfs'/'2025-charged pion.pdf'
    write_pdf(path, 'Flavor dependence of charged pion fragmentation functions')
    outside = tmp_path/'outside.pdf'
    write_pdf(outside, 'Outside configured collection')
    (root/'escape.pdf').symlink_to(outside)
    with TestClient(create_app(app)) as client:
        graph = client.get('/v1/sphere').json()
        paper = next(n for n in graph['nodes'] if n['title'] == 'charged pion')
        response = client.get(paper['source_url'])
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/pdf'
        assert response.content == path.read_bytes()
        assert client.get(source_pdf_url(outside)).status_code == 404
        assert client.get(source_pdf_url(root/'escape.pdf')).status_code == 404
        path.unlink()
        assert client.get(paper['source_url']).status_code == 404


def test_summary_search_result_links_to_unindexed_local_pdf(tmp_path):
    from robotlit.contracts import SearchRequest
    from robotlit.sphere import source_pdf_url
    from test_search import write_pdf
    app = indexed(tmp_path)
    root = app.settings.source_roots['papers']
    pdf = root/'lab'/'pdfs'/'charged-pion.pdf'
    write_pdf(pdf, 'Flavor dependence of charged pion fragmentation functions')
    (root/'lab'/'summary'/'charged-pion.md').write_text('# Charged pion\nCharged pion fragmentation functions')
    app.ingestor.index_summaries('papers')
    result = app.run_search(SearchRequest(question='charged pion fragmentation'))
    paper = next(p for p in result['unresolved'] if p['document_id'] is None)
    assert paper['source_url'] == source_pdf_url(pdf)


def test_result_card_title_and_open_pdf_link_open_the_direct_pdf():
    import json
    import shutil
    import subprocess
    from pathlib import Path
    import pytest
    if not shutil.which('node'):
        pytest.skip('Node.js needed for result card rendering check')
    js = Path('src/robotlit/sphere.js').read_text()
    helpers = js[js.index('  function element('):js.index('  async function api(')]
    card = js[js.index('  function card('):js.index('  function showPapers(')]
    harness = '''
const assert = require('node:assert/strict');
const document = {createElement:tag=>({tag, children:[], append(...nodes){this.children.push(...nodes);}}),
                  createTextNode:text=>({textContent:text})};
const state = {nodes:[],groups:[{id:'physics',label:'Nuclear & particle physics'}]};
HELPERS
CARD
for (const paper of [
    {title:'Charged pion',group_id:'physics',source_url:'/v1/source-files/hash/pdf'},
    {title:'Indexed paper',document_id:'document'}
]) {
    const rendered=card(paper);
    const heading=rendered.children.find(n=>n.tag==='h3');
    const open=rendered.children.find(n=>n.className==='card-links').children[0];
    assert.equal(heading.children[0].tag,'a');
    assert.equal(heading.children[0].href,open.href);
    assert.equal(open.target,'_blank');
    assert.ok(open.href.endsWith('/pdf'));
    if(paper.group_id) assert.equal(rendered.children.find(n=>n.className==='paper-meta').textContent,'Nuclear & particle physics');
}
'''
    subprocess.run(['node', '-e', harness.replace('HELPERS', helpers).replace('CARD', card)], check=True)
