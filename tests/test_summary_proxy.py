import io
import json
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from labs import summarize_paper as summarizer


PROXY_URL = "http://127.0.0.1:8787/v1/chat/completions"


def response(data):
    return io.BytesIO(json.dumps(data).encode())


def test_caps_workers_to_currently_available_proxy_slots(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", PROXY_URL)
    health = {"pool": {"total_slots": 3, "available_slots": 2}}
    with patch.object(summarizer, "urlopen", return_value=response(health)):
        assert summarizer.proxy_worker_count(4) == 2


def test_preserves_requested_count_for_remote_endpoints(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://example.com/v1/chat/completions")
    assert summarizer.proxy_worker_count(4) == 4


def test_capacity_probe_failure_preserves_requested_workers(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", PROXY_URL)
    with patch.object(summarizer, "urlopen", side_effect=OSError("Proxy unreachable")):
        assert summarizer.proxy_worker_count(4) == 4


def test_explicit_single_worker_stays_single(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", PROXY_URL)
    with patch.object(summarizer, "urlopen", return_value=response({"pool": {"total_slots": 3, "available_slots": 3}})):
        assert summarizer.proxy_worker_count(1) == 1


def test_busy_proxy_waits_past_four_failed_requests_then_succeeds():
    errors = [HTTPError(PROXY_URL, 503, "Busy", {}, io.BytesIO(b"busy")) for _ in range(5)]
    clock = [0.0]

    def wait(seconds):
        clock[0] += seconds

    with patch.object(summarizer, "urlopen", side_effect=errors + [response({"ok": True})]), patch.object(summarizer.time, "monotonic", side_effect=lambda: clock[0]), patch.object(summarizer.time, "sleep", side_effect=wait):
        data = summarizer.read_summary_response(Request(PROXY_URL), timeout=1800)
    assert json.loads(data) == {"ok": True}
    assert clock[0] >= 60


def test_busy_wait_is_bounded_by_timeout():
    clock = [0.0]

    def wait(seconds):
        clock[0] += seconds

    error = HTTPError(PROXY_URL, 503, "Busy", {}, io.BytesIO(b"busy"))
    with patch.object(summarizer, "urlopen", side_effect=error), patch.object(summarizer.time, "monotonic", side_effect=lambda: clock[0]), patch.object(summarizer.time, "sleep", side_effect=wait):
        with pytest.raises(HTTPError):
            summarizer.read_summary_response(Request(PROXY_URL), timeout=45)
    assert clock[0] == 45


def test_auth_error_is_not_retried():
    error = HTTPError(PROXY_URL, 401, "Unauthorized", {}, io.BytesIO(b"unauthorized"))
    with patch.object(summarizer, "urlopen", side_effect=error), patch.object(summarizer.time, "sleep", side_effect=AssertionError("Should not retry")):
        with pytest.raises(HTTPError) as exc:
            summarizer.read_summary_response(Request(PROXY_URL), timeout=1800)
    assert exc.value.code == 401
