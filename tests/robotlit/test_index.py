from test_search import indexed, make_app, write_pdf


def test_lexical_queries_use_bounded_database_candidates(tmp_path):
    from robotlit.contracts import QueryPlan
    from robotlit.db import chunks, summaries
    app = indexed(tmp_path)
    original = app.repo.rows
    def reject_full_text_scan(table, condition=None, conn=None):
        assert table not in (chunks, summaries), 'Retrieval must query indexes, not load all corpus text'
        return original(table, condition, conn)
    app.repo.rows = reject_full_text_scan
    hits = app.retriever.retrieve(QueryPlan(search_queries=['wrist RGB policy']), app.repo.corpus_snapshot())
    assert hits and hits[0]['channel'] == 'pdf'
    assert hits[0]['channels'][0]['channel'] == 'lexical'


def test_search_does_not_add_new_summaries_to_saved_review(tmp_path):
    from robotlit.contracts import QueryPlan, SearchRequest, Budget
    app = indexed(tmp_path)
    p = app.settings.source_roots['papers']/'lab'/'pdfs'/'two.pdf'
    write_pdf(p, 'A second camera policy')
    app.ingest('papers'); app.work_until_idle()
    out = app.run_search(SearchRequest(plan=QueryPlan(search_queries=['policy'], mode='collection_review'), mode='collection_review', budgets=Budget(max_documents=1,max_cloud_calls=0)))
    saved = out['snapshot']
    summary = app.settings.source_roots['papers']/'lab'/'summary'/'new.md'
    summary.write_text('# New\nNew magical bimanual policy')
    app.ingestor.index_summaries('papers')
    resumed = app.run_search(SearchRequest(resume_token=out['resume_token']))
    assert resumed['snapshot'] == saved
    assert resumed['coverage']['summary_only_candidates'] == 0


def test_all_predicate_states_and_rrf():
    from robotlit.retrieval import rrf
    assert rrf([['a','b'],['b','c']])[0][0] == 'b'
    assert dict(rrf([['a']]))['a'] == 1/61
