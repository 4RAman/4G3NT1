# The phone app

A window on the running service, for iOS. It shows what the button is doing,
lists the modes, reads the log, and fires a gesture — and it decides nothing.

This is TODO **90(a)**, and the sentence above is the whole design. The full
reasoning is in [TODO.md](../TODO.md) item 90; the short version is that every
decision in this system is host-side, so an app that talked BLE to the button
directly would be a **second brain** — a Swift reimplementation of the parser,
the mode machine and every action, kept in step with Python for ever. That is
refused. When the runtime finishes moving onto the device
([ARCHITECTURE.md](../ARCHITECTURE.md), Phases D and E), this app becomes a
preferences editor and a `Request` fulfiller, which is a normal app. Everything
here is built to survive that: the REST API is the same API the phone tier
uses later.

**What it costs, said plainly: it does nothing while the PC is off.** That is
the honest price of not forking the brain, and it is the complaint item **40**
exists about. Do not fix it here.

## Layout

```
ios/
  ButtonKit/        a Swift package - models, the host seam, pure functions
    Sources/ButtonKit/
      Models.swift      /api/status, /api/config, /api/events, decoded key by key
      HostClient.swift  the seam, its HTTP implementation, and the route table
      Look.swift        what colour the light is at time t - pure, and tested
      Gestures.swift    ordering and labels, derived rather than tabled
      Samples.swift     captured bodies + PreviewHost, the MockDevice of this tier
      Decoding.swift    per-key fallback, the Swift spelling of config._take
    Tests/              swift test - no simulator, no Xcode project
  App/              the SwiftUI half: eight files, no logic worth testing
  Xcode/            not in git - the project file, recreated in five minutes
```

The split is the one this repo already uses. `ButtonKit` is the pure core plus
one I/O seam; `App/` is the part that awaits things and draws. Anything worth a
test goes in the package.

## Getting it onto the Mac

The `.xcodeproj` is deliberately **not committed** — it is a generated file
Xcode rewrites constantly, and hand-merging one is worse than recreating it.
Five minutes, once per machine:

1. Clone this repo on the Mac (`git clone …`, then `git switch <branch>`).
2. **Xcode → File → New → Project → iOS → App.**
   Product Name **Button**, Interface **SwiftUI**, Language **Swift**, Storage
   **None**, tests off. Save it into **`ios/Xcode`** — that folder is
   gitignored, so nothing Xcode generates ever collides with the sources.
3. Delete the two files Xcode made for you (`ButtonApp.swift`,
   `ContentView.swift`) — `ios/App` has the real ones. *Move to Trash*, not
   *Remove Reference*.
4. Drag the **`ios/App`** folder from Finder into the project navigator.
   **Uncheck "Copy items if needed"** — the files stay where git has them —
   and add them to the **Button** target.
5. **File → Add Package Dependencies… → Add Local…** and pick
   **`ios/ButtonKit`**. Then in the target's **General → Frameworks, Libraries
   and Embedded Content**, add **ButtonKit**.
6. Two keys in the target's **Info** tab, both required and both explained
   below:
   - **Privacy - Local Network Usage Description** →
     *"To reach the button service running on your computer."*
   - **App Transport Security Settings → Allow Local Networking** = YES.
7. Run it on a real phone rather than the simulator, on the same network as
   the PC, and type that machine's address into the setup screen.

### Why those two keys, and what to do when it still cannot connect

The service speaks plain HTTP on port 8080 and has **no authentication** — it
is a LAN service by design (`web_host` already defaults to `0.0.0.0`, so
nothing needs configuring on the PC side). iOS pushes back on that twice, and
the two failures look identical from the app:

- **Local Network privacy (iOS 14+).** The first request to a LAN address
  raises a system prompt. Decline it once and every later request fails
  silently with no second prompt — Settings → Privacy & Security → Local
  Network is the only way back.
- **App Transport Security.** *Allow Local Networking* covers `.local` names
  and link-local addresses. If a bare private IP is still refused, the fix is
  to use the machine's Bonjour name (`http://desk.local:8080`) rather than
  turning on *Allow Arbitrary Loads*.

**Off the LAN, the answer is Tailscale**, exactly as MANUAL §4.5 says for the
web UI: the app takes `http://<tailscale-name>:8080` like any other address,
and nothing is exposed publicly. Do not put this service on the open internet.

## Checks

```bash
cd ios/ButtonKit && swift test          # on the Mac. No simulator, no project
./.venv/Scripts/python -m pytest tests/test_ios_client.py -q    # on the PC
```

The Python one is the interesting half. The app mirrors exactly two things
from the service — **the routes it calls** and **one captured response body**
— and `tests/test_ios_client.py` reads both straight out of the Swift files
and checks them against the live FastAPI app. So renaming an endpoint fails a
test on a machine with no Xcode on it, which is the same deal
[test_protocol.py](../tests/test_protocol.py) makes for the wire.

What it cannot tell you is whether the Swift compiles. That needs the Mac.

## Four rules for anything added here

- **The app decides nothing.** It fires gestures and reads answers; the host
  resolves them. The moment a screen contains a rule about what a press
  *means*, the second brain has started.
- **No mirrored tables in Swift.** The gesture list comes off `/api/status`'s
  `active_modes` keys, which is the host's `TRIGGER_TYPES`; look styles are
  strings with a generic fallback; nothing here knows which templates are
  takeovers. A table that must be kept in step with Python needs a test that
  runs on the PC, or it does not go in.
- **Every field falls back on its own.** `Decoding.swift`'s `value(_:or:)` is
  `config._take` in Swift, and for the same reason: a service that grew a
  field, renamed one, or answered with a null must not blank a screen. There
  is no `try` on a model field anywhere in `Models.swift`.
- **Both implementations of `HostClient` stay interchangeable.** `PreviewHost`
  is this tier's `MockDevice`: every view is written against the protocol, so
  the whole app walks in a preview with no service, no network and no button.
  A view that reaches for `HTTPHost` by name has broken that.

## What is not here yet, in the order it is worth doing

1. **Editing.** Reading is done; writing is `PUT /api/config`, and it is not
   free — the editor's whole job is a schema the phone would need too
   (ROADMAP **D3**, one manifest served over `/api/schema`, is the thing that
   makes it cheap). Until then the web UI at `http://<host>:8080` is the
   editor, and the Modes tab says so.
2. **Scenes.** `/api/scenes` and one POST to activate. The cheapest genuinely
   useful next feature, and it needs no schema.
3. **App Intents / Shortcuts** (TODO **39**), so a gesture — or the app —
   can be reached from the phone's own automation. Small once an app exists.
4. **Camera switching** (TODO **38**'s remainder). The shutter itself is BLE
   HID and needs no app at all; only front/back switching does.
5. **A local sound when the button arrives.** Needs the `bluetooth-central`
   background mode and CoreBluetooth state restoration — and note that this
   is the first thing on the list that puts BLE code in the app, so it is the
   first that has to argue it is not the second brain. It is not Find My;
   do not call it that.

## Two things that will bite on the first build

- **Nothing here has been compiled.** It was written on the Windows host,
  which has no Swift toolchain — `swift test` in `ios/ButtonKit` is the first
  thing that has ever looked at it. The pure half is where the tests are and
  the risk is lowest; the SwiftUI half is where to expect corrections.
- **Leave the target on the Swift 5 language mode** for now. `HostStore` is
  `@MainActor` with a `nonisolated init` so the App struct can build it, which
  is the pattern strict concurrency wants — but nothing else here has been
  audited for Swift 6, and turning it on is a separate job.

And one rule about `Samples.swift`, learned by getting it wrong: those are
Swift **raw** strings, so a backslash in them is a literal backslash and the
JSON decoder refuses it as a bad escape. Sample paths use forward slashes for
that reason. `tests/test_ios_client.py` parses the same fences, so a sample
that stops being JSON fails there rather than in a preview.
