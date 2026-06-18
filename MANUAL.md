# AI Button — User Manual

This manual describes the **minimum viable product**: a single physical button
whose meaning changes with the **mode** it is in. It is the complete usage
reference and a validation target for the build — the architecture and phasing
behind it live in [DESIGN.md](DESIGN.md).

> Some pieces ship in phases (see the bottom of this manual). Where a feature
> is Phase 2, it is marked **[Phase 2]**.

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
| **5 taps** | five quick presses in a row — the one *global* gesture |

The first three are interpreted by whatever mode is active. **5 taps** is
different: it is a reserved, mode-independent **escape / power** gesture, the
same everywhere (see §6.1). Everything else the device does is one of the three
mode gestures.

---

## 3. Modes — the core idea

The button is **always in exactly one mode**. A mode is a named personality
that owns:

- what each gesture does,
- how the LED looks and what sounds play,
- any live state it keeps (a running stopwatch, a counter total).

There are two kinds of mode:

- **Ambient modes** sit quietly and *answer* your presses. The **Default**
  mode is ambient and **permanent** — it is always present as the floor, locked
  to the *Always* activation, and sits at the bottom of the list as the
  lowest-priority fallback. You can add other ambient modes above it (e.g. a
  different behaviour 5–7 am); because the list is checked top to bottom, those
  modes *override* the Default for the gestures they define.
- **Takeover modes** *take over* the button. When one starts — an alarm
  ringing, a stopwatch running, a counter open, a Pomodoro counting down —
  every press goes to that mode until you exit it (5 taps), then the button
  drops back to the ambient layer. While a takeover mode is active, your normal
  rules are paused; that is the point.

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
  > Default      always · short->Ask AI · long->Focus      [edit]
  > Wake up      at 07:00 Mon-Fri · Alarm, snooze 9 min     [edit]
  > Focus        entered from Default · Stopwatch "focus"   [edit]
  + Add mode
> Device settings   (AI hosts, timeouts, ports...)
[Save & apply]  [Check]  [Revert]    Saved
```

Click a summary to expand and edit it; click again to collapse. Device
plumbing lives in its own collapsed **Device settings** drawer so it stays out
of your way.

### 4.2 Anatomy of a mode

Every mode is edited with the same three-part card, no matter its kind:

1. **Name** — your label; shown in summaries, the status line, and over
   Bluetooth.
2. **Template** — *what kind* of mode it is (Actions / Alarm / Stopwatch /
   Counter). Choosing it swaps the fields below to match.
3. **Activation** — *when* it turns on (Always / Time window / At a time /
   Entered from another mode). Choosing it swaps the scope fields.

Because the card shape is always the same, the menu never grows new sections
as you add capability — new mode types just appear in the Template dropdown.

### 4.3 Buttons

- **Save & apply** — validates, writes the config, hot-reloads. No restart.
- **Check** — previews what the device *would* accept and which fields would
  fall back to defaults, without saving.
- **Revert** — discards your unsaved edits and reloads the live config.

If something is wrong (e.g. a time window missing an end time), Save/Check
list exactly what to fix first.

---

## 5. Templates (what a mode does)

### 5.1 Actions — the everyday mode

An **ambient** mode. Each gesture is mapped to one action; unmapped gestures
do nothing. Pick a different action per gesture from a dropdown.

Available actions:

| Action | What it does |
|---|---|
| **Ask the AI** | sends your prompt to the model; the spoken/returned answer is shown and sent over Bluetooth |
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

A **takeover** mode. Starting it begins timing (LED shows a teal running pulse).

| Gesture | Result |
|---|---|
| **Short press / double tap** | lap (records a marker) |
| **Long press** | stop and exit; total elapsed time is logged |
| **5 taps** | stop and exit (the universal escape) |

Field: **Timer name** — what the elapsed time is logged as (e.g. `focus`).
Daily totals accumulate, so you can see total focus time for the day.

### 5.4 Counter — tally something

A **takeover** mode. Opening it starts a tally at 0 (LED shows a magenta
counting breathe). Each gesture adds its own **increment**, so you can count up
fast in batches:

| Gesture | Result |
|---|---|
| **Short press** | add the *short* increment (default **+1**) |
| **Long press** | add the *long* increment (default **+10**) |
| **Double tap** | add the *double* increment (default **+20**) |
| **5 taps** | exit (with a session summary) |

Each increment is logged against the event name (as a single +N entry), so
daily counts and streaks build up correctly. Fields: **Event name** (e.g.
`gratitude`) and the three increments.

### 5.5 Pomodoro — focus timer

A **takeover** mode: a **work → break** countdown that **auto-repeats** until
you exit. The LED is an amber breathe during work and a green breathe during a
break; a sound marks each phase change. Each completed work block is logged for
daily focus totals.

The three gestures are **assignable** (pick a command per gesture); the
defaults are:

| Gesture | Default command | Result |
|---|---|---|
| **Short press** | Start / Pause | pause or resume the countdown |
| **Long press** | Restart | reset the current interval to full |
| **Double tap** | Extend | add the extend amount (**+10:00**) |
| **5 taps** | — (reserved) | exit (with a session summary) |

Fields: **Work minutes** (default 25), **Break minutes** (default 5),
**Extend minutes** (default 10), **Log work as** (e.g. `pomodoro`), and the
three assignable gesture commands.

---

## 6. Activations (when a mode turns on)

| Activation | For | You set | Behaviour |
|---|---|---|---|
| **Always** | the permanent Default | — | the floor; active whenever nothing else has taken over. The Default is **locked** to Always and pinned at the bottom of the list (lowest priority). |
| **Time window** | ambient modes | start + end time, optional days | active only inside the window (it may cross midnight, e.g. 22:00–06:00); overrides Default for the gestures it defines |
| **At a time** | Alarm (and other takeover modes) | a clock time, optional days | fires at that time and takes over — this is how you set an alarm |
| **Entered from another mode** | Stopwatch / Counter / Pomodoro | — | never starts on its own; you reach it with an **Enter a mode** action on a gesture in another mode |

How they interact when you press the button:

1. If a **takeover** mode is active, the press goes to it.
2. Otherwise the device checks **ambient** modes top to bottom — your added
   modes first, then the permanent Default last — and the first one that
   defines the pressed gesture wins. (Same first-match-wins logic throughout.)
   This is the priority system: anything you put above the Default overrides it.

A scheduled alarm can fire at any time; if one is due while another takeover
is running, the alarm takes priority.

### 6.1 Turning it off — and the 5-tap escape

**5 quick taps** is the one gesture that means the same thing everywhere. What
it does depends on context:

- **In a takeover mode** (alarm, stopwatch, counter, Pomodoro) → **exit** back
  to the ambient layer. This is how you leave a counter or Pomodoro now that
  their long-press is used for something else.
- **On the Default (ambient)** → **turn the device off**. The LED goes dark and
  presses are ignored — except another 5 taps, which turns it back on. A wake
  alarm still rings while off (then returns to off when dismissed).

So 5 taps is "escape", and on the home screen "escape" means "off".

---

## 7. Recipes

**Wake-up alarm, weekdays at 7 am**
Add mode → name "Wake up" → Template **Alarm** (message "Wake up", snooze 9,
log on dismiss `woke_up`) → Activation **At a time** 07:00, days Mon–Fri.
At 7 am it rings; tap to dismiss, hold to snooze 9 minutes.

**Morning meds reminder that goes quiet once taken**
Add mode → "Morning meds" → Template **Actions** (double tap → Log
`meds_taken`) → Activation **Time window** 05:00–07:00 → set **Skip if already
logged today** = `meds_taken`. Between 5 and 7, a double tap logs your meds and
the reminder stands down for the day.

**A focus stopwatch you start by hand [Phase 2]**
Add mode → "Focus" → Template **Stopwatch** (timer name `focus`) → Activation
**Entered from another mode**. Then in **Default**, map **Long press → Enter a
mode → Focus**. Long-press to start timing; short-press to lap; long-press to
stop and log the elapsed time.

**Gratitude / water tracker**
Add mode → "Gratitude" → Template **Counter** (event `gratitude`, increments
+1/+10/+20) → Entered from another mode. In Default, map **Double tap → Enter a
mode → Gratitude**. Open it, short-tap once per item (long-press +10 to batch),
5 taps to close.

**A Pomodoro focus timer**
Add mode → "Pomodoro" → Template **Pomodoro** (25 work / 5 break, log work as
`pomodoro`) → Entered from another mode. In Default, map **Short press → Enter a
mode → Pomodoro**. Short-tap to pause/resume, long-press to restart the
interval, double-tap to add 10 minutes, 5 taps to stop. Work and break repeat
automatically; each work block adds to your daily focus total.

**Everyday default**
Keep a **Default** Actions mode (Always) with, say, Short press → Ask the AI,
so the button is always useful even when no special mode applies.

---

## 8. LED & sound reference

The RGB LED shows device state; short feedback sounds confirm what happened.

| State | LED | When |
|---|---|---|
| **Idle** | slow blue breathe | waiting, ambient |
| **Listening** | solid yellow | a press was registered |
| **Thinking** | fast rainbow fade, rotating colors | an action is running (e.g. asking the AI) |
| **Success** | green (2 s) | action succeeded |
| **Error** | red flashes | action failed / no rule matched |
| **Ringing** | urgent red/white flash | an alarm is going off |
| **Timing** | teal/cyan pulse | a stopwatch is open |
| **Counting** | magenta breathe | a counter is open |
| **Pomodoro work** | amber breathe | a Pomodoro work interval |
| **Pomodoro break** | green breathe | a Pomodoro break interval |
| **Pomodoro paused** | dim amber, slow | a Pomodoro countdown is paused |
| **Off** | dark | the device is toggled off (5 taps) |

Feedback sounds are designed so the *interval* matches the meaning — a rising
tone means "good", a falling/dissonant one means "bad":

| Sound | Tone | When |
|---|---|---|
| **Ack** | single high click | a press was registered |
| **Success** | rising perfect-fifth | action succeeded |
| **Error** | falling tritone into a low note | action failed |
| **Alarm** | urgent repeating | an alarm is ringing (loops until you stop it) |
| **Wake** | rising arpeggio | the device turned on |
| **Sleep** | falling arpeggio | the device turned off |
| **Phase** | rising perfect-fourth | a Pomodoro phase change |

Each cue is also slightly varied every time it plays (tiny pitch/length jitter)
so repetition doesn't grate. Feedback sounds can be turned off in **Device
settings → Feedback sounds**.

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
- **Virtual device** (development/mock only) — mirrors the LED animations and
  plays the device's actual tones in the browser.

---

## 10. Phone / Bluetooth

The device advertises over Bluetooth LE as the name set in **Device settings →
Bluetooth name**. A subscribed phone or laptop receives state changes and
action results (e.g. the AI's answer) as they happen. The same information is
available over the REST API the web UI uses, so a future phone app can reuse
it.

---

## 11. AI answers, online and offline

"Ask the AI" prefers a model on your LAN for speed and falls back to a smaller
model running on the device itself if the LAN model is unreachable — so the
button still answers when your network or server is down. Hosts, models, and
timeouts are all in **Device settings → AI backends**.

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

## Phasing at a glance

- **Phase 1** — Default/Actions modes, **scheduled Alarms you stop with the
  button**, time-window and always activations, the collapsible Modes menu and
  Device drawer.
- **Phase 2** — **Stopwatch** and **Counter** modes, plus the **Enter a mode**
  action that starts them by gesture.
- **Phase 3** — **Pomodoro** mode (assignable gestures), **Counter increments**
  (+1/+10/+20), the **5-tap** global on/off + takeover escape, the **permanent
  locked Default** floor, and the interval-based **feedback sound** redesign.

Implementation detail and rationale: [DESIGN.md](DESIGN.md).
