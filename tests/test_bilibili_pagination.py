import json

from labs import download_paper


def test_chrome_reads_only_videos_shown_at_supplied_link(monkeypatch):
    url = 'https://space.bilibili.com/123/upload/video?order=pubdate'
    entries = [
        {'webpage_url': 'https://www.bilibili.com/video/BVfirst'},
        {'webpage_url': 'https://www.bilibili.com/video/BVfirst'},
        {'webpage_url': 'https://www.bilibili.com/video/BVsecond'},
    ]

    def fetch(page_url, timeout, page_expression):
        assert page_url == url, 'must preserve the supplied URL without requesting another page'
        return json.dumps({'videos': entries, 'has_more': True})

    monkeypatch.setattr(download_paper, 'fetch_text_from_remote_chrome', fetch)
    monkeypatch.setattr(download_paper, 'fetch_bilibili_video_details', lambda url, timeout: {'title': url})
    videos = download_paper.fetch_bilibili_video_metadata_from_chrome(url, timeout=10, limit=100)
    assert [v['webpage_url'] for v in videos] == [entries[0]['webpage_url'], entries[2]['webpage_url']]


def test_chrome_visible_videos_respect_limit(monkeypatch):
    entries = [{'webpage_url': f'https://www.bilibili.com/video/BV{key}'} for key in ('first', 'second')]
    monkeypatch.setattr(download_paper, 'fetch_text_from_remote_chrome', lambda *a, **kw: json.dumps({'videos': entries}))
    monkeypatch.setattr(download_paper, 'fetch_bilibili_video_details', lambda url, timeout: {'title': url})
    videos = download_paper.fetch_bilibili_video_metadata_from_chrome('https://space.bilibili.com/123/upload/video', 10, 1)
    assert [v['webpage_url'] for v in videos] == [entries[0]['webpage_url']]
