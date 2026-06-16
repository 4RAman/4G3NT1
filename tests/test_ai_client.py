import dataclasses
import types

import httpx
import ollama
import pytest

from aibutton.ai_client import AIClient, AIUnavailableError
from aibutton.config import AppConfig

REMOTE = AppConfig().ollama_host
LOCAL = AppConfig().local_ollama_host


class FakeBackend:
    """behavior: a string to answer with, or an exception to raise."""

    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = []

    async def generate(self, model, prompt, **kwargs):
        self.calls.append((model, prompt))
        if isinstance(self.behavior, Exception):
            raise self.behavior
        return {"response": self.behavior}


def make_client(remote_behavior, local_behavior, **cfg_overrides):
    cfg = dataclasses.replace(AppConfig(), **cfg_overrides)
    backends = {REMOTE: FakeBackend(remote_behavior), LOCAL: FakeBackend(local_behavior)}
    client = AIClient(
        types.SimpleNamespace(config=cfg),
        client_factory=lambda host, timeout: backends[host],
    )
    return client, backends


async def test_remote_ok_skips_local():
    client, backends = make_client("remote answer", "local answer")
    assert await client.query("hi") == "remote answer"
    assert backends[REMOTE].calls == [("llama3.2:1b", "hi")]
    assert backends[LOCAL].calls == []


async def test_remote_connect_error_falls_back():
    client, backends = make_client(httpx.ConnectError("down"), "local answer")
    assert await client.query("hi") == "local answer"
    assert backends[LOCAL].calls == [("smollm2:135m", "hi")]


async def test_remote_timeout_falls_back():
    client, _ = make_client(httpx.ReadTimeout("slow"), "local answer")
    assert await client.query("hi") == "local answer"


async def test_remote_http_error_falls_back():
    client, _ = make_client(ollama.ResponseError("model not found", 404), "local answer")
    assert await client.query("hi") == "local answer"


async def test_both_fail_raises_with_both_errors():
    client, _ = make_client(httpx.ConnectError("r-down"), httpx.ConnectError("l-down"))
    with pytest.raises(AIUnavailableError) as exc_info:
        await client.query("hi")
    msg = str(exc_info.value)
    assert "remote" in msg and "local" in msg


async def test_no_fallback_when_disabled():
    client, backends = make_client(
        httpx.ConnectError("down"), "local answer", fallback_to_local=False
    )
    with pytest.raises(AIUnavailableError):
        await client.query("hi")
    assert backends[LOCAL].calls == []


async def test_prefer_remote_false_uses_local_only():
    client, backends = make_client("remote answer", "local answer", prefer_remote=False)
    assert await client.query("hi") == "local answer"
    assert backends[REMOTE].calls == []
