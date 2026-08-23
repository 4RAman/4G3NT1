"""The `keys` action: what a chord may say, and what happens when it cannot."""

import pytest

from aibutton import keys, keys_io
from aibutton.actions import execute
from aibutton.config import KeysAction, parse_with_warnings


# --- the vocabulary ------------------------------------------------------
#
# One table rather than a case each: the interesting thing is the shape of
# what is accepted, and a table shows the boundary in one screen.

@pytest.mark.parametrize("text, expected", [
    # plain keys
    ("a", ((), "a")),
    ("f12", ((), "f12")),
    ("playpause", ((), "playpause")),
    ("volumeup", ((), "volumeup")),
    # modifiers, in order, and case-folded
    ("ctrl+p", (("ctrl",), "p")),
    ("CTRL+Shift+P", (("ctrl", "shift"), "p")),
    ("ctrl+alt+win+shift+delete", (("ctrl", "alt", "win", "shift"), "delete")),
    ("  ctrl + p  ", (("ctrl",), "p")),
    # refused
    ("", None),
    ("   ", None),
    ("ctrl", None),           # a modifier is not a key
    ("ctrl+", None),          # dangling separator
    ("a+b", None),            # two keys
    ("p+ctrl", None),         # modifier after the key
    ("ctrl+ctrl+a", None),    # repeated modifier
    ("hyper+a", None),        # unknown modifier
    ("f25", None),            # off the end of the function keys
    ("волюм", None),          # not in the vocabulary
])
def test_a_chord_is_spelled_modifiers_then_one_key(text, expected):
    assert keys.parse_combo(text) == expected


def test_every_key_the_vocabulary_offers_can_actually_be_pressed():
    """The two tables are mirrored by hand, so drift is a real possibility:
    a name in `KEYS` with no virtual-key code would parse at load time and
    then fail at the moment somebody pressed the button."""
    missing = [k for k in keys.KEYS + keys.MODIFIERS if k not in keys_io._VK]
    assert missing == []


def test_media_keys_come_first_because_they_are_the_ones_that_work_unfocused():
    # Not decoration: everything else needs the right window in front, which
    # is the caveat the editor hint leads with.
    assert keys.KEYS[:len(keys.MEDIA_KEYS)] == keys.MEDIA_KEYS


# --- parsing a config ----------------------------------------------------

def _action(raw):
    """Parse one binding, with a second valid one beside it.

    The spare binding is load-bearing: a mode whose every gesture is dropped
    is itself skipped, and a config with no valid modes falls back to the
    defaults - so without it this helper would hand back the *default* Home
    and the assertions below would be measuring the wrong object.
    """
    cfg, warnings = parse_with_warnings({
        "modes": [{
            "name": "Home", "template": "actions",
            "activation": {"type": "always"},
            "short_press": raw,
            "long_press": {"action": "log", "event": "still_here"},
        }],
    })
    assert cfg.modes[0].name == "Home", "fell back to defaults"
    return cfg.modes[0].behavior.actions.get("short_press"), warnings


def test_a_chord_and_a_click_both_survive_a_round_trip():
    action, warnings = _action({"action": "keys", "combo": "ctrl+shift+p",
                                "click": "double"})
    assert action == KeysAction(combo="ctrl+shift+p", click="double")
    assert not warnings


def test_a_click_alone_is_a_whole_action():
    action, _ = _action({"action": "keys", "click": "left"})
    assert action == KeysAction(combo="", click="left")


@pytest.mark.parametrize("raw, why", [
    ({"action": "keys"}, "neither a chord nor a click"),
    ({"action": "keys", "combo": "", "click": ""}, "both blank"),
    ({"action": "keys", "combo": "ctrl+nope"}, "key not in the vocabulary"),
    ({"action": "keys", "click": "quadruple"}, "click not in CLICKS"),
    ({"action": "keys", "combo": 7}, "not a string"),
])
def test_a_chord_this_build_cannot_press_is_refused_at_parse_time(raw, why):
    """Refused when the config loads, not when the button is pressed - the
    editor can show a warning and nobody can show a keystroke that did not
    happen. The mode survives; only the binding is dropped."""
    action, warnings = _action(raw)
    assert action is None, why
    assert warnings



# --- dispatch ------------------------------------------------------------

async def test_a_missing_backend_fails_the_action_and_nothing_else(monkeypatch):
    """On a host that cannot synthesize input the action reports failure the
    way a webhook 500 does. It must not raise: `execute` is called from the
    run loop and from a mode's hooks, and neither may die over a keystroke."""
    monkeypatch.setattr(keys_io, "_BACKEND", None)
    result = await execute(KeysAction(combo="ctrl+p", click=""),
                           trigger="short_press", mode_name="Home", store=None)
    assert not result.ok
    assert "windows-only" in result.message.lower()


async def test_a_pressed_chord_reports_what_it_pressed(monkeypatch):
    pressed = []

    class _Fake:
        name = "fake"

        def chord(self, modifiers, key):
            pressed.append(("chord", modifiers, key))

        def click(self, which):
            pressed.append(("click", which))

    monkeypatch.setattr(keys_io, "_BACKEND", _Fake())
    result = await execute(KeysAction(combo="ctrl+shift+p", click="double"),
                           trigger="short_press", mode_name="Home", store=None)
    assert result.ok
    assert pressed == [("chord", ("ctrl", "shift"), "p"), ("click", "double")]
    assert "ctrl+shift+p" in result.message


async def test_a_backend_that_throws_is_reported_not_raised(monkeypatch):
    class _Angry:
        name = "angry"

        def chord(self, modifiers, key):
            raise OSError("the window said no")

        def click(self, which):  # pragma: no cover - not reached
            raise AssertionError

    monkeypatch.setattr(keys_io, "_BACKEND", _Angry())
    result = await execute(KeysAction(combo="ctrl+p", click=""),
                           trigger="short_press", mode_name="Home", store=None)
    assert not result.ok
    assert "the window said no" in result.message
