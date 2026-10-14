import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from labs import summarize_paper as summarizer
from test_summary_cache import make_lab


def test_paper_start_includes_character_change_and_done_includes_elapsed(tmp_path, capsys):
    lab, paper = make_lab(tmp_path, 'abhishek', 'Distributional successor features')
    raw = 'Abstract\nMain result.\nReferences\nUnneeded reference text.'
    original = len(' '.join(raw.split()))
    sent = len('Abstract Main result.')
    with patch.object(summarizer.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)), \
         patch.object(summarizer, 'summarize_with_ai', return_value=json.dumps({'paper_summary':'Overview.'})), \
         patch.object(summarizer.time, 'monotonic', side_effect=[100.0, 112.5]):
        done = summarizer.run_summary_jobs([(lab,paper)],1,90000,False,False,'text',set(),{},1)
    output = capsys.readouterr().out
    starts = [line for line in output.splitlines() if '[summary:paper] start:' in line]
    assert starts == [f'[summary:paper] start: abhishek: Distributional successor features | chars: {original} -> {sent}']
    assert '[summary:text]' not in output
    assert '[summary:paper] done:' in output and 'elapsed: 12.5s' in output
    assert done[lab] == 1


def test_extraction_is_quiet_and_start_count_includes_character_cap(capsys):
    raw = 'Abstract\nMain result.\nReferences\nTail.'
    with patch.object(summarizer.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)):
        assert summarizer.extract_pdf_text(Path('paper.pdf'),max_chars=8) == 'Abstract'
    assert capsys.readouterr().out == ''
    with patch.object(summarizer.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)), \
         patch.object(summarizer, 'summarize_with_ai', return_value='summary'):
        summarizer.summarize_paper_from_text({'title':'Test'},Path('lab/pdfs/paper.pdf'),1,8)
    assert f'chars: {len(" ".join(raw.split()))} -> 8' in capsys.readouterr().out


def test_cached_start_does_not_extract_pdf_or_call_ai(tmp_path, capsys):
    lab,paper = make_lab(tmp_path,'lab')
    with patch.object(summarizer,'summarize_paper_from_text',return_value=json.dumps({'paper_summary':'Saved overview.'})):
        summarizer.summarize_paper(lab,paper,timeout=1,max_chars=100)
    capsys.readouterr()
    with patch.object(summarizer.subprocess,'run',side_effect=AssertionError('Cached PDF extracted')), \
         patch.object(summarizer,'summarize_with_ai',side_effect=AssertionError('Cached AI call')):
        summarizer.run_summary_jobs([(lab,paper)],1,100,False,False,'text',set(),{},1)
    output=capsys.readouterr().out
    assert '[summary:paper] start: lab: Shared Paper | source: cache' in output
    assert 'elapsed:' in output
