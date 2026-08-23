"""What an app reports when it ends: a flat bag of numbers.

An app's result is structured data, not a sentence (ARCHITECTURE.md,
"Composition: an app's edges"). On exit a takeover hands back a flat dict of
scalars - `{"blocks": 4, "focused_s": 6000}` - and the mode's `on_exit` hook
carries it outward: merged into a webhook's JSON payload, appended to an OSC
message's arguments. `ActionResult.message` is the same result written for a
person; this is the half a machine can read, and it is what makes a hook worth
binding rather than decorative.

Pure, and deliberately so: no clock, no store, no device, no config. The whole
contract is checkable with plain dicts, and when the runtime moves onto the
device (ROADMAP Stage 3) a summary is a snapshot of the app's variables at
exit - which is already exactly this shape, so nothing here has to be
rewritten to survive the move.

**The contract is enforced, not asked for.** Flat, scalars only, bounded key
count. `clean` is the single gate every carrier goes through, for the reason
`config.flash_safe` is the single gate every look goes through: a rule each app
is trusted to remember is a rule that drifts the first time somebody writes an
app without reading this file. An app that breaks it loses the offending key
and earns a log line; it never breaks the hook, because a hook can never cost
you the app.

**An app reports the same keys on every exit, or none at all.** A summary
leaves by two doors and one of them is positional - OSC arguments are addressed
by index, so a key that appears only when the session went well silently
renumbers every argument after it. Report a zero instead, and report alongside
it the count that says whether the zero means anything (`played`, `blocks`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

# A scalar: what both carriers can express without inventing a representation.
# JSON has all four; OSC has a type tag for each (see osc._argument). Anything
# else - a list, a nested dict, a datetime, None - would have to be encoded by
# guesswork at the far end, which is the whole reason the contract says
# "scalars" rather than "whatever JSON can hold".
Scalar = bool | int | float | str

# The bound. Big enough that no app in the tree comes close (the widest reports
# four) and small enough that a summary stays something you can read in a
# webhook body. It exists to stop an app turning the exit hook into a data
# feed: a session's result is a handful of numbers, and anything wanting more
# than eight wants the event log, which is the thing that is actually built for
# volume.
MAX_KEYS = 8


def clean(raw) -> tuple[dict[str, Scalar], tuple[str, ...]]:
    """One app's reported summary, reduced to what the contract allows.

    Returns the accepted dict and the complaints about what was dropped. The
    complaints are *returned* rather than logged so this stays pure and so the
    caller can say which mode and which hook they belong to - the same split
    `parse_with_warnings` makes for a bad config, one level down.

    Keys come out **sorted by name**. That is what makes the OSC argument order
    a function of the summary's contents rather than of the order the app's
    code happened to build the dict in, and it means the two carriers agree
    about order without either of them having to sort.

    Total: anything at all may be passed in, including None (the common case -
    most apps report nothing) and something that is not a dict at all.
    """
    if not raw:
        # Nothing reported. The overwhelmingly common case and the one that has
        # to be free: an app with nothing to say must not cost a dict, a
        # warning or a key in anybody's payload.
        return {}, ()
    if not isinstance(raw, Mapping):
        return {}, (f"a summary must be a flat dict, not a {type(raw).__name__}",)

    kept: dict[str, Scalar] = {}
    complaints: list[str] = []
    # `key=str` so a dict with mixed key types still has a total order rather
    # than raising - this function is a gate, and a gate that can throw is a
    # gate that takes the app down with the bad key.
    for key in sorted(raw, key=str):
        value = raw[key]
        if not isinstance(key, str) or not key:
            complaints.append(
                f"dropped the key {key!r}: a summary is keyed by name"
            )
            continue
        if not isinstance(value, (bool, int, float, str)):
            # Nested dicts and lists land here, which is where "flat" is
            # actually enforced: there is no such thing as a deep summary that
            # merely needs flattening.
            complaints.append(
                f"dropped {key!r}: a {type(value).__name__} is not a scalar"
            )
            continue
        if isinstance(value, float) and not math.isfinite(value):
            # NaN and the infinities have no JSON spelling (a receiver either
            # rejects the body or reads back a different number) and no OSC
            # one worth sending. A division nobody guarded is a bug in the app,
            # and the honest report of it is the missing key plus this line.
            complaints.append(f"dropped {key!r}: {value} has no JSON or OSC form")
            continue
        kept[key] = value

    if len(kept) > MAX_KEYS:
        names = list(kept)
        dropped = names[MAX_KEYS:]
        complaints.append(
            f"dropped {', '.join(repr(name) for name in dropped)}: a summary "
            f"carries at most {MAX_KEYS} keys"
        )
        kept = {name: kept[name] for name in names[:MAX_KEYS]}
    return kept, tuple(complaints)


def merge(base: Mapping, session: Mapping) -> dict:
    """A webhook's payload with the session's numbers merged in.

    Flat, not nested under a "session" key: the receiving end of these is a
    rule in IFTTT or a filter node in n8n, and both are markedly happier with
    `{"blocks": 4}` than with one more level to reach through.

    **`base` wins.** Those keys - trigger, mode, ts - are the identity of the
    event rather than part of its content, and a receiver keying on them must
    not be able to be lied to by an app that happens to count something called
    "mode". The user's own payload still wins over both, which is the rule the
    webhook action already had before summaries existed.
    """
    return {**base, **{k: v for k, v in session.items() if k not in base}}


def as_args(session: Mapping) -> tuple:
    """The session's numbers as positional OSC arguments: the values, in key
    order.

    Sorted by key name rather than left in the order the app built the dict,
    because an OSC receiver addresses arguments by *index* - so the order has
    to be derivable from the summary's key names alone, by somebody reading a
    list of them rather than reading our source. `clean` already sorts; this
    sorts again so the rule holds at the point it matters and does not depend
    on which gate ran first.
    """
    return tuple(session[key] for key in sorted(session))
