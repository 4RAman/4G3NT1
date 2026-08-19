"""Hot/Cold: stop a spinning hue wheel as close to a hidden target as you can.

Pure by construction - no clock, no device, no store, no config, and no
asyncio. `step` is a total function over `(game, event, now)` returning the
next game and what the driver should do about it, which is the shape
[ROADMAP.md](../ROADMAP.md)'s Stage-3 runtime wants every app to be in. The
driver in [main.py](main.py) is the only part that awaits anything.

That is not decoration. It is the whole reason this file exists separately:
everything below is exercised by [test_hotcold.py](../tests/test_hotcold.py)
with plain numbers and no mocks, and when the runtime moves onto the device
this half moves unchanged.

**Why the host can know where the wheel is.** The sweep is one `rainbow`
effect pushed at the device, and [firmware/led.py](../firmware/led.py)'s
`_rainbow` starts its hue at whatever moment the effect arrives - so phase 0
is the push, and the phase at any later instant is arithmetic rather than a
guess. That is what makes this game possible without streaming a colour per
frame down the radio: one write per round.

**Why a press has to be dated earlier than it arrives.** A real button holds a
single press back until the multi-tap window closes, so the finger moved before
the gesture landed. How much before is `Game.latency_s`, which the driver fills
in from `ButtonDevice.press_latency_s` - a number this module is *told* rather
than one it knows, because a game that hardcoded a firmware constant would be
wrong on every other way of delivering a press (an injected one is instant) and
would not survive the move onto the device.

Subtracting it works because it is a *constant*, not jitter. What is left over
- radio and scheduling, tens of milliseconds - is the real precision floor, and
the reason `tolerance` is not tighter by default.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


# --- what the driver should do ---------------------------------------------
# A small closed set, in the spirit of the Stage-3 effect list. Deliberately
# not the global one: inventing that is Stage-3 work and ROADMAP.md is explicit
# that no Stage-3 refactor may block Stage 2. These are the four things this
# game asks of the world, named so a test can assert them without a device.


@dataclass(frozen=True)
class Spin:
    """Start the wheel. One rainbow effect, one radio write, no follow-ups."""

    period_s: float


@dataclass(frozen=True)
class Reveal:
    """Show how close the guess was, then hold it there long enough to read."""

    closeness: float  # 0.0 = as far as it gets, 1.0 = dead on
    hit: bool
    hold_s: float


@dataclass(frozen=True)
class Score:
    """Log the guess. Carries closeness so the value column gets a number."""

    closeness: float


@dataclass(frozen=True)
class Leave:
    """The game is over - hand this message back as the takeover's result."""

    message: str


Effect = Spin | Reveal | Score | Leave

# --- events ----------------------------------------------------------------
# Named rather than reusing TriggerType, because two of them are not gestures:
# START is entering the app and NEXT is the reveal having been on screen long
# enough. Keeping them in one vocabulary is what lets `step` be total.

START = "start"
GUESS = "guess"  # short press or double tap - the wheel stops here
NEXT = "next"  # the reveal has been shown; deal the next round
LEAVE = "leave"  # long press, or shutting down


@dataclass(frozen=True)
class Game:
    """A session. Frozen: `step` returns a new one rather than mutating."""

    sweep_s: float
    rounds: int  # 0 = keep dealing until you leave
    tolerance: float
    reveal_s: float
    latency_s: float = 0.0  # how late this device's gestures arrive
    target: float = 0.0  # 0..1, where on the wheel the hidden target sits
    spun_at: float = 0.0  # when the sweep effect went out
    played: int = 0
    hits: int = 0
    best: float | None = None
    over: bool = False


def phase_at(
    spun_at: float, now: float, sweep_s: float, latency_s: float = 0.0
) -> float:
    """Where the wheel was when the finger actually went down, as 0..1.

    Total: a non-positive sweep is a wheel that never moved, which is 0 rather
    than a division by zero. A press dated *before* the spin - possible when
    the latency correction is larger than the time actually elapsed, i.e. a
    press already in flight as the round began - wraps backwards rather than
    going negative, which is what a wheel does.
    """
    if sweep_s <= 0:
        return 0.0
    return ((now - latency_s - spun_at) % sweep_s) / sweep_s


def distance(phase: float, target: float) -> float:
    """How far apart two points on the wheel are, as 0..1.

    Normalised so that 1.0 is *half a turn* - the furthest two points on a
    circle can be. Scaling it that way is what lets `tolerance` and the reveal
    ramp both read as plain "how wrong were you" fractions, instead of topping
    out at 0.5 and needing every consumer to remember why.
    """
    raw = abs(phase - target) % 1.0
    return min(raw, 1.0 - raw) * 2.0


def closeness(phase: float, target: float) -> float:
    """1.0 is dead on, 0.0 is as wrong as the wheel allows."""
    return 1.0 - distance(phase, target)


def summary(game: Game) -> str:
    if not game.played:
        return "hot/cold - no guesses"
    best = f", best {round((game.best or 0.0) * 100)}%"
    return f"hot/cold - {game.hits}/{game.played} on target{best}"


def step(
    game: Game, event: str, now: float, next_target: float = 0.0
) -> tuple[Game, tuple[Effect, ...]]:
    """Advance the game. Total, pure, and free of anything that ticks.

    `next_target` is where the *next* round's target will sit. It is passed in
    on every call rather than drawn here because randomness is I/O by another
    name - a step function that rolled its own dice could not be checked
    against a table. The driver supplies a fresh number each time and it is
    simply unused unless a round actually starts.
    """
    if game.over:
        return game, ()

    if event == START:
        return replace(game, target=next_target, spun_at=now), (Spin(game.sweep_s),)

    if event == GUESS:
        got = closeness(
            phase_at(game.spun_at, now, game.sweep_s, game.latency_s), game.target
        )
        hit = (1.0 - got) <= game.tolerance
        played = game.played + 1
        game = replace(
            game,
            played=played,
            hits=game.hits + (1 if hit else 0),
            best=got if game.best is None else max(game.best, got),
        )
        effects: tuple[Effect, ...] = (
            Score(got),
            Reveal(got, hit, game.reveal_s),
        )
        # A fixed number of rounds ends the session itself; `rounds: 0` is the
        # default and means the only way out is the long press, which is what
        # every other takeover does.
        if game.rounds and played >= game.rounds:
            game = replace(game, over=True)
            effects += (Leave(summary(game)),)
        return game, effects

    if event == NEXT:
        return replace(game, target=next_target, spun_at=now), (Spin(game.sweep_s),)

    if event == LEAVE:
        game = replace(game, over=True)
        return game, (Leave(summary(game)),)

    return game, ()
