"""Going and looking: what a fetched body means, and how a URL is doing.

The third source of reflexes (TODO 99). A reflex already fires from an HTTP
POST (TODO 71) and from a MIDI message (TODO 73); this one has *a clock and a
URL*, and hands what comes back to the ordinary `when` test. **A new source
builds a payload and stops there** (INVARIANTS.md) - the comparison language
already exists and the consequence vocabulary does not grow, so there is
nothing here about what a reflex *does*.

**Why a URL rather than an API** (TODO 100). Google Calendar, Outlook and
iCloud all publish a secret `.ics` URL: a plain HTTPS GET, no OAuth, no app
registration, no key, no token refresh. RSS and Atom are the same shape. That
is the whole reason this module can exist today - authenticated polling needs
the secret store TODO 96(a) has not built, and nothing here invents a
credential mechanism to work around that. If a source needs a header with a
token in it, it waits for 96(a).

**Pure, and that is load-bearing.** Nothing in here opens a socket, reads a
clock or logs a line: `read_body` is a function from (bytes-as-text, reader
name, `now`) to a payload, and `Health` is a state machine over monotonic
numbers that only ever *answers* "is this worth a log line?". The awaiting
half - one `httpx` client, one asyncio task - lives in `main.py`'s
`UrlPoller`, which is the half that assumes the host is awake and connected
and the half that gets rewritten when the brain moves to the device.

**On the iCalendar reader's honesty.** It is small on purpose and it is not a
calendar library: it unfolds lines, reads `DTSTART`, drops cancelled events
and answers "how many minutes until the next one". **It does not expand
`RRULE`.** Recurring events are *counted* into the payload as `recurring`
rather than silently ignored, because a weekly standup that never fires a
reflex is exactly the failure somebody would blame on the button. Expanding
recurrence properly is `dateutil.rrule` plus the exception rules around it -
a dependency and a week - so it is deliberately left out and left visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

# How a fetched body becomes something `ReflexTest` can read. Mirrored as the
# `readers` list on REFLEX_SOURCES' url entry in schema.js;
# test_url_reflex.py fails on drift.
READERS: tuple[str, ...] = ("json", "ics")

# Poll intervals. The default is a quarter of an hour because that is the
# useful answer for a calendar and a feed alike; the floor exists because
# somebody's calendar provider is on the other end of this and a config that
# says 0 would hammer it as fast as the event loop allows.
DEFAULT_PERIOD_MINUTES = 15.0
MIN_PERIOD_MINUTES = 1.0

# How long a dead endpoint is left alone. Backoff doubles from the configured
# period and stops here, so an hourly poll of a server that has been down all
# day still costs one request an hour rather than one a second - and still
# recovers within one period of the server coming back.
MAX_BACKOFF_S = 1800.0

# One request's budget. Longer than the webhook action's 5 s because this is
# nobody's press: a calendar export is a slow, large, redirected GET and
# there is no light waiting on it.
FETCH_TIMEOUT_S = 10.0

# A body bigger than this is a failure rather than something to parse. A busy
# year of calendar is a few hundred kilobytes; anything past two megabytes is
# an endpoint that will happily fill memory if asked politely enough.
MAX_BODY_BYTES = 2_000_000


@dataclass(frozen=True)
class Reading:
    """One attempt's outcome: a payload, or a reason there is not one.

    `error` is prose for a human reading a log line, and it is also the
    *identity* of a failure - `Health.failed` logs again when it changes, so
    "connection refused" turning into "404" is a second line and a hundred
    more refusals are not.
    """

    payload: dict | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == ""


def read_body(body: str, reader: str, now: datetime) -> Reading:
    """Shape a fetched body into a flat dict of numbers, or say why not.

    `now` is passed in rather than read, so a calendar test needs no network
    *and* no waiting: the caller hands over the host's `Clock`, which means the
    web UI's test clock fast-forwards a "ten minutes before my meeting" reflex
    exactly as it fast-forwards an alarm.

    An unknown reader falls back to JSON rather than failing, for the reason
    every other key in a config falls back individually.
    """
    if reader == "ics":
        return _read_ics(body, now)
    return _read_json(body)


def _read_json(body: str) -> Reading:
    """A JSON object is already a payload; that is the whole reader.

    A top-level *array* becomes `{"count": n}`, because "how many are there"
    is the only question a bare list can answer with one number and it is the
    question people ask of one (open incidents, queued jobs, unread items).
    Anything else is a failure with the type in it.
    """
    try:
        data = json.loads(body)
    except ValueError as exc:
        # The wrong reader is the likeliest cause of this, so say so here
        # rather than making somebody diff two config files. It costs one
        # `in` and it turns a mystery into an instruction.
        hint = " - it looks like iCalendar" if "BEGIN:VCALENDAR" in body else ""
        return Reading(error=f"not JSON: {exc}{hint}")
    if isinstance(data, dict):
        return Reading(payload=data)
    if isinstance(data, list):
        return Reading(payload={"count": len(data)})
    return Reading(error=f"JSON, but a {type(data).__name__} rather than an object")


def _read_ics(body: str, now: datetime) -> Reading:
    """`{"events": n, "recurring": n, "minutes": m}` from an iCalendar file.

    `minutes` is how long until the next event *starts*, and it is **absent
    when there is no next event**. That is not a shortcut - a test whose field
    is missing does not fire (INVARIANTS.md), so "no meetings" costs no
    special case anywhere: the reflex simply stays quiet, which is what an
    empty calendar means.

    `events` is the count of future non-recurring events and is always
    present, so it is the field to test when what you want is a zero. That is
    the same rule an app's session summary follows: report a zero, plus the
    count that says whether the zero means anything.

    `recurring` is how many events carried an `RRULE` and were therefore *not*
    considered - see the module docstring. It is in the payload so a calendar
    of nothing but weekly standups reads as `recurring: 12, events: 0` rather
    than as a calendar that is empty.
    """
    if "BEGIN:VCALENDAR" not in body.upper():
        hint = " - it looks like JSON" if body.lstrip()[:1] in "{[" else ""
        return Reading(error=f"not iCalendar (no BEGIN:VCALENDAR){hint}")
    starts: list[datetime] = []
    recurring = 0
    inside = False
    start: datetime | None = None
    repeats = False
    cancelled = False
    for line in unfold(body):
        upper = line.upper()
        if upper.startswith("BEGIN:VEVENT"):
            inside, start, repeats, cancelled = True, None, False, False
            continue
        if upper.startswith("END:VEVENT"):
            if inside and not cancelled:
                if repeats:
                    recurring += 1
                elif start is not None:
                    starts.append(start)
            inside = False
            continue
        if not inside:
            continue
        # `NAME;PARAMS:VALUE`. The first colon separates them - a value may
        # contain more (a URL in a DESCRIPTION), a property name may not.
        name, _, value = line.partition(":")
        prop, _, params = name.partition(";")
        prop = prop.strip().upper()
        if prop == "DTSTART":
            start = parse_dtstart(params, value)
        elif prop == "RRULE":
            repeats = True
        elif prop == "STATUS" and value.strip().upper() == "CANCELLED":
            cancelled = True
    future = sorted(when for when in starts if when > now)
    payload: dict = {"events": len(future), "recurring": recurring}
    if future:
        payload["minutes"] = round((future[0] - now).total_seconds() / 60.0, 2)
    return Reading(payload=payload)


def unfold(text: str) -> list[str]:
    """iCalendar's line folding, undone (RFC 5545 §3.1).

    A line longer than 75 octets is broken and the continuation begins with a
    space or a tab. Every real calendar export folds, and a folded `DTSTART`
    read a line at a time parses as two properties that are both nonsense -
    so this is not a nicety, it is the difference between reading the file and
    not.
    """
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_dtstart(params: str, value: str) -> datetime | None:
    """One `DTSTART` value as **naive local time**, or None if unreadable.

    Everything is normalised to naive local because that is what the host's
    `Clock` hands out, and one arithmetic between an aware and a naive
    datetime is a `TypeError` in the middle of a poll rather than a wrong
    answer. Three forms exist in the wild and all three appear in a Google
    export: a UTC stamp (`...Z`), a wall time with a `TZID` parameter, and an
    all-day `VALUE=DATE`, which is taken as local midnight.
    """
    value = value.strip()
    try:
        if value.endswith("Z"):
            stamp = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            # UTC -> the host's local zone -> naive. `astimezone()` with no
            # argument is the local zone, which is the one the button is in.
            return stamp.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        if "T" in value:
            stamp = datetime.strptime(value, "%Y%m%dT%H%M%S")
        else:
            stamp = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None
    zone = _zone(_param(params, "TZID"))
    if zone is not None:
        return stamp.replace(tzinfo=zone).astimezone().replace(tzinfo=None)
    # No TZID, or a zone this machine cannot name: read it as local wall time.
    # **That is a degradation, not a bug.** Windows ships no IANA time zone
    # database, so `ZoneInfo("America/Denver")` raises here unless the `tzdata`
    # package happens to be installed - and refusing the event would silence a
    # calendar reflex on the platform this project actually runs on. Local wall
    # time is exactly right whenever the calendar is in the button's own zone,
    # which is the case this feature is for.
    return stamp


def _param(params: str, key: str) -> str:
    """`;TZID=Europe/London;VALUE=DATE` -> the named parameter, or ""."""
    for part in params.split(";"):
        name, sep, value = part.partition("=")
        if sep and name.strip().upper() == key:
            return value.strip().strip('"')
    return ""


@lru_cache(maxsize=32)
def _zone(tzid: str):
    """A `ZoneInfo`, or None when this machine has never heard of it.

    Cached because the miss is the expensive path *and* the common one on
    Windows: without it, every poll of a calendar full of `TZID` events pays
    for a failed database lookup per event.
    """
    if not tzid:
        return None
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tzid)
    except Exception:  # noqa: BLE001 - any failure means "read it as local"
        return None


def backoff_s(period_s: float, failures: int) -> float:
    """How long to wait after `failures` consecutive failures.

    Doubling from the configured period, capped - and the cap is never allowed
    to *shorten* the wait, which is why it is a `max` against the period
    itself. An hourly poll that starts failing must not become a half-hourly
    one because a constant said 30 minutes.
    """
    if failures <= 1:
        return period_s
    return min(period_s * (2 ** (failures - 1)), max(MAX_BACKOFF_S, period_s))


@dataclass
class Health:
    """How one polled URL has been doing, and when it is next due.

    **This object is TODO 99's "quiet and visible" requirement, in three
    parts, and it is pure so all three are testable without a network.**

    - *It must not fire the reflex.* A failed attempt produces no payload, so
      nothing reaches the inbound queue at all - there is no "fire with the
      last known value" path to get wrong.
    - *It must not spam the log.* `failed` answers True only for the first
      failure of a run and for a **change of reason**, which is the rule
      `sync_midi_listeners` already uses for a port that will not open. Sixty
      refusals an hour are one line; a refusal that becomes a 404 is a second.
      And `next_at` backs off, so sixty attempts become a handful.
    - *It must stay findable.* `snapshot` is the whole state - failing since
      when, how many times, with what error, next attempt in how long - so
      "why did nothing happen?" has an answer that is not "read the log from
      three hours ago".

    Times are monotonic (`loop.time()`), never wall clock: a poll schedule
    that a clock change can move is a poll schedule that stops for an hour
    twice a year.
    """

    period_s: float
    next_at: float = 0.0
    # None until the first attempt, which is a third state worth having: "not
    # polled yet" is not the same answer as "working" and reporting it as one
    # is how a poller that never started looks healthy.
    ok: bool | None = None
    failures: int = 0
    error: str = ""
    since: float | None = None
    last_ok_at: float | None = None

    def due(self, now: float) -> bool:
        return now >= self.next_at

    def succeeded(self, now: float) -> bool:
        """Record a good attempt. True if this is a *recovery* worth saying."""
        recovered = self.ok is False
        self.ok = True
        self.failures = 0
        self.error = ""
        self.since = None
        self.last_ok_at = now
        self.next_at = now + self.period_s
        return recovered

    def failed(self, now: float, error: str) -> bool:
        """Record a bad attempt. True if this one is worth a log line."""
        first = self.ok is not False
        worth_saying = first or error != self.error
        self.failures += 1
        if first:
            self.since = now
        self.ok = False
        self.error = error
        self.next_at = now + backoff_s(self.period_s, self.failures)
        return worth_saying

    def snapshot(self, now: float) -> dict:
        """A flat, JSON-able answer to "what is this URL doing?"."""
        return {
            "ok": self.ok,
            "failures": self.failures,
            "error": self.error,
            "failing_for_s": None if self.since is None else round(now - self.since, 1),
            "next_in_s": round(max(0.0, self.next_at - now), 1),
            "period_s": self.period_s,
        }

    def describe(self, now: float) -> str:
        """One line for the status the web UI already shows."""
        if self.ok is None:
            return "not polled yet"
        if self.ok:
            return "ok"
        seconds = 0.0 if self.since is None else now - self.since
        return (
            f"failing for {int(seconds // 60)}m after {self.failures} "
            f"attempt(s): {self.error}"
        )
