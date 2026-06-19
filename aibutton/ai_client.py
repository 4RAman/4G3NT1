"""Async Ollama client with remote -> local fallback cascade.

One-time setup
--------------
On the Pi (local fallback server):
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull smollm2:135m        # MUST be pre-pulled; ~270 MB, fits 1 GB RAM

On the LAN server (config "ollama_host"):
    ollama pull llama3.2:1b
    # ensure it listens on the LAN, e.g. OLLAMA_HOST=0.0.0.0 ollama serve

Cascade: remote model first (5 s timeout) when prefer_remote is true;
on timeout/connection/HTTP error, fall back to the Pi-local model
(60 s timeout - the 3B+ generates ~2-4 tokens/s) when fallback_to_local
is true. prefer_remote=false skips the remote entirely. If every
attempt fails, query() raises AIUnavailableError.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx
import ollama

log = logging.getLogger(__name__)

# Errors that mean "this Ollama endpoint can't serve us right now".
# httpx.HTTPError covers ConnectError and all timeout flavours.
_FALLBACK_ERRORS = (httpx.HTTPError, ollama.ResponseError, ConnectionError, OSError)


class AIUnavailableError(Exception):
    """Every configured AI backend failed."""


class _ConfigSource(Protocol):
    @property
    def config(self): ...


class AIClient:
    """`config_source` is anything with a `.config` AppConfig property
    (normally ConfigManager - reads it per query, so SIGHUP reloads
    apply immediately). `client_factory(host, timeout)` exists for
    test injection; defaults to ollama.AsyncClient."""

    def __init__(self, config_source: _ConfigSource, client_factory=None):
        self._cfg_src = config_source
        self._client_factory = client_factory or (
            lambda host, timeout: ollama.AsyncClient(host=host, timeout=timeout)
        )
        self._clients: dict[tuple[str, float], object] = {}

    def _client(self, host: str, timeout: float):
        key = (host, timeout)
        if key not in self._clients:
            self._clients[key] = self._client_factory(host, timeout)
        return self._clients[key]

    async def query(self, prompt: str) -> str:
        cfg = self._cfg_src.config
        attempts: list[tuple[str, str, str, float]] = []
        if cfg.prefer_remote:
            attempts.append(("remote", cfg.ollama_host, cfg.remote_model, cfg.remote_timeout_s))
            if cfg.fallback_to_local:
                attempts.append(
                    ("local", cfg.local_ollama_host, cfg.local_model, cfg.local_timeout_s)
                )
        else:
            attempts.append(("local", cfg.local_ollama_host, cfg.local_model, cfg.local_timeout_s))

        errors: list[str] = []
        for name, host, model, timeout in attempts:
            try:
                log.info("AI query via %s (%s @ %s)", name, model, host)
                response = await self._client(host, timeout).generate(
                    model=model,
                    prompt=prompt,
                    keep_alive="10m",  # keep the model resident between presses
                )
                return response["response"]
            except _FALLBACK_ERRORS as exc:
                log.warning("AI %s backend failed: %s: %s", name, type(exc).__name__, exc)
                errors.append(f"{name}: {type(exc).__name__}: {exc}")

        raise AIUnavailableError("; ".join(errors))
