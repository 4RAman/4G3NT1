# TODO 38's spike: can this board be a BLE HID camera remote for an iPhone?
#
# **A spike, not a feature.** It is deliberately standalone - nothing in the
# shipping firmware imports it, and the flash command in README.md lists files
# by name so it does not travel unless you send it. Item 38 has two unresolved
# design questions (how you enter and leave HID mode, and what happens when a
# phone and a PC both want the one central) and code that pre-empted them would
# be answering the wrong question first.
#
# Run it *instead of* main.py, not alongside. probe() is safe any time - it
# registers nothing - but run() must own the GATT table: main.py calls
# aioble.register_services at import, and re-registering is not something
# NimBLE promises to survive. So main.py is moved aside for the duration,
# which also makes "no host attached" literally true, which is the point.
#
#   python -m mpremote cp firmware/spike_hid.py :
#   python -m mpremote exec "import spike_hid; spike_hid.probe()"
#
#   python -m mpremote exec "import os; os.rename('main.py','main_off.py')" + reset
#   python -m mpremote exec "import spike_hid; spike_hid.run()"
#
# and to put the button back to normal afterwards:
#
#   python -m mpremote exec "import os; os.rename('main_off.py','main.py')" + reset
#
# While main.py is renamed the board boots to a bare REPL and does nothing.
# That is recoverable, never bricked - the rename back is the whole fix.
#
# **Forget the iPhone's pairing before re-testing a changed report map.** iOS
# caches the GATT database per bond, so an edited descriptor is invisible to a
# phone that already knows this device, and the symptom is the spike appearing
# to change nothing. Settings > Bluetooth > (i) > Forget This Device.
#
# What it is built to answer, in order:
#
#   1. Does the stock build actually pair and bond? Checked and expected to be
#      yes - ports/esp32/mpconfigport.h defines
#      MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING (1), in v1.25.0 and master
#      alike, against a default of 0 in extmod/modbluetooth.h. So no custom
#      firmware build. `probe()` confirms it on the board you actually have.
#   2. Does iOS accept an HID peripheral whose report characteristics are not
#      marked encrypted-only? aioble's Characteristic takes no security flags
#      (read/write/write_no_response/notify/indicate/initial/capture and
#      nothing else), so we cannot ask for them without dropping to raw
#      bluetooth.gatts_register_services. If iOS refuses, that is the escape
#      hatch, and this spike is how we find out we need it.
#   3. Does APPEARANCE alone earn the iOS 26 "keyboard connection" automation
#      trigger, or does that need a real keyboard report collection? That is
#      the only native bridge between item 38 and item 39, so it is worth
#      knowing rather than assuming. Flip APPEARANCE below and retry.
#
# Volume Up is the shutter on Apple's built-in Camera and has been since iOS 7.
# Third-party camera apps generally treat it as volume and change it instead,
# so test against Apple's Camera.

import asyncio

import aioble
import bluetooth
import hardware
from clock import now_s
from trigger import DEBOUNCE_S, HOLD_S, TriggerDetector

# Advertised separately from hardware.DEVICE_NAME on purpose: the host scans
# for "AIButton", and a spike answering to that name would be picked up by a
# running service mid-test - which looks like the phone failing to connect.
HID_NAME = "AIButton Cam"

# 0x03C1 Keyboard, 0x03C0 Generic HID. Keyboard is the default because item 38
# wants the Shortcuts trigger tested; question 3 above is whether it is enough.
APPEARANCE = 0x03C1

_ADV_INTERVAL_US = 250_000

# Consumer Control: eight one-bit buttons, all single-byte usages from page
# 0x0C so the report stays one byte. Bit 0 is Volume Up, which is the shutter.
# A Report ID is declared because the Report Reference descriptor below names
# one; the ID travels in that descriptor, never in the value we notify.
_REPORT_MAP = bytes(
    (
        0x05, 0x0C,  # Usage Page (Consumer)
        0x09, 0x01,  # Usage (Consumer Control)
        0xA1, 0x01,  # Collection (Application)
        0x85, 0x01,  #   Report ID (1)
        0x15, 0x00,  #   Logical Minimum (0)
        0x25, 0x01,  #   Logical Maximum (1)
        0x75, 0x01,  #   Report Size (1 bit)
        0x95, 0x08,  #   Report Count (8)
        0x09, 0xE9,  #   Volume Increment   <- bit 0, the shutter
        0x09, 0xEA,  #   Volume Decrement
        0x09, 0xE2,  #   Mute
        0x09, 0xCD,  #   Play/Pause
        0x09, 0xB5,  #   Scan Next Track
        0x09, 0xB6,  #   Scan Previous Track
        0x09, 0xB3,  #   Fast Forward
        0x09, 0xB4,  #   Rewind
        0x81, 0x02,  #   Input (Data, Variable, Absolute)
        0xC0,        # End Collection
    )
)

_SHUTTER_BIT = 0x01
# Long enough for the host to see a distinct down and up. A real key press is
# tens of ms; going much shorter risks both edges landing in one connection
# interval and reading as no press at all.
_TAP_MS = 30

_HID_SERVICE = bluetooth.UUID(0x1812)
_BATTERY_SERVICE = bluetooth.UUID(0x180F)
_DEVICE_INFO_SERVICE = bluetooth.UUID(0x180A)


def _build_services():
    """The three services HOGP requires of a peripheral, in one registration.

    Registered together rather than added later: gatts_register_services
    replaces the whole table, so a second call would drop the first's handles.
    That is also why this is the shape item 38 would take on the real firmware
    - the HID service sits *alongside* the custom one, which is "add, don't
    repurpose" satisfied rather than worked around.
    """
    hid = aioble.Service(_HID_SERVICE)
    # HID Information: bcdHID 1.11, no country code, RemoteWake|NormallyConnectable.
    aioble.Characteristic(hid, bluetooth.UUID(0x2A4A), read=True, initial=b"\x11\x01\x00\x03")
    aioble.Characteristic(hid, bluetooth.UUID(0x2A4B), read=True, initial=_REPORT_MAP)
    # Control Point is write-without-response by spec; nothing reads it here,
    # but a host that writes Suspend to a device lacking it can drop the link.
    aioble.Characteristic(hid, bluetooth.UUID(0x2A4C), write_no_response=True, capture=True)
    report = aioble.Characteristic(
        hid, bluetooth.UUID(0x2A4D), read=True, notify=True, initial=b"\x00"
    )
    # Report Reference: (report id 1, type 1 = Input). Without this the host
    # cannot tell which report in the map this characteristic carries, and iOS
    # simply ignores the device.
    aioble.Descriptor(report, bluetooth.UUID(0x2908), read=True, initial=b"\x01\x01")

    battery = aioble.Service(_BATTERY_SERVICE)
    # HOGP requires Battery Service. A fixed 100% is honest enough for a spike
    # and a lie worth replacing before this ships.
    aioble.Characteristic(battery, bluetooth.UUID(0x2A19), read=True, notify=True, initial=b"\x64")

    info = aioble.Service(_DEVICE_INFO_SERVICE)
    # PnP ID: source 0x02 (USB IF), vendor 0xFFFF (unassigned - do not ship
    # this), product 0x0001, version 0x0001.
    aioble.Characteristic(
        info, bluetooth.UUID(0x2A50), read=True, initial=b"\x02\xff\xff\x01\x00\x01\x00"
    )

    aioble.register_services(hid, battery, info)
    return report


def probe():
    """Print what this board's build supports. No phone needed.

    Answers question 1 on the hardware in front of you rather than from what
    the MicroPython source says the build *should* have - the board runs
    whatever was flashed onto it, which may predate any of this.
    """
    import os
    import sys

    print("MicroPython:", os.uname().release, "/", os.uname().machine)
    print("impl:", sys.implementation)

    ble = bluetooth.BLE()
    ble.active(True)

    # config('bond') raises if pairing/bonding was compiled out, which is the
    # single fact that decides whether HID is possible without a custom build.
    try:
        print("bonding compiled in: yes (bond=%r, le_secure=%r, mitm=%r)"
              % (ble.config("bond"), ble.config("le_secure"), ble.config("mitm")))
    except Exception as exc:  # noqa: BLE001 - the failure *is* the answer
        print("bonding compiled in: NO -", exc)
        print("  -> HID over GATT needs a custom MicroPython build. Stop here.")

    print("BLE.gap_pair present:", hasattr(ble, "gap_pair"))

    try:
        from aioble import security  # noqa: F401
        print("aioble.security: present (bonds persist to ble_secrets.json)")
    except Exception as exc:  # noqa: BLE001
        print("aioble.security: MISSING -", exc)
        print("  -> reinstall with: python -m mpremote mip install aioble")

    print("aioble.Descriptor:", hasattr(aioble, "Descriptor"))
    ble.active(False)


async def _shutter(report, connection):
    """One shutter press: bit down, brief hold, bit up.

    The release matters. A report that never returns to zero reads as a key
    held forever, and the next press changes nothing because nothing changed.
    """
    report.write(bytes([_SHUTTER_BIT]), send_update=True)
    await asyncio.sleep_ms(_TAP_MS)
    report.write(b"\x00", send_update=True)


async def _read_button(on_gesture):
    """Debounce the pin and feed the detector.

    Lifted from main.read_button_forever deliberately unchanged in substance -
    a spike that felt different from the real button would be testing the
    wrong thing. The press is dated at the edge, not at the confirmation, for
    the reason main.py's docstring gives at length.
    """
    from machine import Pin

    pull = Pin.PULL_UP if hardware.BUTTON_PULL_UP else None
    pin = Pin(hardware.BUTTON_PIN, Pin.IN, pull)

    def is_pressed():
        return (pin.value() == 0) if hardware.BUTTON_ACTIVE_LOW else bool(pin.value())

    detector = TriggerDetector()
    stable = is_pressed()
    candidate = stable
    candidate_since = now_s()
    press_t = None
    hold_fired = False

    while True:
        now = now_s()
        raw = is_pressed()

        if raw != candidate:
            candidate = raw
            candidate_since = now
        elif raw != stable and (now - candidate_since) >= DEBOUNCE_S:
            stable = raw
            edge = candidate_since
            if stable:
                press_t = edge
                hold_fired = False
                await on_gesture(detector.on_press(edge))
            else:
                press_t = None
                event, _deadline = detector.on_release(edge)
                await on_gesture(event)

        if stable and not hold_fired and press_t is not None:
            if (now - press_t) >= HOLD_S:
                hold_fired = True
                await on_gesture(detector.on_hold(now))

        await on_gesture(detector.on_timeout(now))
        await asyncio.sleep_ms(10)


async def _main():
    try:
        from aioble import security

        # Before the stack starts, or a bond made last session is not
        # recognised this one and the phone silently re-pairs every time.
        security.load_secrets()
    except Exception as exc:  # noqa: BLE001
        print("no aioble.security:", exc, "- bonds will not persist")

    report = _build_services()
    print("advertising as", HID_NAME, "appearance 0x%04X" % APPEARANCE)
    print("pair from Settings > Bluetooth, then open Camera and press.")

    while True:
        connection = await aioble.advertise(
            _ADV_INTERVAL_US,
            name=HID_NAME,
            services=[_HID_SERVICE],
            appearance=APPEARANCE,
        )
        print("connected:", connection.device)

        # Ask for encryption rather than waiting to be asked. iOS normally
        # initiates when it touches a protected characteristic - but ours are
        # not marked encrypted-only (aioble exposes no flag for it), so a host
        # that only pairs when forced would never pair at all. If this raises,
        # that is question 2 answered and the raw-gatts escape hatch is next.
        try:
            await connection.pair()
            print("paired: encrypted=%r bonded=%r" % (connection.encrypted, connection.bonded))
        except Exception as exc:  # noqa: BLE001
            print("pair failed:", exc, "- continuing unencrypted to see if iOS minds")

        # One Event joined from both sides, rather than waiting on two tasks:
        # MicroPython's asyncio has no wait()/FIRST_COMPLETED (only run,
        # sleep, sleep_ms, wait_for, wait_for_ms and gather), and gather waits
        # for *all* of them. CPython would have accepted asyncio.wait here and
        # no host test would have caught it, because nothing on the host ever
        # imports this file - the same trap main.py sits in.
        stop = asyncio.Event()
        leaving = False

        async def on_gesture(event):
            nonlocal leaving
            if event is None:
                return
            print("gesture:", event)
            if event == "short_press":
                await _shutter(report, connection)
            elif event == "long_press":
                # Long press means "up one level" everywhere else, and there is
                # no level above HID to go to yet - so here it ends the spike,
                # which is that promise kept as far as it can be.
                print("long press - leaving HID mode")
                leaving = True
                stop.set()

        async def watch_disconnect():
            await connection.disconnected()
            stop.set()

        reader = asyncio.create_task(_read_button(on_gesture))
        watcher = asyncio.create_task(watch_disconnect())
        await stop.wait()
        reader.cancel()
        watcher.cancel()

        if leaving:
            await connection.disconnect()
            print("done - reset the board to go back to the host")
            return
        print("disconnected")


def run():
    asyncio.run(_main())
