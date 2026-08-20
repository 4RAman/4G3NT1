"""Executors for the log/timer_toggle/webhook action primitives.

execute() returns an ActionResult instead of raising for expected
failures (a webhook 5xx or unreachable host) - main.py maps ok/not-ok
onto the LED and sound without caring which primitive ran.

The webhook primitive is the entire IFTTT/Make/n8n/Home Assistant
integration surface: anything smarter than these primitives should live
on the receiving end of a webhook, not in the button - AI included.

The osc primitive is the same idea pointed at music and show-control
software, which listens on UDP rather than HTTP. It is a separate action
rather than a webhook setting because the two differ in kind: one is a
request with an answer, the other is a datagram that either leaves or
does not. See [osc.py](osc.py).

The midi primitive is its sibling for the software that does not speak OSC -
Studio One being the case that forced it. Its two halves are elsewhere for the
same reason osc's encoder is: [midi.py](midi.py) says what to send and
[midi_io.py](midi_io.py) gets it to a port, the latter because there turned
out to be two ways to do that and neither works everywhere. What is left here
is the mapping onto ok/not-ok, which is all this module ever does.

Alarm modes are *not* handled here: ringing until dismissed/snoozed needs
the LED/sound/button-event loop that only main.py's run() owns (its
ring_alarm), so alarms fire via the scheduler, never through execute().
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from . import midi, midi_io, osc
from .config import (
    Action,
    LogAction,
    MidiAction,
    OscAction,
    TimerToggleAction,
    WebhookAction,
)

log = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str  # human-readable; shown in the web UI / REST status


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    hours, rem = divmod(s, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else _ORDINAL_SUFFIXES.get(n % 10, "th")
    return f"{n}{suffix}"


def _send_midi(action: MidiAction) -> ActionResult:
    """Map a MIDI send onto ok/not-ok. The port work is in midi_io.py.

    Three failures, three different messages, because they have three different
    fixes: no backend at all is a thing you install, a port that is not there is
    a thing you name or create in loopMIDI, and anything else is the driver
    talking and is worth quoting verbatim.
    """
    what = midi.describe(action.kind, action.channel, action.number, action.value)
    payload = midi.message(
        action.kind, action.channel, action.number, action.value
    )
    try:
        port = midi_io.send(action.port, payload)
        return ActionResult(True, f"MIDI {what} -> {port}")
    except midi_io.PortNotFound as exc:
        return ActionResult(False, str(exc))
    except midi_io.MidiUnavailable as exc:
        return ActionResult(False, f"MIDI unavailable: {exc}")
    except Exception as exc:  # noqa: BLE001
        # Broad on purpose. Both backends reach a C layer - ctypes and rtmidi
        # alike - and neither documents its exception set reliably. A press
        # must never take the service down over a MIDI cable.
        log.exception("midi send failed")
        return ActionResult(False, f"MIDI failed: {type(exc).__name__}: {exc}")


async def execute(
    action: Action,
    *,
    trigger: str,
    mode_name: str,
    store,
    webhook_transport: httpx.AsyncBaseTransport | None = None,
) -> ActionResult:
    if isinstance(action, LogAction):
        ts = store.log_event(action.event, mode=mode_name)
        message = f"Logged {action.event} at {ts.astimezone():%H:%M}"
        count = store.count_today(action.event)
        streak = store.current_streak(action.event)
        details = []
        if count > 1:
            details.append(f"{_ordinal(count)} today")
        if streak > 1:
            details.append(f"{streak}-day streak")
        if details:
            message += f" ({', '.join(details)})"
        return ActionResult(True, message)

    if isinstance(action, TimerToggleAction):
        state, elapsed = store.toggle_timer(action.log_as, mode=mode_name)
        if state == "started":
            return ActionResult(True, f"{action.log_as} timer started")
        message = f"{action.log_as} stopped after {_fmt_elapsed(elapsed)}"
        total = store.total_today(action.log_as)
        if total > elapsed:
            message += f" ({_fmt_elapsed(total)} today)"
        return ActionResult(True, message)

    if isinstance(action, OscAction):
        payload = osc.message(action.address, action.args)
        try:
            # Resolved on the loop rather than inside sendto: a hostname would
            # otherwise cost a blocking DNS lookup in the middle of a press,
            # and "feedback is fire-and-forget" is a promise about the whole
            # path, not just the last call in it.
            loop = asyncio.get_running_loop()
            info = await loop.getaddrinfo(
                action.host, action.port, type=socket.SOCK_DGRAM
            )
            family, socktype, proto, _canon, sockaddr = info[0]
            with socket.socket(family, socktype, proto) as sock:
                sock.setblocking(False)
                sock.sendto(payload, sockaddr)
            # "Sent", never "delivered". UDP has nothing to report back, and
            # claiming more than that is the one thing this result must not do.
            return ActionResult(
                True, f"OSC {action.address} -> {action.host}:{action.port}"
            )
        except (OSError, ValueError) as exc:
            return ActionResult(False, f"OSC failed: {type(exc).__name__}: {exc}")

    if isinstance(action, MidiAction):
        return _send_midi(action)

    if isinstance(action, WebhookAction):
        payload = {
            "trigger": trigger,
            "mode": mode_name,
            "ts": datetime.now(timezone.utc).isoformat(),
            **action.payload,  # user payload wins on key collisions
        }
        try:
            async with httpx.AsyncClient(
                timeout=WEBHOOK_TIMEOUT_S, transport=webhook_transport
            ) as client:
                response = await client.post(action.url, json=payload)
            if response.is_success:
                return ActionResult(True, f"Webhook OK ({response.status_code})")
            return ActionResult(False, f"Webhook returned {response.status_code}")
        except httpx.HTTPError as exc:
            return ActionResult(False, f"Webhook failed: {type(exc).__name__}: {exc}")

    return ActionResult(False, f"unknown action type {type(action).__name__}")
