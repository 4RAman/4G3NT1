# Running an app with nobody attached.
#
# The runtime is pure (runtime.py) and the package is data (apppkg.py); this is
# the small amount of glue that gives them a clock and a light. It owns three
# things and no more: which state the app is in, when its timer is due, and
# whether the shell around it is awake.
#
# **When it runs.** Only while no central is connected. A host that is present
# still owns the button exactly as it always has - this file does not fight it,
# and with no package on flash it never exists at all. So the failure mode of
# everything here is "the button behaves the way it did last week".
#
# That is also the demo: stop the service, and the button keeps its app. It is
# ARCHITECTURE.md's first degradation row - *the device must work when the
# others are gone* - performed rather than asserted.
#
# **There is no shell.** The package's start app *is* the ambient layer - a
# menu, compiled like everything else - so this file holds no menu logic and
# knows nothing about launchers. What it owns is the one rule that has nowhere
# else to live: leaving an app returns to whatever entered it, and leaving the
# start app has nothing above it, so it sleeps. That is CLAUDE.md's "up one
# level, and at the root up means off" arrived at from the device end, with the
# same fade the host does.
#
# **One level of return, exactly like the host.** `_return_to` is a single slot
# rather than a stack, because `return_after` is one level there too: a gesture
# always travels one rung, never one-or-two depending how you got there.

import asyncio

import apppkg
import protocol
import runtime
import sequence
from clock import now_s

# How often the timer deadline is checked. Fine enough that a cue's dwell is
# accurate to a frame, coarse enough to be free on a 240 MHz MCU. It is also
# the thing light sleep will replace (ROADMAP 3c): a deadline is knowable in
# advance, so the radio and the CPU could both be asleep until it.
_TICK_S = 0.02

# How long the light takes to go out when the shell sleeps, and what it lands
# on. Mirrors main._SLEEP_FADE_S and main._STANDBY_COLOR host-side - the same
# gesture should look the same whether or not a PC is in the room.
_SLEEP_FADE_S = 1.0
_SLEEP_COLOR = (0, 0, 0)


def event_for(gesture):
    """A trigger.py gesture name -> (event kind, parameter), or None.

    One place, so the package format and the detector cannot drift apart on
    what "double tap" is called. Hold levels (TODO 29) arrive as a parameter
    here rather than as new names, which is why the kind carries one at all.
    """
    if gesture == "long_press":
        return apppkg.EV_HOLD, 0
    count = protocol.TAP_COUNTS.get(gesture)
    if count is None:
        return None
    return apppkg.EV_TAP, count


class Standalone:
    """One app, driven by presses and a clock."""

    def __init__(self, bundle, led, buzzer):
        self.bundle = bundle
        self._led = led
        self._buzzer = buzzer
        self._app = None        # index into bundle.apps
        self._state = None      # index into that app's states
        self._return_to = None  # who to hand back to on EXIT
        self._deadline = None
        self._asleep = False
        self._enabled = False   # set by main() when the host goes away

    @property
    def app(self):
        """The running app, or None while asleep."""
        if self._app is None:
            return None
        return self.bundle.apps[self._app]

    # --- the shell ----------------------------------------------------

    def enable(self, now=None):
        """The host is gone: take the button."""
        self._enabled = True
        self._asleep = False
        self.start(now)

    def disable(self):
        """A host connected: give it back, silently. The LED is left alone -
        whoever just connected is about to write a state anyway, and blanking
        it here would be a visible flicker on every reconnect."""
        self._enabled = False
        self._app = None
        self._state = None
        self._return_to = None
        self._deadline = None

    def load(self, bundle, now=None):
        """Replace what is installed, live.

        Called after a push lands (main.serve_package). If the app was running
        it is restarted on the new package rather than left half in the old
        one - state indices from a different bundle mean nothing, and carrying
        them over is how a runtime ends up somewhere that does not exist.
        """
        self.bundle = bundle
        if self._enabled and not self._asleep:
            self.start(now)
        else:
            self._app = None
            self._state = None
            self._return_to = None
            self._deadline = None

    def start(self, now=None):
        """Enter the ambient app - the one a press lands on with nothing else
        running, and the one a package names as its start."""
        if self.bundle is None:
            return
        self._return_to = None
        self._open(self.bundle.start, now_s() if now is None else now)

    def _open(self, index, now):
        """Hand the button to one app in the package."""
        if index >= len(self.bundle.apps):
            print("app: no app %d in this package" % index)
            return
        self._app = index
        self._enter(self.bundle.apps[index].start, now)

    def _sleep(self):
        """Fade out and stop answering. A two-stop one-shot, exactly as the
        host builds it: the first stop is a hard cut to where the light already
        is, the movement is the second."""
        self._asleep = True
        self._app = None
        self._state = None
        self._return_to = None
        self._deadline = None
        self._led.show_sequence(
            (
                (self._led.palette_color(protocol.LED_IDLE), 0.0, 0.0, 0),
                (_SLEEP_COLOR, 0.0, _SLEEP_FADE_S, sequence.CURVE_EASE_IN),
            ),
            False,
        )

    # --- events -------------------------------------------------------

    def gesture(self, name, now=None):
        """One press, while no host is listening.

        `now` is injectable for the same reason `trigger.py` takes its
        timestamps rather than reading a clock: everything here is decided by
        when things happened, and a test that cannot say when cannot assert
        anything about a dwell.
        """
        if not self._enabled or self.bundle is None:
            return
        if now is None:
            now = now_s()
        event = event_for(name)
        if event is None:
            return
        kind, param = event

        if self._asleep:
            # Only the gesture that put it to sleep brings it back, and it is
            # swallowed: waking must not also fire whatever it landed on.
            if kind == apppkg.EV_HOLD:
                self._asleep = False
                self.start(now)
            return

        state, ops = runtime.step(self.app, self._state, kind, param)
        self._apply(state, ops, now)

    def tick(self, now):
        """Fire the running state's timer if it is due.

        Split out of `run` so the host suite can drive a whole show with a
        clock it controls - the same split `trigger.py` already makes, and for
        the same reason: everything worth asserting about this file is in here,
        and none of it should need an event loop to reach.
        """
        if not self._enabled or self._state is None or self._deadline is None:
            return
        if now < self._deadline:
            return
        state, ops = runtime.step(self.app, self._state, apppkg.EV_TIMER, 0)
        self._apply(state, ops, now)

    async def run(self):
        """The clock. Nothing else in here needs a loop - a press arrives as a
        call from the button poll, which is already running."""
        while True:
            self.tick(now_s())
            await asyncio.sleep(_TICK_S)

    # --- running a state ----------------------------------------------

    def _apply(self, state, ops, now):
        if ops is None:  # nothing matched; a running timer keeps running
            return
        if state == apppkg.EXIT:
            # Up one level: back to whoever opened this app, or - if nothing
            # did, because this *is* the root - off.
            if self._return_to is None:
                self._sleep()
            else:
                target, self._return_to = self._return_to, None
                self._open(target, now)
            return
        self._enter(state, now)

    def _enter(self, state, now):
        """Run a state's entry ops. The deadline is cleared first: a state with
        no OP_TIMER is one that waits for a press, which is what "held" means
        to a light show and what every menu state is.

        **A state that shows nothing wears the button's own IDLE light.** A
        menu has no look of its own, and without this, leaving an app would
        leave that app's colour on screen - which is the host's rule too: a
        takeover ending drops back to IDLE.
        """
        self._state = state
        self._deadline = None
        ops = runtime.entry_ops(self.app, state)
        if not any(op[0] == apppkg.OP_SHOW for op in ops):
            self._led.set_state(protocol.LED_IDLE)
        for op in ops:
            kind = op[0]
            if kind == apppkg.OP_SHOW:
                self._show(op[1])
            elif kind == apppkg.OP_PLAY:
                self._buzzer.play(op[1])
            elif kind == apppkg.OP_TIMER:
                self._deadline = now + op[1]
            elif kind == apppkg.OP_ENTER:
                # Launching is the last thing a state does, so nothing after it
                # in this list can run - the app being left is already gone.
                self._return_to = self._app
                self._open(op[1], now)
                return

    def _show(self, index):
        if self.app is None or index >= len(self.app.looks):
            print("app: look %d does not exist" % index)
            return
        look = self.app.looks[index]
        if look[0] == "sequence":
            self._led.show_sequence(look[2], look[1])
        else:
            self._led.show_effect(look[1], look[2], look[3], look[4])
