"""The control panel's decisions, without a tray.

Everything asserted here is what the icon colour and the menu text are
derived from, plus the two commands the panel actually runs. tray.py itself
is not imported: it needs pystray and a display, and there is nothing in it
worth testing that is not here.
"""

import json
from pathlib import Path

from aibutton.control.status import (
    Health,
    Level,
    from_payload,
    headline,
    summary_lines,
)
from aibutton.control.supervisor import (
    Supervisor,
    flash_command,
    prefs_path,
    scene_url,
    service_command,
    status_url,
    web_url,
)

STATUS_OK = {
    "state": "IDLE",
    "device_connected": True,
    "mock": False,
    "last_mode": "Pomodoro",
    "last_message": "focus - 24:12 left",
    "store_degraded": False,
}


# --- what colour the icon is -------------------------------------------


def test_nothing_running_reads_as_stopped():
    assert Health().level is Level.STOPPED


def test_a_spawned_service_reads_as_starting_until_its_api_answers():
    # The gap between spawn and first response is seconds long; showing it as
    # a fault would make every normal start flash red.
    assert Health(process_alive=True, responding=False).level is Level.STARTING


def test_a_connected_button_reads_as_ready():
    assert from_payload(STATUS_OK, process_alive=True).level is Level.READY


def test_a_service_with_no_button_in_range_reads_as_waiting():
    payload = dict(STATUS_OK, device_connected=False)
    assert from_payload(payload, process_alive=True).level is Level.WAITING


def test_a_simulated_button_reads_as_ready_rather_than_waiting():
    # MockDevice has no radio to be disconnected from, so treating it as
    # "waiting" would leave the offline dev setup amber forever.
    payload = dict(STATUS_OK, device_connected=False, mock=True)
    health = from_payload(payload, process_alive=True)
    assert health.level is Level.READY
    assert "simulated" in headline(health)


def test_a_service_that_exited_by_itself_reads_as_a_fault():
    assert Health(exit_code=1).level is Level.FAULT
    assert "exit 1" in headline(Health(exit_code=1))


def test_a_service_that_was_asked_to_stop_is_not_a_fault():
    assert Health(exit_code=0).level is Level.STOPPED


# --- what the menu says -------------------------------------------------


def test_only_known_facts_are_shown_while_the_service_is_silent():
    # Rendering stale mode/state from a previous poll would be a confident
    # lie about a service that is no longer answering.
    lines = summary_lines(Health(process_alive=True, pid=42))
    assert lines == ["Service: Starting...  (pid 42)"]


def test_a_running_service_reports_button_state_and_last_action():
    lines = summary_lines(from_payload(STATUS_OK, process_alive=True, pid=7))
    assert lines[0] == "Service: Ready  (pid 7)"
    assert lines[1] == "Button: connected"
    assert "Pomodoro" in lines[3]
    assert "focus - 24:12 left" in lines[4]


def test_a_degraded_event_log_is_called_out_in_the_status_block():
    payload = dict(STATUS_OK, store_degraded=True)
    lines = summary_lines(from_payload(payload, process_alive=True))
    assert any("degraded" in line for line in lines)


def test_a_junk_payload_degrades_instead_of_raising():
    # The control panel watching a service must not be the thing that breaks.
    health = from_payload({"state": None, "device_connected": "yes"}, process_alive=True)
    assert health.responding is True
    assert summary_lines(health)  # renders something rather than exploding


# --- what it actually runs ----------------------------------------------


def test_the_service_command_runs_the_module_unbuffered(tmp_path):
    cfg = tmp_path / "config.json"
    argv = service_command("py.exe", cfg)
    assert argv[:4] == ["py.exe", "-u", "-m", "aibutton.main"]
    assert argv[-2:] == ["--config", str(cfg)]


def test_the_panel_starts_the_real_button_by_default(tmp_path):
    # Someone running the control panel has a button. A Start that quietly
    # launched a simulated one would look like it worked and do nothing.
    assert "--ble" in service_command("py.exe", tmp_path / "config.json")


def test_the_panel_can_be_told_to_start_a_simulated_button(tmp_path):
    argv = service_command("py.exe", tmp_path / "config.json", ble=False)
    assert "--ble" not in argv


def test_the_ble_preference_survives_a_restart(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    first = Supervisor(tmp_path, cfg)
    assert first.use_ble is True  # the default
    first.set_use_ble(False)
    first.close()

    assert Supervisor(tmp_path, cfg).use_ble is False


def test_panel_preferences_live_beside_the_config_not_inside_it(tmp_path):
    # config.json is the service's, is hot-reloaded, and is rewritten
    # wholesale by the web UI's editor - a panel setting stored there would
    # not survive a Save.
    cfg = tmp_path / "config.json"
    cfg.write_text('{"web_port": 8080}', encoding="utf-8")
    sup = Supervisor(tmp_path, cfg)
    sup.set_use_ble(False)
    sup.close()
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"web_port": 8080}
    assert prefs_path(cfg).exists()


def test_corrupt_panel_preferences_fall_back_to_defaults(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    prefs_path(cfg).write_text("{not json", encoding="utf-8")
    sup = Supervisor(tmp_path, cfg)
    try:
        assert sup.use_ble is True
    finally:
        sup.close()


def test_the_flash_command_lists_every_firmware_module_explicitly(tmp_path):
    # The shell is not involved, so a "firmware/*.py" glob would reach
    # mpremote as a literal and copy nothing.
    firmware = tmp_path / "firmware"
    firmware.mkdir()
    for name in ("main.py", "protocol.py", "led.py"):
        (firmware / name).write_text("", encoding="utf-8")
    (firmware / "README.md").write_text("", encoding="utf-8")

    argv = flash_command("py.exe", tmp_path)
    assert argv[:4] == ["py.exe", "-m", "mpremote", "cp"]
    assert argv[4:] == ["firmware/led.py", "firmware/main.py", "firmware/protocol.py",
                        ":", "+", "reset"]
    assert not any("README" in arg for arg in argv)


def test_the_real_firmware_tree_is_what_would_be_flashed():
    # Guards against the panel silently skipping a module someone adds.
    root = Path(__file__).resolve().parent.parent
    argv = flash_command("py.exe", root)
    copied = {a.removeprefix("firmware/") for a in argv if a.startswith("firmware/")}
    assert copied == {p.name for p in (root / "firmware").glob("*.py")}
    assert "main.py" in copied and "protocol.py" in copied


# --- where it looks for the service -------------------------------------


def _config(tmp_path, **body) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_a_wildcard_listen_address_is_dialled_as_localhost(tmp_path):
    # 0.0.0.0 means "listen on everything"; it is not an address to connect to.
    cfg = _config(tmp_path, web_host="0.0.0.0", web_port=8080)
    assert status_url(cfg) == "http://127.0.0.1:8080/api/status"
    assert web_url(cfg) == "http://127.0.0.1:8080/"


def test_a_service_with_the_web_ui_switched_off_has_no_status_url(tmp_path):
    assert status_url(_config(tmp_path, web_enabled=False)) is None
    assert web_url(_config(tmp_path, web_enabled=False)) is None


def test_an_unreadable_config_falls_back_instead_of_raising(tmp_path):
    # load_config never raises, and the panel must not be the first thing to.
    bad = tmp_path / "config.json"
    bad.write_text("{not json", encoding="utf-8")
    assert status_url(bad) == "http://127.0.0.1:8080/api/status"


# --- scenes, from the panel's side --------------------------------------


def _scene_config(tmp_path, active="focus", web_enabled=False):
    """A config pointing at two scenes beside it.

    The web UI is off by default so `switch_scene` has no URL to try: these
    tests are about the offline path, and a config that dialled the default
    port could reach a real service on this machine and switch *its* scene.
    """
    scenes_dir = tmp_path / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    (scenes_dir / "focus.json").write_text(
        json.dumps({"name": "Deep Focus", "modes": []}), encoding="utf-8"
    )
    (scenes_dir / "kitchen.json").write_text(
        json.dumps({"name": "Kitchen", "modes": []}), encoding="utf-8"
    )
    return _config(
        tmp_path, web_enabled=web_enabled, scenes={"dir": "scenes", "active": active}
    )


def test_the_scene_list_is_read_from_files_so_it_works_while_stopped(tmp_path):
    sup = Supervisor(tmp_path, _scene_config(tmp_path))

    entries, active = sup.scene_state()

    assert [e.name for e in entries] == ["Deep Focus", "Kitchen"]
    assert active == "focus"


def test_the_scene_list_is_cached_between_polls(tmp_path):
    # The tray polls once a second and this reads every scene file.
    config = _scene_config(tmp_path)
    sup = Supervisor(tmp_path, config)
    sup.scene_state(now=100.0)

    (config.parent / "scenes" / "late.json").write_text(
        json.dumps({"name": "Late", "modes": []}), encoding="utf-8"
    )

    assert len(sup.scene_state(now=101.0)[0]) == 2  # still the cached read
    assert len(sup.scene_state(now=110.0)[0]) == 3  # past the TTL


def test_switching_with_nothing_running_moves_the_pointer_for_the_next_start(tmp_path):
    config = _scene_config(tmp_path)
    sup = Supervisor(tmp_path, config)

    assert sup.switch_scene("kitchen") is True

    assert json.loads(config.read_text(encoding="utf-8"))["scenes"]["active"] == "kitchen"
    assert "applies at next start" in sup.log_text()


def test_switching_to_no_scene_clears_the_pointer(tmp_path):
    config = _scene_config(tmp_path)
    sup = Supervisor(tmp_path, config)

    sup.switch_scene(None)

    assert "active" not in json.loads(config.read_text(encoding="utf-8"))["scenes"]


def test_a_switch_invalidates_the_cached_list(tmp_path):
    config = _scene_config(tmp_path)
    sup = Supervisor(tmp_path, config)
    sup.scene_state(now=100.0)

    sup.switch_scene("kitchen")

    assert sup.scene_state(now=100.0)[1] == "kitchen"


def test_switching_an_unwritable_config_reports_instead_of_raising(tmp_path):
    config = tmp_path / "config.json"
    config.write_text("{not json", encoding="utf-8")
    sup = Supervisor(tmp_path, config)

    assert sup.switch_scene("focus") is False
    assert "could not switch scene" in sup.log_text()


def test_the_scene_activate_url_is_derived_from_the_config(tmp_path):
    cfg = _scene_config(tmp_path, web_enabled=True)  # string building only, no request
    assert scene_url(cfg, "kitchen") == "http://127.0.0.1:8080/api/scenes/kitchen/activate"
    assert scene_url(cfg, None) == "http://127.0.0.1:8080/api/scenes/none/activate"


def test_a_scene_name_with_a_space_is_escaped_into_the_url(tmp_path):
    cfg = _scene_config(tmp_path, web_enabled=True)
    assert scene_url(cfg, "My Focus").endswith("/api/scenes/My%20Focus/activate")


def test_no_web_ui_means_no_scene_url_and_the_file_path_instead(tmp_path):
    config = _config(tmp_path, web_enabled=False, scenes={"dir": "scenes", "active": "focus"})
    (tmp_path / "scenes").mkdir(exist_ok=True)
    sup = Supervisor(tmp_path, config)

    assert scene_url(config, "kitchen") is None
    assert sup.switch_scene("kitchen") is True  # still switches, via the file
