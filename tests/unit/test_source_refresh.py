from __future__ import annotations

import importlib.util
import sys
from email.message import Message
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "refresh_official_source", Path(__file__).parents[2] / "scripts" / "refresh-official-source.py"
)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
SourcePolicy = _module.SourcePolicy
acquire = _module.acquire
update_decision = _module.update_decision


class FakeResponse:
    def __init__(self, data: bytes, url: str, content_type: str = "application/pdf"):
        self._data = data
        self._url = url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def geturl(self):
        return self._url

    def read(self, size=-1):
        if not self._data:
            return b""
        data, self._data = self._data[:size], self._data[size:]
        return data


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, _request, timeout):
        assert timeout == 30
        return self.response


def policy():
    return SourcePolicy("example.com", "https://example.com/source.pdf")


def test_304_is_not_modified(monkeypatch):
    monkeypatch.setattr(_module, "_validate_url", lambda *_args: None)
    import urllib.error

    class Opener:
        def open(self, _request, timeout):
            raise urllib.error.HTTPError("url", 304, "not modified", Message(), None)

    result = acquire(policy(), etag="etag", opener=Opener())
    assert update_decision(result, "old") == "not_modified"


def test_same_hash_is_unchanged(monkeypatch):
    monkeypatch.setattr(_module, "_validate_url", lambda *_args: None)
    response = FakeResponse(b"%PDF-synthetic", "https://example.com/source.pdf")
    result = acquire(policy(), opener=FakeOpener(response))
    assert update_decision(result, result.sha256) == "unchanged"


def test_changed_hash_enters_quarantine_decision(monkeypatch):
    monkeypatch.setattr(_module, "_validate_url", lambda *_args: None)
    result = acquire(policy(), opener=FakeOpener(FakeResponse(b"%PDF-new", "https://example.com/source.pdf")))
    assert update_decision(result, "0" * 64) == "changed_quarantine"


def test_size_limit_and_magic_are_enforced(monkeypatch):
    monkeypatch.setattr(_module, "_validate_url", lambda *_args: None)
    with pytest.raises(ValueError, match="response_too_large"):
        acquire(
            SourcePolicy("example.com", "https://example.com/a.pdf", max_bytes=4),
            opener=FakeOpener(FakeResponse(b"%PDF-123", "https://example.com/a.pdf")),
        )
