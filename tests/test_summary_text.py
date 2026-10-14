from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from labs import summarize_paper as summarizer


@pytest.mark.parametrize('heading', [
    'References', 'REFERENCES', 'R EFERENCES', 'R E F E R E N C E S', '9 References', '9. References',
    'VIII. REFERENCES', 'Bibliography', 'Works Cited',
    'Appendix', 'Appendices', 'Appendix A', 'Appendix A. Implementation Details',
    'Appendix: Additional Results', 'A. Appendix', 'Supplementary Material',
    'Supplemental Material', 'Supplementary Information',
    'References                  [14] A reference in the second column.',
    'Appendix A                  More details about the robot',
])
def test_extraction_removes_back_matter_before_flattening(heading):
    raw = 'Abstract\nMain finding.\f9 Conclusion\nFinal result.\n\n' + heading + '\nTail content not needed.\fMore tail.'
    with patch.object(summarizer.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)):
        text = summarizer.extract_pdf_text(Path('paper.pdf'))
    assert text == 'Abstract Main finding. 9 Conclusion Final result.'


def test_inline_mentions_and_contents_entries_do_not_cut_main_text():
    raw = ('Contents\nReferences ........ 9\nAppendix A. More Results ...... 10\n'
           'Abstract\nWe describe our method in Appendix A.\n'
           'Appendix A provides additional implementation details.\n'
           'Further discussion is given in\nAppendix D.\n'
           'References to earlier work motivate our method.\n'
           'Our method includes a references field.\n'
           '10 Conclusion\nThe final main result.\n'
           'References\n[1] Prior work.\nAppendix A\nExtra results.')
    with patch.object(summarizer.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)):
        text = summarizer.extract_pdf_text(Path('paper.pdf'))
    assert 'Appendix A provides additional implementation details.' in text
    assert 'Further discussion is given in Appendix D.' in text
    assert 'The final main result.' in text
    assert '[1] Prior work' not in text


def test_no_heading_keeps_existing_character_limit():
    raw = 'Abstract\n' + 'Main content. ' * 100
    with patch.object(summarizer.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)):
        text = summarizer.extract_pdf_text(Path('paper.pdf'), max_chars=60)
    assert text == ' '.join(raw.split())[:60]


def test_text_prompt_receives_trimmed_main_content():
    raw = 'Abstract\nOur useful main result.\nReferences\nUnneeded citation.\nAppendix\nLong appendix.'
    with patch.object(summarizer.subprocess, 'run', return_value=SimpleNamespace(stdout=raw)), \
         patch.object(summarizer, 'summarize_with_ai', return_value='summary') as request:
        summarizer.summarize_paper_from_text({'title':'Test'}, Path('paper.pdf'), timeout=1, max_chars=90000)
    prompt = request.call_args.args[0]
    assert 'Our useful main result.' in prompt
    assert 'Unneeded citation.' not in prompt and 'Long appendix.' not in prompt
