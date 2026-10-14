"""Opt-in production integration; isolated schema, never existing user tables."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.mark.skipif(not os.environ.get('ROBOTLIT_TEST_DATABASE_URL'), reason='PostgreSQL integration URL not configured')
def test_postgres_identity_jobs_and_lexical_index(tmp_path):
    from robotlit.config import Settings
    from robotlit.contracts import SearchRequest
    from robotlit.service import LiteratureSystem
    from test_search import write_pdf
    url = make_url(os.environ['ROBOTLIT_TEST_DATABASE_URL'])
    schema = 'robotlit_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        assert int(conn.execute(text('SHOW server_version_num')).scalar_one()) >= 170000
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        version = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar_one()
        assert tuple(map(int, version.split('.')[:2])) >= (0,8)
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    isolated_url = url.update_query_dict({'options': f'-csearch_path={schema},public'})
    try:
        root = tmp_path/'labs'; (root/'lab'/'pdfs').mkdir(parents=True)
        path=root/'lab'/'pdfs'/'policy.pdf'
        write_pdf(path,'A multi-view camera policy with language conditioning')
        path.with_name('alias.pdf').write_bytes(path.read_bytes())
        system=LiteratureSystem(Settings(source_roots={'papers':root}, data_dir=tmp_path/'data',
                                        database_url=isolated_url.render_as_string(hide_password=False)))
        rid=system.ingest('papers');system.work_until_idle()
        assert system.status(rid)['result']['searchable']==1
        result=system.run_search(SearchRequest(question='multi-view camera policy'))
        assert result['coverage']['documents_in_snapshot']==1
        assert result['unresolved'] and result['usage']['cloud_calls']==0
        assert system.evidence.resolve(result['unresolved'][0]['source_passages'][0])['text']
        system.repo.engine.dispose()
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()
