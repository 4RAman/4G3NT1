# AI Button — User Manual

This manual describes the **minimum viable product**: a single physical button
whose meaning changes with the **mode** it is in. It is the complete usage
reference and a validation target for the build — the architecture and phasing
behind it live in [DESIGN.md](DESIGN.md).

---

## 1. What it is

One button. Three gestures. The same gesture can mean different things at
different times of day or in different situations — because the button is
always in a **mode**, and the mode decides what each gesture does and how the
device looks and sounds.

You never program it by hand. A built-in web page lets you point and click to
build modes, then **Save & apply** — changes take effect immediately, no
restart.

---

## 2. The three gestures

| Gesture | How |
|---|---|
| **Short press** | a single quick press and release |
| **Long press** | press and hold (~1 second) |
| **Double tap** | two quick presses |

That is the entire physical vocabulary. Everything the device does is one of
these three gestures, interpreted by whatever mode is active.

---

## 3. Modes — the core idea

The button is **always in exactly one mode**. A mode is a named personality
that owns:

- what each gesture does,
- how the LED looks and what sounds play,
- any live state it keeps (a running stopwatch, a counter total).

There are two kinds of mode:

- **Ambient modes** sit quietly and *answer* your presses. The **Default**
  mode is ambient and is always available as the floor. You can add other
  ambient modes scoped to a time window (e.g. a different behaviour 5–7 am).
- **Takeover modes** *take over* the button. When one starts — an alarm
  ringing, a stopwatch running, a counter open — every press goes to that mode
  until you exit it, then the button drops back to the ambient layer. While a
  takeover mode is active, your normal rules are paused; that is the point.

You build the device by defining modes and the **trigger** that activates each.

---

## 4. The web menu

Open **http://&lt;device&gt;:8080** on any phone or laptop on the same network
(during development, `http://localhost:8080`). The page has a live dashboard
and a **Configure** section.

### 4.1 The Modes list

Configure shows your modes as a list of one-line summaries:

```
MODES
  > Default      always · short->Log "meds" · long->Focus   [edit]
  > Wake up      at 07:00 Mon-Fri · Alarm, snooze 9 min     [edit]
  > Focus        entered from Default · Stopwatch "focus"   [edit]
  + Add mode
> Device settings   (Bluetooth name, database, ports...)
[Save & apply]  [Check]  [Revert]    Saved
```

Click a summary to expand and edit it; click again to collapse. Device
plumbing lives in its own collapsed **Device settings** drawer so it stays out
of your way, and the colours in a **Lights** drawer beside it (§8).

Next to **+ Add mode** is a **ready-made mode** picker: Pomodoro, Gratitude
counter, Stopwatch and a 5AM alarm, each dropped in complete and ready to
edit. Quicker than assembling one field by field, and a decent tour of what
the button can do.

### 4.2 Anatomy of a mode

Every mode is edited with the same three-part card, no matter its kind:

1. **Name** — your label; shown in summaries, the status line, and over
   Bluetooth.
2. **What it does** — *what kind* of mode it is (Actions / Alarm / Stopwatch /
   Counter / Pomodoro / Metronome). Choosing it swaps the fields below to
   match.
3. **When it's on** — (Always on / Only during certain hours / At a set time
   each day / Only when another mode starts it). Choosing it swaps the scope
   fields.

Because the card shape is always the same, the menu never grows new sections
as you add capability — new mode types just appear in the **What it does**
dropdown.

Modes are listed in two groups, because they turn on in completely different
ways: **Everyday modes** answer presses in list order, and **modes that take
over the button** own every press until you leave them. Each takeover mode's
card says in plain words how to start it and how to get back out, and warns
you if nothing can start it at all.

### 4.3 Buttons

- **Save & apply** — validates, writes the config, hot-reloads. No restart.
- **Check** — previews what the device *would* accept and which fields would
  fall back to defaults, without saving.
- **Revert** — discards your unsaved edits and reloads the live config.

If something is wrong (e.g. a time window missing an end time), Save/Check
list exactly what to fix first.

---

## 5. What a mode does

### 5.1 Actions — the everyday mode

An **ambient** mode. Each gesture is mapped to one action; unmapped gestures
do nothing. Pick a different action per gesture from a dropdown.

Available actions:

| Action | What it does |
|---|---|
| **Log an event** | records a timestamped event (meds, habits); counted and streak-tracked |
| **Start / stop a timer** | toggles a named stopwatch; the elapsed time is logged when stopped |
| **Call a webhook** | POSTs to any URL — the IFTTT / Make / n8n / Home Assistant hook |
| **Enter a mode** | switches the button into one of your takeover modes (how you start a stopwatch or counter by hand) |

Optional: **Skip if already logged today** — give an event name and the whole
mode is skipped for the rest of the day once that event has been logged (e.g.
a meds reminder that goes quiet after you have taken them).

### 5.2 Alarm — rings until you stop it

A **takeover** mode. When it activates, the device rings: urgent red/white LED
and a repeating alarm tone. It keeps ringing until you act.

| While ringing | Result |
|---|---|
| **Any press** | dismisses the alarm |
| **Long press** (if snooze set) | snoozes for the configured minutes, then rings again |

Fields:

- **Message** — shown while ringing.
- **Short label** — optional name for status/Bluetooth.
- **Snooze minutes** — `0` means long-press just dismisses like any other press.
- **Log on dismiss** — optional event name recorded when you dismiss (e.g.
  `woke_up`), so it shows up in your history.

Activate an alarm with **At a time** (a real alarm clock) — see §6.

### 5.3 Stopwatch — time something

A **takeover** mode. Starting it begins timing (LED shows a running state).

| Gesture | Result |
|---|---|
| **Short press** | lap (records a marker) |
| **Long press** | stop and exit; total elapsed time is logged |

Field: **Timer name** — what the elapsed time is logged as (e.g. `focus`).
Daily totals accumulate, so you can see total focus time for the day.

### 5.4 Pomodoro — work in blocks

A **takeover** mode. Starting it begins a work block; when that ends, a
break begins, and so on. The LED shows which half you are in — a slow orange
breathe for work, green for a break — so it reads from across the room.

Every finished **work** block is logged (breaks are not), so your counts and
streaks work on focus time like any other event.

Fields:

- **Work / Break / Long break minutes** — 25 / 5 / 15 by default.
- **Blocks before a long break** — every 4th break is the long one.
- **Between blocks** — how much the button asks of you:
  *start the next block automatically*, *wait for a press every time*, or
  *breaks start themselves, work waits for a press*.
- **Minutes added by "Add more time"** — 10 by default.
- **Log each finished block as** — the event name, `pomodoro` by default.

**The three gestures are yours to assign**, each to one of: start/pause,
restart the block, add more time, skip to the next block, or leave. The
defaults are **tap = start/pause, long press = leave, double tap = +10 min**
— long press leaves, matching every other takeover mode. Assign *restart*
to whichever gesture you prefer.

While paused (or waiting for you to start the next block) the LED shows the
**Listening** colour, since nothing is counting down.

### 5.5 Counter — tally something

A **takeover** mode. Opening it starts a tally (LED shows a counting state).

| Gesture | Result |
|---|---|
| **Short press / double tap** | +1 (each is logged, so counts and streaks build up) |
| **Long press** | exit |

Field: **Event name** — what each increment is logged as (e.g. `water`).

### 5.6 Metronome — tap out a tempo

A **takeover** mode, and the only one with nothing to configure — the tempo is
whatever you tap, not something you save.

| Gesture | Result |
|---|---|
| **Short press / double tap** | mark a beat |
| **Long press** | exit |

The BPM is a rolling average of your recent taps, so it settles as you keep
going rather than jumping on every beat; pause for more than two seconds and
it starts the average over. The LED pulses live at the tapped tempo — fast
tapping is capped at a safe flash rate — and goes back to your configured
**Metronome running** colour when you leave.

---

## 6. When it's on

| Setting | For | You set | Behaviour |
|---|---|---|---|
| **Always on** | the Default everyday mode | — | the floor; active whenever nothing else has taken over. Exactly one mode is Always on. |
| **Only during certain hours** | everyday modes | start + end time, optional days | active only inside the window (it may cross midnight, e.g. 22:00–06:00); overrides Default for the gestures it defines |
| **At a set time each day** | Alarm | a clock time, optional days | fires at that time and takes over — this is how you set an alarm |
| **Only when another mode starts it** | Stopwatch / Counter / Pomodoro | — | never starts on its own; you reach it with an **Enter a mode** action on a gesture in another mode |

How they interact when you press the button:

1. If a **takeover** mode is active, the press goes to it.
2. Otherwise the device checks **ambient** modes top to bottom — time-window
   modes first, then Default — and the first one that defines the pressed
   gesture wins. (Same first-match-wins logic throughout.)

A scheduled alarm can fire at any time; if one is due while another takeover
is running, the alarm takes priority.

---

## 7. Recipes

**Wake-up alarm, weekdays at 7 am**
Add mode → name "Wake up" → **Alarm** (message "Wake up", snooze 9,
log on dismiss `woke_up`) → **At a set time each day** 07:00, days Mon–Fri.
At 7 am it rings; tap to dismiss, hold to snooze 9 minutes.

**Morning meds reminder that goes quiet once taken**
Add mode → "Morning meds" → **Actions** (double tap → Log
`meds_taken`) → **Only during certain hours** 05:00–07:00 → set **Skip if
already logged today** = `meds_taken`. Between 5 and 7, a double tap logs
your meds and
the reminder stands down for the day.

**A focus stopwatch you start by hand**
Add mode → "Focus" → **Stopwatch** (timer name `focus`) → **Only when another
mode starts it**. Then in **Default**, map **Long press → Enter a mode →
Focus**. Long-press to start timing; short-press to lap; long-press to stop
and log the elapsed time. Until you add that Enter a mode gesture, the Focus
card tells you nothing can start it.

**Water tracker**
Add mode → "Water" → **Counter** (event `water`) → **Only when another mode
starts it**. In Default, map **Double tap → Enter a mode → Water**. Open it,
tap once per glass, long-press to close.

**A Pomodoro on the desk**
Add a **Pomodoro** from the ready-made picker, then in **Default** map
**Long press → Enter a mode → Pomodoro**. Long-press to start working; the
LED breathes orange while you work and green on breaks. Tap to pause, double
tap for ten more minutes, long press when you are done. Each finished block
is logged, so `pomodoro` gets a daily count and a streak like anything else.

**Everyday default**
Keep a **Default** Actions mode (Always) with, say, Short press → Log an event,
so the button is always useful even when no special mode applies.

---

## 8. LED & sound reference

The RGB LED shows device state; short feedback sounds confirm what happened.

**The colours are yours to change.** In the web menu, open **Lights (what
each state looks like)**. Every state gets a style, its colours, and how fast
it moves; **Save & apply** sends them straight to the button — no restart, no
reflashing. The swatch beside each row animates exactly as the LED will.

| Style | What it does |
|---|---|
| **Solid** | one colour, held |
| **Breathe** | fades between off and the colour |
| **Flash** | hard on/off blink |
| **Alternate two colours** | swaps between two colours |
| **Fade between two colours** | crossfades between two colours, through the shades in between |
| **Rainbow** | cycles through every hue |

The defaults, which are also what the button shows if it is powered up with
no computer attached:

| State | LED | When |
|---|---|---|
| **Idle** | slow blue breathe (3 s) | waiting, ambient |
| **Listening** | solid yellow | a press was registered |
| **Thinking** | rainbow, 1 s a turn | an action is running (e.g. calling a webhook) |
| **Success** | solid green (held 2 s) | action succeeded |
| **Error** | red flash | action failed / no rule matched |
| **Ringing** | red/white alternating | an alarm is going off |
| **Timing** | cyan breathe (1.6 s) | a stopwatch is open |
| **Counting** | magenta breathe (2.2 s) | a counter is open |
| **Working** | slow orange breathe (5 s) | a Pomodoro work block is running |
| **Resting** | slow green breathe (5 s) | a Pomodoro break is running |
| **Metronome running** | amber flash at the tapped tempo | a metronome is open |

| Sound | Tone | When |
|---|---|---|
| **Ack** | single high beep | a press was registered |
| **Success** | rising two-tone | action succeeded |
| **Error** | low triple buzz | action failed |
| **Alarm** | urgent repeating | an alarm is ringing (loops until you stop it) |

Feedback sounds can be turned off in **Device settings → Feedback sounds**.

---

## 9. The dashboard

Above the Configure section the page shows:

- **State badge & last action** — current state, and the last gesture → mode →
  result.
- **Recent events** — your logged events and timer durations, newest first.
- **Simulate presses** — buttons that fire Short press / Long press / Double
  tap through the real pipeline, handy for testing a mode without touching the
  hardware.
- **Test clock** — set the time the device *thinks* it is (e.g. 06:59) to try
  a time-windowed mode or watch a 07:00 alarm fire seconds later. It keeps
  ticking, never persists across restarts, and never changes your event
  history timestamps.
- **Virtual device** (whenever no real button is connected) — mirrors the LED
  animations and plays the device's actual tones in the browser.

---

## 10. Bluetooth

The button and the computer are two halves of one device: the button detects
your gestures and shows the LED and tones, the computer runs everything else.
They talk over Bluetooth LE, and the button advertises under the name set in
**Device settings → Bluetooth name**.

Two consequences worth knowing: **the computer has to be awake** for a press to
do anything (alarms included), and everything the app knows is on the REST API
the web UI uses — so a phone app can reuse it.

---

## 11. Reaching an AI

There is no model on the button. To involve one, use **Call a webhook** and
let whatever receives it do the thinking — an automation in n8n / Make /
Home Assistant, or your own script.

---

## 12. If something goes wrong

- **A bad config never bricks the button.** A missing or malformed setting
  falls back to a safe default with a logged warning; the web editor shows you
  those warnings after a Save or Check, so you can see exactly what was
  accepted.
- **No mode matched a press** → the error state (red flash + error tone). Add
  or adjust a mode so the gesture is covered — the **Default** mode is your
  safety net; keep at least one gesture mapped there.
- **An alarm won't stop** → any press dismisses it; if only long-press seems
  to act, you have a snooze set (long-press snoozes, any other press
  dismisses).

---

Everything in this manual is live, on real hardware: an ESP32 detects your
gestures and shows the lights and tones, the computer runs everything else.
With no button attached, the browser's virtual device stands in for it and
every word above still applies.

Implementation detail and rationale: [DESIGN.md](DESIGN.md) for the mode
machine, [DESIGN-ESP32.md](DESIGN-ESP32.md) for the hardware split. What is
coming next — swappable apps, and a button that keeps working when you walk
away from the computer: [ROADMAP.md](ROADMAP.md).
