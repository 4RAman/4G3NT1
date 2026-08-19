"""The panel's "show yourself" channel, and the states it has to tell apart.

This exists because of a real wedge: the panel held its lock, put up a modal
dialog parented to a withdrawn root - so invisible and undismissable - and told
anyone who launched it again to go and look for a tray icon that Windows had
filed away in the hidden overflow. Three different things all looked like
"already running".

So what is worth asserting is not that a socket works, but that the three
outcomes stay distinguishable: someone answered, nobody is there, and someone
is there but wedged.
"""

import socket
import threading

from aibutton.control.beacon import Beacon, ask_to_show, port_path


def test_a_running_panel_answers_and_shows_itself(tmp_path):
    config = tmp_path / "config.json"
    shown = threading.Event()
    beacon = Beacon(config, shown.set)
    beacon.start()
    try:
        assert ask_to_show(config) is True
        assert shown.wait(timeout=2.0), "the panel was asked but never shown"
    finally:
        beacon.stop()


def test_no_panel_at_all_is_not_an_answer(tmp_path):
    """No port file: nothing has ever run here."""
    assert ask_to_show(tmp_path / "config.json") is False


def test_a_stale_port_file_is_not_an_answer(tmp_path):
    """The holder crashed, so its port file survived it. Connecting is what
    settles this - the file alone proves nothing, which is exactly why the
    old PID-file thinking was not enough."""
    config = tmp_path / "config.json"
    # A port nobody is listening on. Bind and close to get one that is
    # plausible and free, rather than guessing a number.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead = probe.getsockname()[1]
    port_path(config).write_text(str(dead), encoding="ascii")

    assert ask_to_show(config) is False


def test_a_corrupt_port_file_is_not_an_answer(tmp_path):
    config = tmp_path / "config.json"
    port_path(config).write_text("not a port", encoding="ascii")
    assert ask_to_show(config) is False


def test_stopping_removes_the_port_file(tmp_path):
    """A clean exit must not leave something behind that makes the next launch
    think a wedged panel is running."""
    config = tmp_path / "config.json"
    beacon = Beacon(config, lambda: None)
    beacon.start()
    assert port_path(config).exists()
    beacon.stop()
    assert not port_path(config).exists()
    assert ask_to_show(config) is False


def test_a_beacon_that_cannot_write_its_port_still_lets_the_panel_run(tmp_path):
    """Best-effort by construction: a panel that refused to start because its
    convenience socket failed would be a worse bug than the one this fixes."""
    unwritable = tmp_path / "no-such-dir" / "config.json"
    beacon = Beacon(unwritable, lambda: None)
    beacon.start()  # must not raise
    try:
        assert ask_to_show(unwritable) is False
    finally:
        beacon.stop()


def test_it_only_answers_its_own_word(tmp_path):
    """Not a general-purpose channel. Anything else gets nothing back, which
    is what keeps this from quietly growing into an IPC protocol."""
    config = tmp_path / "config.json"
    called = threading.Event()
    beacon = Beacon(config, called.set)
    beacon.start()
    try:
        port = int(port_path(config).read_text(encoding="ascii"))
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as conn:
            conn.sendall(b"quit")
            conn.settimeout(1.0)
            try:
                assert conn.recv(8) == b""
            except socket.timeout:
                pass  # no reply is the same answer
        assert not called.is_set(), "an unknown word must not show the window"
    finally:
        beacon.stop()
