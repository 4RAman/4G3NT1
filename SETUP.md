# AI Button — Pi Setup Guide

Target: Raspberry Pi 3B+ running Raspberry Pi OS Lite 64-bit (Bookworm),
default user `pi`, project deployed to `/home/pi/aibutton`.

## 1. Wiring

| Component | Pin | Notes |
|---|---|---|
| Button leg A | GPIO17 (physical pin 11) | momentary pushbutton |
| Button leg B | GND (physical pin 9) | internal pull-up is used — no resistor needed |
| LED red | GPIO18 (pin 12) | through 330R |
| LED green | GPIO23 (pin 16) | through 330R |
| LED blue | GPIO24 (pin 18) | through 330R |
| LED common | GND (pin 14) | **common-cathode** assumed |

Common-anode LED instead? Wire common to 3.3V and construct
`LEDController(active_high=False)` in `aibutton/main.py`.

**Optional speaker** (feedback sounds + future alarms, ~$3-4): a
PAM8302-class mono amp board + small 4-8 ohm speaker, fed from the Pi's
3.5 mm jack (tip = audio, sleeve = GND; power the amp from 5 V + GND
pins). No GPIO cost. Route audio to the jack and set a sane volume:

```bash
sudo raspi-config nonint do_audio 1   # force 3.5mm headphone jack
amixer set Master 80%
```

Without a speaker, set `"sounds_enabled": false` in the config (or
leave it — playback silently no-ops when nothing is audible).

## 2. OS packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-gpiozero python3-lgpio bluez alsa-utils
sudo timedatectl set-timezone America/Denver   # rules use local wall-clock time
```

gpiozero picks the `lgpio` pin factory automatically on Bookworm — no
RPi.GPIO needed, software PWM included.

## 3. Project + Python deps

Copy the project to `/home/pi/aibutton` (scp/rsync/git), then:

```bash
cd /home/pi/aibutton
python3 -m venv --system-site-packages .venv   # reuses apt's gpiozero/lgpio
.venv/bin/pip install httpx ollama bluez-peripheral fastapi uvicorn
# (equivalently: .venv/bin/pip install -r requirements.txt)
```

## 4. Ollama

**On the Pi** (local fallback — model MUST be pre-pulled):

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull smollm2:135m
```

> 1 GB RAM note: smollm2:135m occupies ~250-300 MB while loaded. The
> service itself stays under ~40 MB. Expect ~2-4 tokens/s on the A53.

**On the LAN server** (primary):

```bash
ollama pull llama3.2:1b
# make sure it listens beyond localhost:
#   systemd: Environment="OLLAMA_HOST=0.0.0.0" in the ollama unit, or
#   shell:   OLLAMA_HOST=0.0.0.0 ollama serve
```

## 5. Config

```bash
sudo mkdir -p /etc/aibutton
sudo cp config.json /etc/aibutton/config.json
sudo chown -R pi:pi /etc/aibutton     # lets the web UI save config edits
nano /etc/aibutton/config.json        # set ollama_host to your server's IP
```

Config errors never crash the service — invalid keys are logged and
replaced with defaults, and broken rules are skipped individually.
After edits: `sudo systemctl reload aibutton` (SIGHUP). Only
`ble_device_name` needs a full restart.

### Rules

`rules` is an ordered list, first match wins. Each rule can scope itself
with `between` (["HH:MM","HH:MM"], may cross midnight) and `days`
(["mon".."sun"]), then maps gestures to actions. A matching rule that
doesn't define the pressed gesture falls through to the next rule, so a
scoped rule can override one gesture while the default handles the rest.

The four action shapes:

```json
{ "action": "prompt",       "prompt": "…", "label": "…" }
{ "action": "log",          "event": "meds_taken" }
{ "action": "timer_toggle", "log_as": "deep_work" }
{ "action": "webhook",      "url": "https://hook.make.com/…", "payload": {"any": "json"} }
```

Webhooks POST `{"trigger", "rule", "ts"}` merged with your `payload` —
that's the entire IFTTT/Make/n8n/Home Assistant integration surface.
Log and timer events land in SQLite at `database_path` (default
`data/events.db` under the working directory); inspect with:

```bash
sqlite3 data/events.db "SELECT * FROM events ORDER BY id DESC LIMIT 20;"
```

### Web UI

While the service runs, browse to `http://<pi-address>:8080` — live
state, the rule list, a config editor with validation warnings and
hot-reload, the event log, and Simulate buttons that fire the full
pipeline without touching the hardware. The REST API behind it
(`/api/status`, `/api/config`, `/api/events`, `/api/trigger/{type}`,
docs at `/docs`) is what a future phone app should target.

There is **no authentication** — it trusts your LAN like any homelab
device. To restrict it, set `"web_host": "127.0.0.1"` (SSH-tunnel
access only), change `web_port`, or set `"web_enabled": false`.

The Dev controls section includes a **test clock** (shift what time the
rules think it is — works on the real Pi too, banner shows while
active, resets on restart) and Simulate buttons that fire the full
pipeline without touching the physical button.

## 6. Bluetooth permissions

```bash
sudo usermod -aG bluetooth pi
bluetoothctl power on        # should already be on by default
```

Log out/in (or reboot) after the group change.

## 7. On-device test sequence (in deliverable order)

```bash
cd /home/pi/aibutton

# 2. LED — watch: blue breathe, yellow, white pulse, green, red flashes
.venv/bin/python device_tests/test_led.py

# 3. Button — tap / hold / double-tap, watch printed triggers
.venv/bin/python device_tests/test_button.py

# 4. AI — mocked first (no network), then real
.venv/bin/python device_tests/test_ai.py --mock
.venv/bin/python device_tests/test_ai.py

# 6. Full app in the foreground
.venv/bin/python -m aibutton.main
```

**5. BLE test** — with the app (or service) running, on your laptop:

```
pip install bleak
python central_test/ble_central.py
```

Press the button: STATUS notifications should walk THINKING → SUCCESS →
IDLE and the full AI answer should print after reassembly.

## 8. Install the service

```bash
sudo cp aibutton.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aibutton
journalctl -u aibutton -f
```

## Troubleshooting

- **No BLE advertisement**: check `bluetoothctl show` says `Powered: yes`;
  check the service log for "BLE unavailable". D-Bus permission errors
  usually mean the `bluetooth` group change hasn't taken effect yet.
  If advertising stops after a while, some BlueZ versions expire adverts
  despite `timeout=0` — set the `Advertisement(..., 0)` timeout in
  `aibutton/ble_peripheral.py` to e.g. `180` and restart to re-register.
- **Central sees garbled/missing response text**: its negotiated MTU is
  below 183. Lower `CHUNK_SIZE` in `aibutton/ble_peripheral.py` (20 is
  universally safe).
- **Every press errors**: run `device_tests/test_ai.py` to see which
  backend is failing; check `ollama_host` in the config and that the
  remote server's `OLLAMA_HOST=0.0.0.0`.
- **LED colors wrong/inverted**: you likely have a common-anode LED —
  see §1.
- **No feedback sounds**: check `aplay -l` lists the headphone device,
  re-run the §1 audio routing commands, and confirm `sounds_enabled` is
  true. Quick hardware check: `speaker-test -t sine -f 880 -l 1`.
- **A time-scoped rule fires at the wrong hours**: the Pi's timezone is
  wrong — `timedatectl` to check, §2 to fix.
- **Web UI can't save** ("cannot write" error): `/etc/aibutton` is still
  root-owned — re-run the `chown` in §5.
- **Web UI unreachable**: check the journal for "web UI stopped" (port
  in use?) and that `web_enabled` is true; the service keeps running
  without it either way.
- **WiFi/BLE coexistence**: the device only advertises (no scanning), so
  the shared antenna is not a practical problem. Avoid adding BLE *scan*
  features to this codebase.
