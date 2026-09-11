#!/usr/bin/env python3
"""Aquisição controlada de uma fonte oficial, sem crawler ou publicação automática."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

MAX_REDIRECTS = 3
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
USER_AGENT = "MentorConcursos-OfficialSourceRefresh/1.0"


@dataclass(frozen=True)
class SourcePolicy:
    host: str
    canonical_url: str
    max_bytes: int = DEFAULT_MAX_BYTES
    allowed_mime: tuple[str, ...] = ("application/pdf", "text/plain")


@dataclass(frozen=True)
class Acquisition:
    status: int
    url: str
    content_type: str
    data: bytes
    sha256: str
    etag: str | None
    last_modified: str | None
    redirects: tuple[str, ...]
    changed: bool


def _validate_url(url: str, policy: SourcePolicy) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != policy.host:
        raise ValueError("url_not_allowlisted")
    if parsed.username or parsed.password:
        raise ValueError("url_credentials_forbidden")
    addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise ValueError("private_address_forbidden")


def _magic_ok(content_type: str, data: bytes, allowed: tuple[str, ...]) -> bool:
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime not in allowed:
        return False
    if mime == "application/pdf":
        return data.startswith(b"%PDF-")
    return True


def acquire(policy: SourcePolicy, *, etag: str | None = None, last_modified: str | None = None, opener=None) -> Acquisition:
    _validate_url(policy.canonical_url, policy)
    opener = opener or urllib.request.build_opener()
    request = urllib.request.Request(policy.canonical_url, headers={"User-Agent": USER_AGENT, "Accept": ", ".join(policy.allowed_mime)})
    if etag:
        request.add_header("If-None-Match", etag)
    if last_modified:
        request.add_header("If-Modified-Since", last_modified)
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return Acquisition(304, policy.canonical_url, "", b"", "", error.headers.get("ETag"), error.headers.get("Last-Modified"), (), False)
        raise
    history = tuple(getattr(response, "history", ()) or ())
    if len(history) > MAX_REDIRECTS:
        raise ValueError("too_many_redirects")
    redirects: list[str] = []
    for hop in history:
        hop_url = hop.geturl()
        _validate_url(hop_url, policy)
        redirects.append(hop_url)
    final_url = response.geturl()
    _validate_url(final_url, policy)
    if final_url != policy.canonical_url:
        redirects.append(final_url)
    content_type = response.headers.get("Content-Type", "")
    length = response.headers.get("Content-Length")
    if length and int(length) > policy.max_bytes:
        raise ValueError("response_too_large")
    data = bytearray()
    while True:
        block = response.read(min(1024 * 1024, policy.max_bytes - len(data) + 1))
        if not block:
            break
        data.extend(block)
        if len(data) > policy.max_bytes:
            raise ValueError("response_too_large")
    payload = bytes(data)
    if not _magic_ok(content_type, payload, policy.allowed_mime):
        raise ValueError("mime_or_magic_mismatch")
    digest = hashlib.sha256(payload).hexdigest()
    return Acquisition(200, final_url, content_type, payload, digest, response.headers.get("ETag"), response.headers.get("Last-Modified"), tuple(redirects), True)


def update_decision(acquisition: Acquisition, previous_sha256: str | None) -> str:
    if acquisition.status == 304:
        return "not_modified"
    if previous_sha256 and acquisition.sha256 == previous_sha256:
        return "unchanged"
    return "changed_quarantine"
