from __future__ import annotations

import pytest

from apps.external import fetch as fetch_module


def test_validate_url_requires_https() -> None:
    with pytest.raises(ValueError, match="url_not_https"):
        fetch_module.validate_url("http://example.com/x", {"example.com"})


def test_validate_url_requires_allowlisted_host() -> None:
    with pytest.raises(ValueError, match="url_not_allowlisted"):
        fetch_module.validate_url("https://other.com/x", {"example.com"})


def test_validate_url_rejects_credentials() -> None:
    with pytest.raises(ValueError, match="url_credentials_forbidden"):
        fetch_module.validate_url("https://user:pass@example.com/x", {"example.com"})


class _StreamResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, size: int = -1) -> bytes:
        if not self._data:
            return b""
        data, self._data = self._data[:size], self._data[size:]
        return data

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class _Opener:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def open(self, _request, timeout=None):
        return _StreamResponse(self._data)


def test_fetch_reads_body(monkeypatch) -> None:
    monkeypatch.setattr(fetch_module, "validate_url", lambda *_a: "example.com")
    data = fetch_module.fetch(
        "https://example.com/x",
        allowed_hosts={"example.com"},
        opener_factory=lambda: _Opener(b"<html>lei</html>"),
    )
    assert data == b"<html>lei</html>"


def test_fetch_enforces_size_limit(monkeypatch) -> None:
    monkeypatch.setattr(fetch_module, "validate_url", lambda *_a: "example.com")
    with pytest.raises(ValueError, match="response_too_large"):
        fetch_module.fetch(
            "https://example.com/x",
            allowed_hosts={"example.com"},
            max_bytes=4,
            opener_factory=lambda: _Opener(b"x" * 100),
        )
