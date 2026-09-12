"""Busca HTTP endurecida para consulta externa (HTTPS, SSRF, limite)."""

from __future__ import annotations

import time
import urllib.parse
import urllib.request

USER_AGENT = "MentorConcursos-ExternalConsultation/1.0"
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_DEADLINE_SECONDS = 30.0


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
    max_bytes: int = DEFAULT_MAX_BYTES,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    opener_factory=None,
) -> bytes:
    """Busca uma URL única, sem redirect automático, com limite de tamanho e prazo."""
    validate_url(url, allowed_hosts)
    opener = opener_factory() if opener_factory else urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    deadline = time.monotonic() + deadline_seconds
    with opener.open(request, timeout=deadline_seconds) as response:
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
