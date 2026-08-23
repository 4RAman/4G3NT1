"""Reaction timer: wait for the light, press as fast as you can.

Pure by construction and shaped exactly like [hotcold.py](hotcold.py) - a
total `step` over `(game, event, now)` returning the next game and what the
driver should do about it. The two games do *not* import each other; what they
share is the constant below and the idea behind it, both taken from the same
place.

**How honest the number is.** Two corrections are possible and only one of
them is:

- However late this device's gestures arrive is known and is subtracted
  (`Game.latency_s`, filled in by the driver from
  `ButtonDevice.press_latency_s`). On a real button that is the multi-tap
  window, and without the correction every reading would be 400 ms too slow -
  more than the thing being measured.
- The one-way BLE latency between the host pushing the go signal and the
  device actually lighting up is *not* known - tens of milliseconds, varying
  with connection interval. It lands as a systematic offset on every reading.

So absolute times here are approximate, and the comparison between your own
attempts - which is what a reaction timer is actually for - is sound, because
the unknown offset is the same for all of them. Anything claiming millisecond
accuracy over this link would be lying; ARCHITECTURE.md's latency budget is
why that only gets fixed by moving the runtime onto the device.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


# --- what the driver should do ---------------------------------------------


@dataclass(frozen=True)
class Arm:
    """Go dark and wait this long before the go signal."""

    delay_s: float


@dataclass(frozen=True)
class Go:
    """Light up. The clock starts the instant this goes out."""


@dataclass(frozen=True)
class Result:
    """Show how it went. `ms` is None when the press came too early."""

    ms: float | None
    false_start: bool
    hold_s: float


@dataclass(frozen=True)
class Score:
    """Log the attempt. False starts are not scored - there is no time to log."""

    ms: float


@dataclass(frozen=True)
class Leave:
    message: str


Effect = Arm | Go | Result | Score | Leave

START = "start"
GO = "go"  # the armed delay has elapsed
PRESS = "press"
NEXT = "next"  # the result has been shown; arm the next attempt
LEAVE = "leave"


@dataclass(frozen=True)
class Game:
    rounds: int  # 0 = until you leave
    reveal_s: float
    latency_s: float = 0.0  # how late this device's gestures arrive
    lit_at: float | None = None  # when the go signal went out; None = still dark
    played: int = 0
    false_starts: int = 0
    best_ms: float | None = None
    total_ms: float = 0.0
    over: bool = False


def summary(game: Game) -> str:
    if not game.played:
        starts = f" ({game.false_starts} false starts)" if game.false_starts else ""
        return f"reaction - no times{starts}"
    average = round(game.total_ms / game.played)
    best = round(game.best_ms or 0.0)
    starts = f", {game.false_starts} false" if game.false_starts else ""
    return f"reaction - best {best} ms, average {average} ms{starts}"


def tally(game: Game) -> dict:
    """The same session as a flat bag of numbers, for an `on_exit` hook to
    carry out ([summary.py](summary.py)). Shaped exactly like
    [hotcold.py](hotcold.py)'s, and pure for the same reason.

    Zeros rather than missing keys when nothing was timed - the key set has to
    be the same on every exit because one of the carriers is positional - and
    `played` is what says whether the times mean anything. `false_starts` is
    reported even though it is not a time: it is the half of the session the
    average deliberately leaves out, so a receiver that never saw it would
    think a scrappy run was a clean one.
    """
    return {
        "played": game.played,
        "best_ms": round(game.best_ms or 0.0, 1),
        "average_ms": round(game.total_ms / game.played, 1) if game.played else 0.0,
        "false_starts": game.false_starts,
    }


def step(
    game: Game, event: str, now: float, next_delay: float = 0.0
) -> tuple[Game, tuple[Effect, ...]]:
    """Advance the game. Total and pure; `next_delay` is the driver's die roll,
    passed in for the reason hotcold.step takes `next_target`."""
    if game.over:
        return game, ()

    if event == START:
        return replace(game, lit_at=None), (Arm(next_delay),)

    if event == GO:
        # Dated at the moment the effect goes out. The device lights up a
        # radio hop later, which is the offset this cannot correct for.
        return replace(game, lit_at=now), (Go(),)

    if event == PRESS:
        pressed_at = now - game.latency_s
        # Too early - including the case where the press physically happened
        # before the light and only arrived afterwards, which is exactly what
        # the latency correction exists to catch.
        if game.lit_at is None or pressed_at < game.lit_at:
            game = replace(
                game, false_starts=game.false_starts + 1, lit_at=None
            )
            return game, (Result(None, True, game.reveal_s),)

        ms = (pressed_at - game.lit_at) * 1000.0
        played = game.played + 1
        game = replace(
            game,
            played=played,
            lit_at=None,
            total_ms=game.total_ms + ms,
            best_ms=ms if game.best_ms is None else min(game.best_ms, ms),
        )
        effects: tuple[Effect, ...] = (
            Score(ms),
            Result(ms, False, game.reveal_s),
        )
        if game.rounds and played >= game.rounds:
            game = replace(game, over=True)
            effects += (Leave(summary(game)),)
        return game, effects

    if event == NEXT:
        # Arming is its own step rather than riding along with the result,
        # because the two want opposite things from the light: a result has to
        # stay up long enough to read, and arming means going dark. Emitting
        # both at once would blank the answer before anyone saw it.
        return replace(game, lit_at=None), (Arm(next_delay),)

    if event == LEAVE:
        game = replace(game, over=True)
        return game, (Leave(summary(game)),)

    return game, ()
