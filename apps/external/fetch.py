"""Busca HTTP endurecida para consulta externa (HTTPS, SSRF, limite, redirects)."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (compatible; MentorConcursos/1.0; "
    "+github.com/araujosdeveloper/mentor-concursos)"
)
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_DEADLINE_SECONDS = 30.0
DEFAULT_MAX_REDIRECTS = 3
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def validate_url(url: str, allowed_hosts: set[str]) -> str:
    """Rejeita URL não-HTTPS, fora da allowlist ou com credenciais.

    A proteção contra destinos privados (SSRF/DNS rebinding) é aplicada pelo
    proxy de egress (Squid), único ponto que resolve DNS e conecta externamente;
    contêineres em redes internas não resolvem DNS público.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("url_not_https")
    host = parsed.hostname or ""
    if host not in allowed_hosts:
        raise ValueError("url_not_allowlisted")
    if parsed.username or parsed.password:
        raise ValueError("url_credentials_forbidden")
    return host


def fetch(
    url: str,
    *,
    allowed_hosts: set[str],
    headers: dict[str, str] | None = None,
    method: str = "GET",
    body: bytes | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    opener_factory=None,
) -> bytes:
    """Busca uma URL, seguindo no máximo `max_redirects` saltos validados."""
    opener = opener_factory() if opener_factory else urllib.request.build_opener(NoRedirect())
    deadline = time.monotonic() + deadline_seconds
    current_url = url
    for _ in range(max_redirects + 1):
        validate_url(current_url, allowed_hosts)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("fetch_timeout")
        request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
        request = urllib.request.Request(
            current_url, data=body, headers=request_headers, method=method
        )
        try:
            response = opener.open(request, timeout=remaining)
        except urllib.error.HTTPError as error:
            if error.code in _REDIRECT_CODES and error.headers.get("Location"):
                current_url = urllib.parse.urljoin(current_url, error.headers["Location"])
                continue
            raise
        break
    else:
        raise ValueError("too_many_redirects")
    with response:
        data = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise ValueError("fetch_timeout")
            block = response.read(min(1024 * 1024, max_bytes - len(data) + 1))
            if not block:
                break
            data.extend(block)
            if len(data) > max_bytes:
                raise ValueError("response_too_large")
    return bytes(data)
