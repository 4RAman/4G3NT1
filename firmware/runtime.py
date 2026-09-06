# The app runtime: one step function, and nothing else.
#
# ARCHITECTURE.md lists eight things that run on the device; this is number
# three, in the smallest form that is still the real thing. It is deliberately
# the same shape as rules.py and trigger.py - pure, total, no clock of its own:
#
#     step(app, state, kind, param) -> (next state, ops to run)
#
# **Pure means the host suite drives it directly**, which is why there is no
# second implementation to keep in step. ARCHITECTURE.md anticipates two
# interpreters guarded by a conformance suite; until the web UI grows one in
# JavaScript, one file imported by both sides is strictly better than two files
# that agree today.
#
# What it cannot do yet, said plainly: there are no variables, no expressions
# and no guards. A transition matches on (event kind, parameter) and nothing
# else. That runs a light show, a gesture map and a signal light, and it does
# not run a metronome - averaging eight tap intervals needs arithmetic, and
# arithmetic is the next increment. The compiler covers the gap for anything
# countable by *unrolling* it: a show's cue ring is N states pointing at each
# other, not an index and a modulo.

from apppkg import EXIT


def entry_ops(app, state):
    """What running `state` emits on entry. Empty for a state that is not
    there, which is what makes a corrupt target survivable."""
    if state is None or state == EXIT or state >= len(app.states):
        return ()
    return app.states[state][0]


def step(app, state, kind, param):
    """One event against one state.

    Returns `(next_state, ops)`:
      - `(state, None)` when nothing matched. `None` rather than `()` because
        "no transition" and "a transition to a state that emits nothing" are
        different facts, and only the first one must leave a running timer
        alone.
      - `(target, ops)` on a match, `target` being `EXIT` for "leave the app".

    First match wins, in package order - the same rule `rules.py` applies to
    ambient modes, so a config that lists two transitions for one gesture
    behaves the same on both sides of the wire.
    """
    if state is None or state == EXIT or state >= len(app.states):
        return state, None
    for transition in app.states[state][1]:
        if transition[0] == kind and transition[1] == param:
            target = transition[2]
            if target == EXIT:
                return EXIT, ()
            if target >= len(app.states):
                # A dangling target is a compiler bug, not a user's mistake.
                # Stay put and say so rather than jumping somewhere arbitrary.
                print("app: transition to missing state", target)
                return state, None
            return target, app.states[target][0]
    return state, None
