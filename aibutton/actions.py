"""Executors for the prompt/log/timer_toggle/webhook action primitives.

execute() returns an ActionResult instead of raising for expected
failures (AI backends down, webhook 5xx/unreachable) - main.py maps
ok/not-ok onto LED, sound, and BLE without caring which primitive ran.

The webhook primitive is the entire IFTTT/Make/n8n/Home Assistant
integration surface: anything smarter than these primitives should live
on the receiving end of a webhook, not in the button.

Alarm modes are *not* handled here: ringing until dismissed/snoozed needs
the LED/sound/button-event loop that only main.py's run() owns (its
ring_alarm), so alarms fire via the scheduler, never through execute().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .ai_client import AIUnavailableError
from .config import (
    Action,
    LogAction,
    PromptAction,
    TimerToggleAction,
    WebhookAction,
)

log = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str  # human-readable; sent to BLE RESPONSE_CHAR on success


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    hours, rem = divmod(s, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else _ORDINAL_SUFFIXES.get(n % 10, "th")
    return f"{n}{suffix}"


async def execute(
    action: Action,
    *,
    trigger: str,
    mode_name: str,
    ai,
    store,
    webhook_transport: httpx.AsyncBaseTransport | None = None,
) -> ActionResult:
    if isinstance(action, PromptAction):
        try:
            return ActionResult(True, await ai.query(action.prompt))
        except AIUnavailableError as exc:
            return ActionResult(False, f"AI unavailable: {exc}")

    if isinstance(action, LogAction):
        ts = store.log_event(action.event)
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
        state, elapsed = store.toggle_timer(action.log_as)
        if state == "started":
            return ActionResult(True, f"{action.log_as} timer started")
        message = f"{action.log_as} stopped after {_fmt_elapsed(elapsed)}"
        total = store.total_today(action.log_as)
        if total > elapsed:
            message += f" ({_fmt_elapsed(total)} today)"
        return ActionResult(True, message)

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
