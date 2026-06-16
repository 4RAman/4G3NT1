"""Config loading, validation, and hot-reload for the AI Button.

The config file lives at /etc/aibutton/config.json (override with the
AIBUTTON_CONFIG environment variable or the --config CLI flag).

Config errors never crash the service: a missing file, broken JSON, or a
wrongly-typed key is logged loudly and replaced by its safe default. The
merge is per-key; invalid modes/actions are skipped individually.

v0.3 schema - modes
-------------------
"modes" is an ordered list. The button is always in exactly one mode; a
mode is a named personality made of a behaviour *template* plus an
*activation* that decides when it turns on. Template-specific fields are
stored flat on the mode object, mirroring how actions store their fields.

    "modes": [
      { "name": "Default",
        "template": "actions",
        "activation": { "type": "always" },
        "short_press": { "action": "prompt", "prompt": "...", "label": "..." } },
      { "name": "Morning meds",
        "template": "actions",
        "activation": { "type": "window", "between": ["05:00", "07:00"],
                        "days": ["mon","tue","wed","thu","fri"] },
        "unless_logged_today": "meds_taken",
        "double_tap": { "action": "log", "event": "meds_taken" } },
      { "name": "Wake up",
        "template": "alarm",
        "activation": { "type": "schedule", "at": "07:00",
                        "days": ["mon","tue","wed","thu","fri"] },
        "message": "Wake up", "snooze_minutes": 9, "dismiss_event": "woke_up" }
    ]

Two natures of mode (the template picks the nature):

* **Ambient** (`actions`) - passive; it only *answers* gestures while in
  scope. Pairs with `always`/`window` activations. Resolved first-match-wins
  in config order (see rules.py).
* **Takeover** (`alarm`) - the device *enters* it (a `schedule` fires at a
  clock time) and it owns the button until dismissed (see scheduler.py +
  main.py). The standalone `alarm` *action* of v0.2 is gone - alarms are a
  template now.

Action primitives (the `actions` template body): prompt (Ollama), log
(SQLite event), timer_toggle (start/stop stopwatch pairs), webhook (POST -
the IFTTT/Make/n8n hook).

Migration / back-compat: legacy v0.2 "rules" configs load and are converted
to ambient `actions` modes (window activation from between/days, else
always); a rule gesture using the removed `alarm` action has no fire time
to synthesise, so it is dropped with a loud warning. Legacy v0.1 "commands"
configs still load as a single Default actions mode. Hot reload via SIGHUP
applies to everything except ble_device_name (BLE advertisement registers
once at startup).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import time

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "/etc/aibutton/config.json"

TRIGGER_TYPES = ("short_press", "long_press", "double_tap")

_DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # index = datetime.weekday()


# --- action primitives -------------------------------------------------

@dataclass(frozen=True)
class PromptAction:
    prompt: str
    label: str = ""


@dataclass(frozen=True)
class LogAction:
    event: str


@dataclass(frozen=True)
class TimerToggleAction:
    log_as: str


@dataclass(frozen=True)
class WebhookAction:
    url: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EnterModeAction:
    """Switch into the named takeover mode (alarm/stopwatch/counter). This is
    how a gesture in an ambient mode starts a takeover, so "entered by a
    gesture" needs no special activation type - it is simply an action that
    switches modes. The target is resolved at runtime (main.py), not at parse
    time: forward references and config ordering mean the target may be defined
    later in the list, and a missing/non-takeover target is handled gracefully
    by the runtime (fail state, never a crash)."""

    target: str


Action = PromptAction | LogAction | TimerToggleAction | WebhookAction | EnterModeAction


# --- activations -------------------------------------------------------
#
# Tagged by .type in JSON. always/window are ambient; schedule is takeover.

@dataclass(frozen=True)
class AlwaysActivation:
    """The base Default; active whenever nothing else has taken over."""


@dataclass(frozen=True)
class WindowActivation:
    """Active while the wall-clock is inside `between` (may cross midnight,
    e.g. 22:00-06:00) and the weekday is in `days`. At least one of the two
    is present - an empty window would just be `always`."""

    between: tuple[time, time] | None = None
    days: frozenset[int] | None = None  # 0=Mon .. 6=Sun


@dataclass(frozen=True)
class ScheduleActivation:
    """Fires (enters the mode) at clock time `at`, on `days` (or every day
    when days is None)."""

    at: time
    days: frozenset[int] | None = None  # 0=Mon .. 6=Sun


@dataclass(frozen=True)
class ManualActivation:
    """Never auto-activates - the mode is reached only via an enter_mode
    action from another mode. Takeover-only: it is never ambient-resolved
    (rules.py) and never scheduled (scheduler.py)."""


Activation = AlwaysActivation | WindowActivation | ScheduleActivation | ManualActivation


# --- behaviour templates -----------------------------------------------

@dataclass(frozen=True)
class ActionsBehavior:
    """The everyday ambient template: a gesture -> action map, with an
    optional `unless_logged_today` that stands the whole mode down for the
    rest of the day once the named event has been logged."""

    actions: dict[str, Action]  # trigger value -> action
    unless_logged_today: str | None = None

    @property
    def template(self) -> str:
        return "actions"


@dataclass(frozen=True)
class AlarmBehavior:
    """The takeover alarm template: rings (ALERT LED + looping tone) until a
    press dismisses it, or - on long_press with snooze_minutes set - snoozes.
    Handled by main.py's ring loop, not actions.execute(), since ringing
    owns the LED/sound/button-event loop."""

    message: str = ""
    label: str = ""
    snooze_minutes: float = 0  # 0 = long_press dismisses like any other press
    dismiss_event: str = ""  # optional `log` event name written on dismiss

    @property
    def template(self) -> str:
        return "alarm"


@dataclass(frozen=True)
class StopwatchBehavior:
    """The takeover stopwatch template: enter starts a timer (logged under
    `log_as`); short_press/double_tap mark a lap; long_press stops and exits.
    Handled by main.py's run_stopwatch loop, not actions.execute(), since it
    owns the LED/sound/button-event loop while running."""

    log_as: str = ""

    @property
    def template(self) -> str:
        return "stopwatch"


@dataclass(frozen=True)
class CounterBehavior:
    """The takeover counter template: enter resets the tally to 0;
    short_press/double_tap logs `event` (so existing count_today/streaks just
    work) and bumps the count; long_press exits. Handled by main.py's
    run_counter loop, not actions.execute()."""

    event: str = ""

    @property
    def template(self) -> str:
        return "counter"


Behavior = ActionsBehavior | AlarmBehavior | StopwatchBehavior | CounterBehavior

# Which activation types each template accepts (per-template allow-list,
# mirroring schema.js's `allowedActivations`). A mode whose activation type is
# not allowed for its template is skipped at parse time with a warning.
_ALLOWED_ACTIVATIONS = {
    "actions": (AlwaysActivation, WindowActivation),
    "alarm": (ScheduleActivation,),
    "stopwatch": (ManualActivation,),
    "counter": (ManualActivation,),
}


@dataclass(frozen=True)
class Mode:
    """A named personality: a behaviour template + the activation that turns
    it on. `template` is derived from the behaviour, never stored separately."""

    name: str
    behavior: Behavior
    activation: Activation

    @property
    def template(self) -> str:
        return self.behavior.template


def _default_modes() -> tuple[Mode, ...]:
    return (
        Mode(
            name="Default",
            activation=AlwaysActivation(),
            behavior=ActionsBehavior(
                actions={
                    "short_press": PromptAction(
                        prompt="Summarize the latest system status in one sentence.",
                        label="Status Check",
                    ),
                    "long_press": PromptAction(
                        prompt="What is the current time and a productivity tip?",
                        label="Focus Prompt",
                    ),
                    "double_tap": PromptAction(
                        prompt="Tell me something interesting.",
                        label="Random Fact",
                    ),
                },
            ),
        ),
    )


@dataclass(frozen=True)
class AppConfig:
    ollama_host: str = "http://192.168.1.10:11434"
    local_ollama_host: str = "http://127.0.0.1:11434"
    local_model: str = "smollm2:135m"
    remote_model: str = "llama3.2:1b"
    prefer_remote: bool = True
    fallback_to_local: bool = True
    # The local fallback runs on the Pi itself at ~2-4 tokens/s, so it
    # needs a far longer budget than the LAN server.
    remote_timeout_s: float = 5.0
    local_timeout_s: float = 60.0
    ble_device_name: str = "AIButton"
    sounds_enabled: bool = True
    database_path: str = "data/events.db"  # relative to WorkingDirectory
    web_enabled: bool = True
    web_host: str = "0.0.0.0"  # LAN-facing; the web UI has no auth (see webui.py)
    web_port: int = 8080
    modes: tuple[Mode, ...] = field(default_factory=_default_modes)


# --- parsing helpers ----------------------------------------------------

def _take(raw: dict, key: str, expected: type, default):
    """Return raw[key] if present and well-typed, else the default."""
    if key not in raw:
        return default
    value = raw[key]
    if expected is float:
        # Accept ints for float fields, but never bools (bool is an int subclass).
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    elif expected is bool:
        if isinstance(value, bool):
            return value
    elif isinstance(value, expected) and not isinstance(value, bool):
        return value
    log.error(
        "config: %r should be %s, got %r - using default %r",
        key, expected.__name__, value, default,
    )
    return default


def _parse_action(raw, where: str) -> Action | None:
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - ignored", where)
        return None
    # Legacy v0.1 command entries have no "action" key, just prompt/label.
    kind = raw.get("action", "prompt" if "prompt" in raw else None)
    if kind == "prompt":
        prompt, label = raw.get("prompt"), raw.get("label", "")
        if isinstance(prompt, str) and prompt and isinstance(label, str):
            return PromptAction(prompt=prompt, label=label)
    elif kind == "log":
        event = raw.get("event")
        if isinstance(event, str) and event:
            return LogAction(event=event)
    elif kind == "timer_toggle":
        log_as = raw.get("log_as")
        if isinstance(log_as, str) and log_as:
            return TimerToggleAction(log_as=log_as)
    elif kind == "webhook":
        url, payload = raw.get("url"), raw.get("payload", {})
        if (
            isinstance(url, str)
            and url.startswith(("http://", "https://"))
            and isinstance(payload, dict)
        ):
            return WebhookAction(url=url, payload=payload)
    elif kind == "enter_mode":
        # The target is validated as a non-empty string only; whether a
        # takeover mode by that name actually exists is left to the runtime
        # (forward references / config ordering - see EnterModeAction).
        target = raw.get("target")
        if isinstance(target, str) and target:
            return EnterModeAction(target=target)
    elif kind == "alarm":
        # v0.2 standalone alarm *action* is removed (alarm is a template
        # now). It cannot be migrated inline (no fire time), so callers that
        # see one drop it with a loud warning - see _migrate_rule.
        log.error(
            "config: %s uses the removed 'alarm' action - alarms are now an "
            "alarm-template mode; ignored", where,
        )
        return None
    log.error("config: %s is not a valid action - ignored", where)
    return None


def _parse_time(value) -> time | None:
    if isinstance(value, str):
        try:
            return time.fromisoformat(value)
        except ValueError:
            pass
    return None


def _parse_days(raw_days, where: str) -> frozenset[int] | None | object:
    """Parse a `days` list into a weekday-index set. Returns None when no
    days key was meaningful, or the sentinel _INVALID when present but
    malformed (so the caller can skip the mode)."""
    if isinstance(raw_days, list) and raw_days and all(
        isinstance(d, str) and d.lower() in _DAY_NAMES for d in raw_days
    ):
        return frozenset(_DAY_NAMES.index(d.lower()) for d in raw_days)
    log.error("config: %s must be a list of %s", where, "/".join(_DAY_NAMES))
    return _INVALID


_INVALID = object()  # sentinel: a key was present but malformed -> skip the mode


def _parse_activation(raw, where: str) -> Activation | None:
    """Parse an activation object (tagged by .type). Returns None on any
    problem so the caller skips the whole mode - running a scoped mode at
    the wrong time is worse than not running it."""
    if not isinstance(raw, dict):
        log.error("config: %s.activation must be an object - mode skipped", where)
        return None
    kind = raw.get("type")

    if kind == "always":
        return AlwaysActivation()

    if kind == "manual":
        return ManualActivation()

    if kind == "window":
        between = None
        if "between" in raw:
            pair = raw["between"]
            if isinstance(pair, list) and len(pair) == 2:
                start, end = _parse_time(pair[0]), _parse_time(pair[1])
                if start is not None and end is not None:
                    between = (start, end)
            if between is None:
                log.error(
                    "config: %s.activation.between must be [\"HH:MM\", \"HH:MM\"] - mode skipped",
                    where,
                )
                return None
        days = None
        if "days" in raw:
            days = _parse_days(raw["days"], f"{where}.activation.days")
            if days is _INVALID:
                log.error("config: %s - mode skipped", where)
                return None
        if between is None and days is None:
            # A window with neither bound is just "always".
            return AlwaysActivation()
        return WindowActivation(between=between, days=days)

    if kind == "schedule":
        at = _parse_time(raw.get("at"))
        if at is None:
            log.error("config: %s.activation.at must be \"HH:MM\" - mode skipped", where)
            return None
        days = None
        if "days" in raw:
            days = _parse_days(raw["days"], f"{where}.activation.days")
            if days is _INVALID:
                log.error("config: %s - mode skipped", where)
                return None
        return ScheduleActivation(at=at, days=days)

    log.error("config: %s.activation has unknown type %r - mode skipped", where, kind)
    return None


def _parse_actions_body(raw: dict, where: str, name: str) -> ActionsBehavior | None:
    """Parse the flat actions-template fields. An invalid action is dropped
    individually; a mode left with zero valid gesture actions is skipped."""
    unless_logged_today = None
    if "unless_logged_today" in raw:
        value = raw["unless_logged_today"]
        if isinstance(value, str) and value:
            unless_logged_today = value
        else:
            log.error(
                "config: %s.unless_logged_today must be a non-empty string - mode skipped",
                where,
            )
            return None

    actions: dict[str, Action] = {}
    for trigger in TRIGGER_TYPES:
        if trigger in raw:
            action = _parse_action(raw[trigger], f"{where}.{trigger}")
            if action is not None:
                actions[trigger] = action
    if not actions:
        log.error("config: %s (%r) has no valid gesture actions - skipped", where, name)
        return None
    return ActionsBehavior(actions=actions, unless_logged_today=unless_logged_today)


def _parse_alarm_body(raw: dict, where: str) -> AlarmBehavior | None:
    """Parse the flat alarm-template fields, each falling back per-key."""
    defaults = AlarmBehavior()

    message = raw.get("message", defaults.message)
    if not isinstance(message, str):
        log.error("config: %s.message must be a string - using default", where)
        message = defaults.message

    label = raw.get("label", defaults.label)
    if not isinstance(label, str):
        log.error("config: %s.label must be a string - using default", where)
        label = defaults.label

    snooze = raw.get("snooze_minutes", defaults.snooze_minutes)
    if not (isinstance(snooze, (int, float)) and not isinstance(snooze, bool) and snooze >= 0):
        log.error("config: %s.snooze_minutes must be a number >= 0 - using default", where)
        snooze = defaults.snooze_minutes

    dismiss_event = raw.get("dismiss_event", defaults.dismiss_event)
    if not isinstance(dismiss_event, str):
        log.error("config: %s.dismiss_event must be a string - using default", where)
        dismiss_event = defaults.dismiss_event

    return AlarmBehavior(
        message=message, label=label,
        snooze_minutes=float(snooze), dismiss_event=dismiss_event,
    )


def _parse_stopwatch_body(raw: dict, where: str) -> StopwatchBehavior | None:
    """Parse the flat stopwatch-template field, falling back per-key."""
    defaults = StopwatchBehavior()
    log_as = raw.get("log_as", defaults.log_as)
    if not isinstance(log_as, str):
        log.error("config: %s.log_as must be a string - using default", where)
        log_as = defaults.log_as
    return StopwatchBehavior(log_as=log_as)


def _parse_counter_body(raw: dict, where: str) -> CounterBehavior | None:
    """Parse the flat counter-template field, falling back per-key."""
    defaults = CounterBehavior()
    event = raw.get("event", defaults.event)
    if not isinstance(event, str):
        log.error("config: %s.event must be a string - using default", where)
        event = defaults.event
    return CounterBehavior(event=event)


def _parse_mode(raw, idx: int) -> Mode | None:
    """Parse one mode. A mode with a broken activation, a template<->
    activation nature mismatch, or no usable body is skipped entirely
    (logged) - the fail-soft floor is the built-in default modes."""
    where = f"modes[{idx}]"
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - skipped", where)
        return None
    name = raw["name"] if isinstance(raw.get("name"), str) and raw.get("name") else f"mode {idx + 1}"

    activation = _parse_activation(raw.get("activation", {"type": "always"}), where)
    if activation is None:
        return None

    template = raw.get("template", "actions")
    allowed = _ALLOWED_ACTIVATIONS.get(template)
    if allowed is None:
        log.error("config: %s (%r) has unknown template %r - skipped", where, name, template)
        return None
    if not isinstance(activation, allowed):
        log.error(
            "config: %s (%r) is a %r mode but its activation is %s - skipped",
            where, name, template, type(activation).__name__,
        )
        return None

    if template == "actions":
        behavior = _parse_actions_body(raw, where, name)
    elif template == "alarm":
        behavior = _parse_alarm_body(raw, where)
    elif template == "stopwatch":
        behavior = _parse_stopwatch_body(raw, where)
    elif template == "counter":
        behavior = _parse_counter_body(raw, where)
    else:  # pragma: no cover - allow-list keys and this dispatch stay in sync
        log.error("config: %s (%r) has unknown template %r - skipped", where, name, template)
        return None

    if behavior is None:
        return None
    return Mode(name=name, behavior=behavior, activation=activation)


def _migrate_rule(raw, idx: int) -> Mode | None:
    """Convert one legacy v0.2 rule into an ambient actions mode: window
    activation when it had between/days, else always. A gesture using the
    removed `alarm` action cannot be migrated (no fire time) and is dropped
    with a loud warning; if that empties the rule, it is skipped."""
    where = f"rules[{idx}]"
    if not isinstance(raw, dict):
        log.error("config: %s must be an object - skipped", where)
        return None
    name = raw["name"] if isinstance(raw.get("name"), str) and raw.get("name") else f"rule {idx + 1}"

    between = None
    if "between" in raw:
        pair = raw["between"]
        if isinstance(pair, list) and len(pair) == 2:
            start, end = _parse_time(pair[0]), _parse_time(pair[1])
            if start is not None and end is not None:
                between = (start, end)
        if between is None:
            log.error("config: %s.between must be [\"HH:MM\", \"HH:MM\"] - rule skipped", where)
            return None

    days = None
    if "days" in raw:
        days = _parse_days(raw["days"], f"{where}.days")
        if days is _INVALID:
            log.error("config: %s.days invalid - rule skipped", where)
            return None

    unless_logged_today = None
    if "unless_logged_today" in raw:
        value = raw["unless_logged_today"]
        if isinstance(value, str) and value:
            unless_logged_today = value
        else:
            log.error("config: %s.unless_logged_today must be a non-empty string - rule skipped", where)
            return None

    actions: dict[str, Action] = {}
    for trigger in TRIGGER_TYPES:
        if trigger in raw:
            entry = raw[trigger]
            if isinstance(entry, dict) and entry.get("action") == "alarm":
                log.warning(
                    "config: %s.%s uses the removed 'alarm' action - cannot migrate a "
                    "gesture-fired alarm to a scheduled alarm mode; dropped. Re-add it as "
                    "an alarm-template mode with a schedule.", where, trigger,
                )
                continue
            action = _parse_action(entry, f"{where}.{trigger}")
            if action is not None:
                actions[trigger] = action
    if not actions:
        log.error("config: %s (%r) has no migratable gesture actions - skipped", where, name)
        return None

    if between is not None or days is not None:
        activation: Activation = WindowActivation(between=between, days=days)
    else:
        activation = AlwaysActivation()
    return Mode(
        name=name,
        behavior=ActionsBehavior(actions=actions, unless_logged_today=unless_logged_today),
        activation=activation,
    )


def _parse_modes(raw: dict) -> tuple[Mode, ...]:
    """Resolve the modes list, applying the migration ladder:
    modes (v0.3) -> rules (v0.2) -> commands (v0.1) -> built-in defaults."""
    if isinstance(raw.get("modes"), list):
        modes = tuple(
            mode
            for idx, entry in enumerate(raw["modes"])
            if (mode := _parse_mode(entry, idx)) is not None
        )
        if not modes:
            log.error("config: no valid modes - using defaults")
            return _default_modes()
        return modes

    if raw.get("modes") is not None:
        log.error("config: 'modes' must be a list - falling back to legacy/defaults")

    if isinstance(raw.get("rules"), list):
        log.info("config: legacy 'rules' schema - migrating to ambient actions modes")
        modes = tuple(
            mode
            for idx, entry in enumerate(raw["rules"])
            if (mode := _migrate_rule(entry, idx)) is not None
        )
        if not modes:
            log.error("config: no migratable rules - using defaults")
            return _default_modes()
        return modes

    if raw.get("rules") is not None:
        log.error("config: 'rules' must be a list - using defaults")

    if isinstance(raw.get("commands"), dict):
        # Legacy v0.1 schema: commands become a single default actions mode.
        log.info("config: legacy 'commands' schema - treating as one default mode")
        mode = _migrate_rule({"name": "Default", **raw["commands"]}, 0)
        if mode is not None:
            return (mode,)
        log.error("config: legacy commands had no valid actions - using defaults")

    return _default_modes()


def parse_config(raw: dict) -> AppConfig:
    """Validate a raw config object. Never raises - bad keys fall back
    per-key with a logged warning/error. Also the validation path for
    configs submitted through the web API."""
    defaults = AppConfig()
    known = {
        "ollama_host", "local_ollama_host", "local_model", "remote_model",
        "prefer_remote", "fallback_to_local", "remote_timeout_s",
        "local_timeout_s", "ble_device_name", "sounds_enabled",
        "database_path", "web_enabled", "web_host", "web_port",
        "modes", "rules", "commands",
    }
    for key in raw:
        if key not in known:
            log.warning("config: unknown key %r - ignored", key)

    return AppConfig(
        ollama_host=_take(raw, "ollama_host", str, defaults.ollama_host),
        local_ollama_host=_take(raw, "local_ollama_host", str, defaults.local_ollama_host),
        local_model=_take(raw, "local_model", str, defaults.local_model),
        remote_model=_take(raw, "remote_model", str, defaults.remote_model),
        prefer_remote=_take(raw, "prefer_remote", bool, defaults.prefer_remote),
        fallback_to_local=_take(raw, "fallback_to_local", bool, defaults.fallback_to_local),
        remote_timeout_s=_take(raw, "remote_timeout_s", float, defaults.remote_timeout_s),
        local_timeout_s=_take(raw, "local_timeout_s", float, defaults.local_timeout_s),
        ble_device_name=_take(raw, "ble_device_name", str, defaults.ble_device_name),
        sounds_enabled=_take(raw, "sounds_enabled", bool, defaults.sounds_enabled),
        database_path=_take(raw, "database_path", str, defaults.database_path),
        web_enabled=_take(raw, "web_enabled", bool, defaults.web_enabled),
        web_host=_take(raw, "web_host", str, defaults.web_host),
        web_port=_take(raw, "web_port", int, defaults.web_port),
        modes=_parse_modes(raw),
    )


def load_config(path: str) -> AppConfig:
    """Load config from `path`. Never raises - bad input falls back per-key."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        log.warning("config: %s not found - using built-in defaults", path)
        return AppConfig()
    except (OSError, json.JSONDecodeError) as exc:
        log.error("config: cannot read %s (%s) - using built-in defaults", path, exc)
        return AppConfig()

    if not isinstance(raw, dict):
        log.error("config: top level of %s is not an object - using defaults", path)
        return AppConfig()

    return parse_config(raw)


def _action_to_dict(action: Action) -> dict:
    if isinstance(action, PromptAction):
        return {"action": "prompt", "prompt": action.prompt, "label": action.label}
    if isinstance(action, LogAction):
        return {"action": "log", "event": action.event}
    if isinstance(action, TimerToggleAction):
        return {"action": "timer_toggle", "log_as": action.log_as}
    if isinstance(action, WebhookAction):
        return {"action": "webhook", "url": action.url, "payload": action.payload}
    if isinstance(action, EnterModeAction):
        return {"action": "enter_mode", "target": action.target}
    raise TypeError(f"unknown action type {type(action).__name__}")


def _activation_to_dict(activation: Activation) -> dict:
    if isinstance(activation, AlwaysActivation):
        return {"type": "always"}
    if isinstance(activation, ManualActivation):
        return {"type": "manual"}
    if isinstance(activation, WindowActivation):
        entry: dict = {"type": "window"}
        if activation.between is not None:
            entry["between"] = [t.strftime("%H:%M") for t in activation.between]
        if activation.days is not None:
            entry["days"] = [_DAY_NAMES[i] for i in sorted(activation.days)]
        return entry
    if isinstance(activation, ScheduleActivation):
        entry = {"type": "schedule", "at": activation.at.strftime("%H:%M")}
        if activation.days is not None:
            entry["days"] = [_DAY_NAMES[i] for i in sorted(activation.days)]
        return entry
    raise TypeError(f"unknown activation type {type(activation).__name__}")


def _mode_to_dict(mode: Mode) -> dict:
    entry: dict = {
        "name": mode.name,
        "template": mode.template,
        "activation": _activation_to_dict(mode.activation),
    }
    if isinstance(mode.behavior, ActionsBehavior):
        if mode.behavior.unless_logged_today is not None:
            entry["unless_logged_today"] = mode.behavior.unless_logged_today
        for trigger, action in mode.behavior.actions.items():
            entry[trigger] = _action_to_dict(action)
    elif isinstance(mode.behavior, AlarmBehavior):
        entry["message"] = mode.behavior.message
        entry["label"] = mode.behavior.label
        entry["snooze_minutes"] = mode.behavior.snooze_minutes
        entry["dismiss_event"] = mode.behavior.dismiss_event
    elif isinstance(mode.behavior, StopwatchBehavior):
        entry["log_as"] = mode.behavior.log_as
    elif isinstance(mode.behavior, CounterBehavior):
        entry["event"] = mode.behavior.event
    return entry


def as_dict(cfg: AppConfig) -> dict:
    """JSON-ready view of an AppConfig. Round-trips: the output is valid
    input for parse_config, so the web UI can edit the effective config.

    Only activation fields that are set are emitted; a window with neither
    bound is never produced (migration picks `always` instead)."""
    return {
        "ollama_host": cfg.ollama_host,
        "local_ollama_host": cfg.local_ollama_host,
        "local_model": cfg.local_model,
        "remote_model": cfg.remote_model,
        "prefer_remote": cfg.prefer_remote,
        "fallback_to_local": cfg.fallback_to_local,
        "remote_timeout_s": cfg.remote_timeout_s,
        "local_timeout_s": cfg.local_timeout_s,
        "ble_device_name": cfg.ble_device_name,
        "sounds_enabled": cfg.sounds_enabled,
        "database_path": cfg.database_path,
        "web_enabled": cfg.web_enabled,
        "web_host": cfg.web_host,
        "web_port": cfg.web_port,
        "modes": [_mode_to_dict(mode) for mode in cfg.modes],
    }


class ConfigManager:
    """Holds the live AppConfig; reload() re-reads the file (SIGHUP hook)."""

    def __init__(self, path: str | None = None):
        self._path = path or os.environ.get("AIBUTTON_CONFIG", DEFAULT_CONFIG_PATH)
        self._config = load_config(self._path)

    @property
    def path(self) -> str:
        return self._path

    @property
    def config(self) -> AppConfig:
        return self._config

    def reload(self) -> None:
        self._config = load_config(self._path)
        log.info("config reloaded from %s", self._path)
