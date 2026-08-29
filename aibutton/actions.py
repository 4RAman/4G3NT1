"""Executors for the log/timer_toggle/webhook/osc/midi action primitives.

execute() returns an ActionResult instead of raising for expected failures (a
webhook 5xx or unreachable host) - main.py maps ok/not-ok onto the LED and
sound without caring which primitive ran.

The webhook primitive is the entire IFTTT/Make/n8n/Home Assistant integration
surface: anything smarter than these primitives should live on the receiving
end of a webhook, not in the button - AI included.

The osc primitive is the same idea pointed at music and show-control software,
which listens on UDP rather than HTTP. It is a separate action rather than a
webhook setting because the two differ in kind: one is a request with an
answer, the other is a datagram that either leaves or does not. See
[osc.py](osc.py).

The midi primitive is its sibling for software that does not speak OSC. Its
two halves are elsewhere for the same reason osc's encoder is:
[midi.py](midi.py) says what to send and [midi_io.py](midi_io.py) gets it to a
port - the latter because there are two ways to do that and neither works
everywhere. What is left here is the mapping onto ok/not-ok.

Alarm modes are *not* handled here: ringing until dismissed/snoozed needs the
LED/sound/button-event loop that only main.py's run() owns (its ring_alarm), so
alarms fire via the scheduler, never through execute().
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from . import keys_io, midi, midi_io, osc, summary
from .config import (
    Action,
    KeysAction,
    LogAction,
    MidiAction,
    OscAction,
    SequenceAction,
    TimerToggleAction,
    WebhookAction,
)

log = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str  # human-readable; shown in the web UI / REST status
    # What a takeover reports about the session it just ended - `message`
    # written for a machine, and what an `on_exit` hook carries outward
    # ([summary.py](summary.py)). None for every action and most apps: nothing
    # to report costs nothing.
    summary: Mapping[str, object] | None = None


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    hours, rem = divmod(s, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else _ORDINAL_SUFFIXES.get(n % 10, "th")
    return f"{n}{suffix}"


def _press_keys(action: KeysAction) -> ActionResult:
    """Map a keystroke onto ok/not-ok. The OS work is in keys_io.py.

    Two failures worth distinguishing: no backend is a platform fact the user
    cannot fix here (they are not on Windows), while a refused SendInput is
    almost always UIPI - an elevated window will not accept input from a
    normal-integrity process, and it presents as a chord that works everywhere
    except the one app you wanted it for.
    """
    try:
        return ActionResult(True, f"pressed {keys_io.send(action.combo, action.click)}")
    except keys_io.KeysUnavailable as exc:
        return ActionResult(False, str(exc))
    except Exception as exc:  # noqa: BLE001 - ctypes reaches a C layer; see _send_midi
        log.exception("keys failed")
        return ActionResult(False, f"keys failed: {exc}")


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
    session: Mapping[str, object] | None = None,
) -> ActionResult:
    """Run one action.

    `session` is the summary the app just ended reported, already through
    [summary.py](summary.py)'s gate - flat, scalar and bounded by the time it
    arrives here, so this module never validates it again. Only the two
    carriers that can express structured data read it: a webhook merges it into
    the payload, an OSC message appends it to the arguments. The others ignore
    it on purpose - a log row is one event name and a MIDI message is three
    bytes, and stuffing numbers into either would invent an encoding nobody
    asked for.
    """
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
        # The session's numbers ride *after* the configured arguments, so the
        # indexes a receiver was already mapping do not move when a mode grows
        # an exit hook. Their own order is by key name - summary.as_args.
        args = (*action.args, *summary.as_args(session)) if session else action.args
        payload = osc.message(action.address, args)
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

    if isinstance(action, SequenceAction):
        # **Every step runs, even after one fails.** A sequence is a script,
        # not a transaction: if the webhook is down, the MIDI note that was
        # going to follow it is still what the button was asked to send. The
        # first failure is what the status line reports, because it is the one
        # that explains the rest.
        failure = None
        for index, step in enumerate(action.steps, start=1):
            if step.wait_s:
                await asyncio.sleep(step.wait_s)
            # Steps are resolved before they arrive here
            # (`config.resolve_action`), so a step is always a primitive and
            # this recursion is one deep by construction, not by luck.
            result = await execute(
                step.action, trigger=trigger, mode_name=mode_name, store=store,
                webhook_transport=webhook_transport, session=session,
            )
            if not result.ok and failure is None:
                failure = f"step {index}: {result.message}"
        count = len(action.steps)
        plural = "" if count == 1 else "s"
        if failure is not None:
            return ActionResult(False, f"{count} step{plural}, {failure}")
        return ActionResult(True, f"Sent {count} step{plural}")

    if isinstance(action, KeysAction):
        return _press_keys(action)

    if isinstance(action, WebhookAction):
        payload = {
            # The session's numbers merge in flat, between the identity of the
            # event and the user's own payload: summary.merge says why the
            # first three win over an app and the last one wins over everything.
            **summary.merge(
                {
                    "trigger": trigger,
                    "mode": mode_name,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
                session or {},
            ),
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
