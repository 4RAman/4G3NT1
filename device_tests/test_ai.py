"""AI client test — works anywhere with --mock, needs Ollama hosts without it.

Mocked (no network; demonstrates the remote-fails -> local-answers cascade):
    python device_tests/test_ai.py --mock

Real (uses /etc/aibutton/config.json or $AIBUTTON_CONFIG or --config):
    .venv/bin/python device_tests/test_ai.py
    .venv/bin/python device_tests/test_ai.py --prompt "Say hello in five words."
"""

import argparse
import asyncio
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from aibutton.ai_client import AIClient, AIUnavailableError  # noqa: E402
from aibutton.config import AppConfig, ConfigManager  # noqa: E402


class _DeadRemote:
    async def generate(self, **kwargs):
        import httpx

        raise httpx.ConnectError("mock: remote server unreachable")


class _WorkingLocal:
    async def generate(self, model, prompt, **kwargs):
        await asyncio.sleep(0.5)
        return {"response": f"[mock local {model}] response to: {prompt}"}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="no network; fake clients")
    parser.add_argument("--config", default=None)
    parser.add_argument("--prompt", default="Reply with the single word: pong")
    args = parser.parse_args()

    if args.mock:
        cfg_src = types.SimpleNamespace(config=AppConfig())
        fakes = {
            AppConfig().ollama_host: _DeadRemote(),
            AppConfig().local_ollama_host: _WorkingLocal(),
        }
        client = AIClient(cfg_src, client_factory=lambda host, timeout: fakes[host])
        print("mock mode: remote will fail, local will answer")
    else:
        cm = ConfigManager(args.config)
        print(f"config: {cm.path}")
        print(f"remote: {cm.config.remote_model} @ {cm.config.ollama_host}")
        print(f"local:  {cm.config.local_model} @ {cm.config.local_ollama_host}")
        client = AIClient(cm)

    print(f"prompt: {args.prompt!r}")
    try:
        answer = await client.query(args.prompt)
    except AIUnavailableError as exc:
        print(f"FAILED — all backends down: {exc}")
        sys.exit(1)
    print(f"answer: {answer}")


if __name__ == "__main__":
    asyncio.run(main())
