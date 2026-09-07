"""The phone app's copy of the API surface, checked against the real one.

The iOS app (`ios/`, TODO 90) is a window on this service, so the one thing it
mirrors is the set of routes it calls and one captured response body. Mirrored
tables are tested, not trusted - and this is the cheap half of that: it needs
no Mac, no Xcode and no Swift toolchain, just the text of two files.

What it cannot check is that the Swift compiles. That is `swift test` in
`ios/ButtonKit`, on the machine with Xcode on it.
"""

import json
import re
from pathlib import Path

import pytest

from aibutton.audio import ToneLibrary
from aibutton.config import ConfigManager
from aibutton.device import MockDevice
from aibutton.main import Clock, DeviceStatus
from aibutton.store import EventStore
from aibutton.webui import WebContext, create_app

IOS = Path(__file__).resolve().parent.parent / "ios" / "ButtonKit" / "Sources" / "ButtonKit"
CLIENT = IOS / "HostClient.swift"
SAMPLES = IOS / "Samples.swift"


@pytest.fixture
def app(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"ble_device_name": "TestBtn"}), encoding="utf-8")
    store = EventStore(str(tmp_path / "events.db"))
    tones = ToneLibrary()
    ctx = WebContext(
        cm=ConfigManager(str(cfg_path)),
        store=store,
        status=DeviceStatus(),
        device=MockDevice(),
        clock=Clock(),
        tones=tones,
    )
    yield create_app(ctx)
    store.close()
    tones.close()


def _swift_routes() -> set[str]:
    """Every `/api/...` string literal in the Swift client."""
    text = CLIENT.read_text(encoding="utf-8")
    return set(re.findall(r'"(/api/[^"]*)"', text))


def _sample(name: str) -> object:
    """One of the captured bodies out of Samples.swift.

    They are Swift raw strings (`#"""` ... `"""#`) holding nothing but JSON, so
    the whole extraction is finding the fence.
    """
    text = SAMPLES.read_text(encoding="utf-8")
    match = re.search(
        r'static let %s = #"""(.*?)"""#' % re.escape(name), text, re.DOTALL
    )
    assert match, f"no sample named {name!r} in {SAMPLES.name}"
    return json.loads(match.group(1))


def test_the_app_only_calls_routes_the_service_serves(app):
    served = {route.path for route in app.routes}
    called = _swift_routes()
    assert called, "found no /api routes in the Swift client - has it moved?"
    missing = called - served
    assert not missing, (
        f"the iOS app calls {sorted(missing)}, which this service does not "
        f"serve. Change ios/ButtonKit/Sources/ButtonKit/HostClient.swift in the "
        f"same commit as the endpoint."
    )


def test_the_app_calls_few_enough_routes_to_still_be_a_window(app):
    # Not a style rule: every route the phone learns is a decision it could
    # start making for itself, which is the one shape TODO 90 refused. If this
    # needs raising, that is a decision to record rather than a number to bump.
    assert len(_swift_routes()) <= 6


@pytest.mark.parametrize("name,route", [("status", "/api/status"), ("config", "/api/config")])
async def test_a_captured_body_has_no_field_the_service_stopped_sending(
    app, name, route
):
    """The sample is what previews render and what the Swift tests decode.

    A key in it that the service no longer sends is a field the app believes in
    and will never receive - so the direction that matters is subset, not
    equality. A service that *grew* a key is fine here and the app ignores it.
    """
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        live = (await client.get(route)).json()

    stale = set(_sample(name)) - set(live)
    assert not stale, (
        f"Samples.{name} still carries {sorted(stale)}, which {route} no longer "
        f"answers with."
    )
