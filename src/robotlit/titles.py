"""Paper names come from paper records or PDF text, never video captions."""
import re
import subprocess
import unicodedata
from urllib.parse import urlparse
from xml.etree import ElementTree


def paper_key(title):
    title = unicodedata.normalize('NFKC', title).casefold()
    return '-'.join(re.findall(r'[^\W_]+', title, re.UNICODE))


def video_record(info):
    host = (urlparse(info.get('page_url', '')).hostname or '').lower()
    return any(host == domain or host.endswith('.' + domain)
               for domain in ('bilibili.com', 'youtube.com', 'youtu.be'))


def paper_url(url):
    return re.sub(r'v\d+(?=\.pdf$|$)', '', url or '').removesuffix('.pdf')


def pdf_title(path):
    """Read only page one; the largest text near the top is normally the title."""
    try:
        result = subprocess.run(['pdftotext', '-f', '1', '-l', '1', '-bbox', str(path), '-'],
                                capture_output=True, timeout=15)
        if result.returncode:
            return None
        root = ElementTree.fromstring(result.stdout)
        page = next(e for e in root.iter() if e.tag.rsplit('}', 1)[-1] == 'page')
        lines = {}
        for word in page.iter():
            if word.tag.rsplit('}', 1)[-1] != 'word' or not word.text:
                continue
            y, height = float(word.get('yMin')), float(word.get('yMax')) - float(word.get('yMin'))
            if height > 35 and height > 1.4 * (float(word.get('xMax')) - float(word.get('xMin'))):
                continue  # Rotated arXiv sidebar text is not the paper heading.
            if y > float(page.get('height')) * .45:
                continue
            lines.setdefault(round(y, 1), []).append((float(word.get('xMin')), height, word.text))
        candidates = []
        for y, words in sorted(lines.items()):
            words.sort()
            text = ' '.join(w[2] for w in words)
            if len(re.findall(r'[^\W_]+', text)) >= 2 and not re.search(r'https?://|arxiv:|@', text, re.I):
                candidates.append((y, max(w[1] for w in words), text))
        if not candidates:
            return None
        largest = max(height for _, height, _ in candidates)
        start = next(i for i, (_, height, _) in enumerate(candidates) if height >= largest * .93)
        chosen = [candidates[start][2]]
        previous = candidates[start][0]
        for y, height, text in candidates[start + 1:]:
            if height < largest * .88 or y - previous > largest * 2.2 or len(chosen) >= 5:
                break
            chosen.append(text); previous = y
        title = ' '.join(chosen).strip()
        return title if 8 <= len(title) <= 400 else None
    except (OSError, subprocess.TimeoutExpired, ElementTree.ParseError, StopIteration, ValueError, TypeError):
        return None
