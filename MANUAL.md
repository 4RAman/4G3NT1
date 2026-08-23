# AI Button — User Manual

This manual describes the **minimum viable product**: a single physical button
whose meaning changes with the **mode** it is in. It is the complete usage
reference and a validation target for the build — the architecture and phasing
behind it live in [DESIGN.md](DESIGN.md).

---

## 1. What it is

One button. Six gestures. The same gesture can mean different things at
different times of day or in different situations — because the button is
always in a **mode**, and the mode decides what each gesture does and how the
device looks and sounds.

You never program it by hand. A built-in web page lets you point and click to
build modes, then **Save & apply** — changes take effect immediately, no
restart.

---

## 2. The gestures

| Gesture | How |
|---|---|
| **Short press** | a single quick press and release |
| **Long press** | press and hold (~1 second) |
| **Double tap** | two quick presses |
| **Triple tap** | three quick presses |
| **Four taps** | four quick presses |
| **Five taps** | five quick presses |

That is the entire physical vocabulary. Everything the device does is one of
these gestures, interpreted by whatever mode is active.

**Long press means "up one level", everywhere.** Out of an app, then out of
the menu that opened it, then back to the everyday layer. It is the one
gesture you never have to think about, which is why no app may spend it on
something else — a control surface will not even let you bind it. The
launcher is the single exception and it proves the rule: it launches on a
*double tap*, because a menu where the universal escape gesture instead
committed you to something would be the worst possible place to break it. An
app you opened from the launcher comes back to the launcher when you leave,
so the gesture always travels exactly one level rather than one or two
depending on how you got there.

**A press is never instant, and that is deliberate.** A single press is held
back until the multi-tap window closes — about 0.4 seconds — because until
then the button cannot know a second press isn't coming. It always waits: no
setting makes a single press fire on contact. Treat it as a constant rather
than as lag. Anything that measures your own timing (the reaction game, the
metronome) already subtracts it before judging you.

**The longer bursts slow down the shorter ones.** Bind nothing longer than a
double tap and a double still fires the instant the second press lands. Bind
a triple and the double has to wait out the window too, to prove it isn't the
start of a triple; four and five taps push that same cost one and two rungs
further along. You never configure this — the button is told how far to count
from what your modes actually bind, so you only pay for the gestures you use.
Four and five taps are deliberately awkward, which makes them the right home
for something you would hate to fire by accident: an off switch, say.

---

## 3. Modes — the core idea

The button is **always in exactly one mode**. A mode is a named personality
that owns:

- what each gesture does,
- how the LED looks and what sounds play,
- any live state it keeps (a running stopwatch, a counter total).

There are two kinds of mode:

- **Ambient modes** sit quietly and *answer* your presses. **Home** — the
  always-on mode a fresh button ships with — is ambient, and is the floor
  that is always available. You can add other ambient modes scoped to a time
  window (e.g. a different behaviour 5–7 am).
- **Takeover modes** *take over* the button. When one starts — an alarm
  ringing, a stopwatch running, a counter open — every press goes to that mode
  until you exit it, then the button drops back to the ambient layer. While a
  takeover mode is active, your normal rules are paused; that is the point.

You build the device by defining modes and the **trigger** that activates each.

---

## 4. The web menu

Open **http://&lt;device&gt;:8080** on any phone or laptop on the same network
(during development, `http://localhost:8080`). The page has a live dashboard
down one side and four tabs: **Modes**, **Lights**, **Events** and
**Device**.

### 4.1 The Modes list

The Modes tab shows your modes as a list of one-line summaries. This is what a
button with no config of its own starts out holding:

```
[Modes] [Lights] [Events] [Device]

MODES
  > Home        always · short->Log "button_press" · double->Launcher
                                                  · long->Pomodoro     [edit]
  > Launcher    entered from another mode · offers every app           [edit]
  > Pomodoro    entered from another mode · 25/5, logs "pomodoro"      [edit]
  > Stopwatch   entered from another mode · Stopwatch "stopwatch"      [edit]
  + Add mode
[Save & apply]  [Check]  [Revert]    Saved
```

**Home** is the everyday layer and the only one that is always on. Its double
tap opens the **Launcher**, which reaches every app you add later without you
wiring anything (§7), and its long press opens the Pomodoro. Those four modes
are also the floor a broken config falls back to, so this list is what the
button does when nothing else is true.

Click a summary to expand and edit it; click again to collapse. Device
plumbing lives on its own **Device** tab so it stays out of your way, and the
colours on a **Lights** tab beside it (§8).

Next to **+ Add mode** is a **ready-made mode** picker — fourteen complete
modes, each dropped in ready to edit: Pomodoro, Tabata and HIIT intervals, a
Gratitude counter, a Stopwatch, a 10-minute Countdown, a 5AM alarm, a
Metronome, the Hot/Cold and Reaction games, a Status light, and three
footswitch/transport remotes for a DAW (OSC and MIDI). Quicker than
assembling one field by field, and a decent tour of what the button can do.

### 4.2 Anatomy of a mode

Every mode is edited with the same three-part card, no matter its kind:

1. **Name** — your label; shown in summaries, the status line, and over
   Bluetooth.
2. **What it does** — *what kind* of mode it is: **Actions** for the everyday
   layer, or one of the eleven apps — Alarm, Reminder, Stopwatch, Counter,
   Intervals, Metronome, Countdown, Hot/Cold, Reaction timer, Signal light,
   Control surface — plus the **App launcher** that reaches them all (§5).
   Choosing it swaps the fields below to match.
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

### 4.4 Scenes — saved setups you can swap

The bar above the tabs holds the **scene**: a whole saved setup — every mode,
every colour, every setting — that you can switch between in one click. Keep a
"Work" scene and a "Kitchen" scene. Try two arrangements of the same modes and
see which one you actually use.

- **The picker** switches scenes immediately. No restart; the button changes
  under your hand, colours included.
- **Save as…** saves what is on screen right now as a new scene and switches
  to it. This is how you make the second half of an A/B pair: set it up, save
  as "B", then flip between them.
- **Rename / Duplicate / Delete** do what they say. Deleting the scene you are
  running drops you back to the base config first.
- **Export / Import** move a scene between machines, or in and out of a text
  editor.
- **No scene — base config** runs `config.json` on its own. That is what a
  button that has never used scenes is doing.

**Scenes are files.** They live in a `scenes/` folder next to `config.json`,
one `.json` each, and you can edit them in Notepad with nothing running — no
service, no button, no browser. To check one before you use it:

```bash
.venv/Scripts/python -m aibutton.scenes check focus
```

That runs the same validator the button does and prints exactly what it would
complain about. `list` shows every scene, `activate <name>` switches without
opening anything.

Two things worth knowing:

- **A scene only has to hold what it changes.** A scene with just `modes` in
  it keeps the colours from `config.json` — useful when you want to compare
  two sets of behaviour without the lights changing underneath you. Scenes you
  save from this page hold everything, because that is what was on screen.
- **A few settings only apply at startup** — the Bluetooth name, the web
  address and port, and where the event database lives. Switch to a scene that
  changes one of those and the page will say so and name it; restart the
  service to make it take. Everything else is instant.

---

## 5. What a mode does

One everyday mode kind, eleven apps, and a launcher that reaches them:

| Kind | What it is | Getting out |
|---|---|---|
| **Actions** | the everyday layer: one action per gesture, answered without taking the button over (§5.1) | — it never takes over |
| **Alarm** | rings at a set time until you stop it (§5.2) | any press; long press snoozes if you set one |
| **Reminder** | a gentler alarm: shows at a set time, chimes once, gives up on its own after a while | any press |
| **Stopwatch** | times something, with laps (§5.3) | long press stops and logs |
| **Counter** | a tally you press up (§5.5) | long press |
| **Intervals** | work/rest blocks — Pomodoro, Tabata or HIIT from the one template (§5.4) | whichever gesture you put "leave" on; long press by default |
| **Metronome** | tap a tempo and the light keeps it, or follow a DAW's MIDI clock (§5.6) | long press |
| **Countdown** | counts a set number of minutes down, the colour walking as the time goes, then rings | long press; at zero it rings until any press |
| **Hot / Cold** | a guessing game: stop a spinning colour wheel on the hidden target | long press (short press stops the wheel) |
| **Reaction timer** | the light goes out at a random moment; press as fast as you can | long press (short press is your answer) |
| **Signal light** | wears one of your positions — Free / Busy / On air — and can send something on each change, which makes it an OSC or MIDI footswitch too | long press (short = next, double tap = send again) |
| **Control surface** | a remote: one command per gesture, held open so you can send several. Bind a gesture to **Enter a mode** and it becomes a menu page | long press |
| **App launcher** | steps through your apps so you don't need a gesture wired to each one | long press (short = next app, **double tap launches**) |

Everything except **Actions** is a *takeover*: it owns every press until you
leave. Each app's card in the menu says in plain words how to start it and how
to get back out.

### 5.1 Actions — the everyday mode

An **ambient** mode. Each gesture is mapped to one action; unmapped gestures
do nothing. Pick a different action per gesture from a dropdown.

Available actions:

| Action | What it does |
|---|---|
| **Log an event** | records a timestamped event (meds, habits); counted and streak-tracked |
| **Show a count on the light** | blinks today's count for an event back at you without opening anything: tens as slow pulses, units as quick ones, so 27 is two slow then seven quick. It only reads — it never adds a count of its own |
| **Start / stop a timer** | toggles a named stopwatch; the elapsed time is logged when stopped |
| **Call a webhook** | POSTs to any URL — the IFTTT / Make / n8n / Home Assistant hook. Pick a service and it fills in a template for you |
| **Send an OSC message** | fires one OSC message over the network at anything listening — Reaper, QLab, Resolume, TouchOSC, VCV Rack |
| **Send a MIDI message** | sends one note or CC to a MIDI port, for a DAW that speaks MIDI and not OSC. Start from a DAW command (Play, Record, Loop…) and it works unlearned |
| **Enter a mode** | opens one of your apps — how you start a stopwatch, a counter or the launcher by hand |
| **Sleep / wake the button** | puts the everyday layer to sleep; the same gesture wakes it |

**About the count readout.** Zero is a single dim blink rather than no blinks
at all, so "counted nothing today" reads differently from a button that just
sat there. Nothing about it depends on telling colours apart — the *rhythm*
carries the number — so it still works across a warm-tinted room and for a
colourblind reader. And because it only reads, it is safe on a gesture that
some other mode already logs to: you will not double-count anything.

**About Sleep / wake.** While asleep the button answers nothing — no tone, no
light, no logged event — except the gesture you bound to this, which is what
wakes it again. The resting light dims to a dark glow rather than going out,
because "off" and "unplugged" have to look different. What sleeps is the
everyday layer *only*: an app already running keeps running, and an alarm you
set still rings, since a stray five-tap should not be able to cancel your
morning. It lasts as long as the service does — restart and the button is
awake. A five-tap is its natural home.

**Where each action works.** Actions appear in three places: on the gestures
of an everyday mode, on the gestures of a control surface, and on a signal
light's positions. Two of them are everyday-only. **Show a count on the
light** takes the light over for as long as it counts, and **Sleep / wake**
changes what the *next* press means — both are things only the everyday layer
handles, so binding either inside an app gets you the error flash rather than
the behaviour. **Enter a mode** works on an everyday mode and on a control
surface (that is how one page opens another), but not on a signal position.

Optional: **Skip if already logged today** — give an event name and the whole
mode is skipped for the rest of the day once that event has been logged (e.g.
a meds reminder that goes quiet after you have taken them).

**Named actions — one action, several gestures.** An action can live in a
shared pool instead of on a single gesture. Name it once under **Named
actions** on the Modes tab (with the other fringe controls, behind the
header's **⚙ Tinker** toggle), then point as many gestures as you like at the
name: the three gestures that all send the same webhook become one thing to
edit rather than three. Naming is optional and most actions never need it — an
action used once is better written straight on the gesture. Rename one in the
menu and everything pointing at it follows. Delete one and the gestures that
named it are left pointing at nothing *on purpose*: the menu shows
"(missing)" and the button says so plainly when you press it, which is more
honest than quietly re-aiming several gestures at something you never chose.

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

### 5.4 Intervals — work in blocks (Pomodoro, Tabata, HIIT)

A **takeover** mode, and one template behind three ready-made modes: a
classic 25/5 Pomodoro, a 20-second Tabata, and HIIT intervals are the same
app with different numbers in it. Starting it begins a work block; when that
ends, a rest begins, and so on. The LED shows which half you are in — a slow
orange breathe for work, green for a rest — so it reads from across the room.

Every finished **work** block is logged (rests are not), so your counts and
streaks work on focus time like any other event.

Fields:

- **Work / Rest / Long rest** — 25 / 5 / 15 minutes by default.
- **Blocks before a long rest** — every 4th rest is the long one.
- **Rounds** — stop after this many work blocks. `0` (the default) alternates
  until you leave, which is classic Pomodoro.
- **Get-ready countdown** — a pause before block 1, for setup time. `0`
  starts immediately.
- **Between blocks** — how much the button asks of you:
  *start the next block automatically*, *wait for a press every time*, or
  *breaks start themselves, work waits for a press*.
- **While paused or waiting for a press** — how the light moves when nothing
  is counting down. Solid is a good default, since breathing and flashing
  already mean "still running".
- **Time added by "Add more time"** — 10 minutes by default.
- **Log each finished block as** — the event name, `pomodoro` by default.

**Three gestures are yours to assign** — short press, long press and double
tap — each to one of: start/pause, restart the block, add more time, skip to
the next block, leave, or nothing at all. The defaults are **tap =
start/pause, long press = leave, double tap = +10 min**; long press leaves,
matching every other app. Assign *restart* to whichever gesture you prefer.
The menu warns you if you take "leave" off the only gesture that had it.

While paused, waiting for you to start the next block, or counting a
get-ready pause, the LED keeps the **colour of the block it is about** and
just stops moving — the style you picked under *While paused or waiting for a
press*. Same colour, no animation: it is the same block, not counting.

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
| **Always on** | the everyday floor — **Home**, as shipped | — | active whenever nothing else has taken over. Exactly one mode is Always on. |
| **Only during certain hours** | everyday modes | start + end time, optional days | active only inside the window (it may cross midnight, e.g. 22:00–06:00); overrides Home for the gestures it defines |
| **At a set time each day** | Alarm, Reminder | a clock time, optional days | fires at that time and takes over — this is how you set an alarm |
| **Only when another mode starts it** | every other app | — | never starts on its own; you reach it with an **Enter a mode** action on a gesture in another mode, or from the App launcher |

Only the two clock-started apps get **At a set time each day**; the other
nine, and the launcher, are started by a gesture and offer only **Only when
another mode starts it**. The menu offers each mode kind exactly the
activations it can actually use, so there is no wrong combination to pick.

With nine apps and six gestures, wiring one gesture per app runs out fast —
that is what the **App launcher** is for. Point one gesture at the launcher
and it steps through your apps: short press moves to the next, double tap
opens it, long press comes home.

How they interact when you press the button:

1. If a **takeover** mode is active, the press goes to it.
2. Otherwise the device checks **ambient** modes top to bottom — time-window
   modes first, then the always-on one (**Home**) — and the first one that
   defines the pressed gesture wins. (Same first-match-wins logic throughout.)

A scheduled alarm can fire at any time; if one is due while another takeover
is running, the alarm takes priority.

---

## 7. Recipes

**Some of this already works.** A button with no config of its own starts with
**Home** on the everyday layer — short press logs `button_press`, double tap
opens the **Launcher**, long press opens a **Pomodoro** — and a **Stopwatch**
waiting behind the launcher. So the first recipes here change what you already
have; the later ones add what nothing ships.

**Change what the everyday press logs**
Open **Home** → **Short press**. It is already **Log an event**, named
`button_press`, which is a placeholder for whatever you actually want to
count. Put your own name in: `water`, `meds_taken`, `smoke`. That name is the
key everything downstream keys off — the daily count, the streak, the Events
tab, and the readout below. Smallest useful edit there is, and it is one
field.

**Put today's count back on the light**
Nothing shows you a number by default, because the button has one LED and no
screen. In **Home**, map **Triple tap → Show a count on the light** with the
same event name your short press logs. Now three taps blinks the total back:
tens as slow pulses, units as quick ones, so seven is seven quick blinks and
twenty-seven is two slow then seven quick. It only reads, so sitting beside
the gesture that logs costs you no double counting.

There *is* a price and it is not on the light. Binding a triple makes the
double tap wait out the tap window to prove it is not the start of a triple,
so your launcher stops opening the instant you tap it (§2). Worth it for a
habit you check every day; not worth it for one you don't.

**Swap the app on the long press**
Long press already opens the Pomodoro, so this is a substitution, not a build.
Either open **Home** → **Long press** → **Enter a mode** and pick a different
app — or leave the gesture alone and edit the **Pomodoro** mode itself, since
Tabata and HIIT are that same app with different numbers in it (§5.4).
Clearing the long press entirely is a fine third option: every app is still a
double tap and a few short presses away through the launcher.

**Add an app without spending a gesture**
Add mode → "Water" → **Counter** (event `water`) → **Only when another mode
starts it**. That is the whole recipe; there is no second step. The launcher
offers every app in list order unless you name a shorter list, so the new
counter turns up on your double tap with nothing else wired. Open it, tap once
per glass, long-press to close — and because you launched it from the
launcher, that long press lands you back in the launcher rather than all the
way home.

**Trim or reorder the launcher's menu**
Open **Launcher**. Its app list is empty, and empty means *all of them, in
config order* — which is what makes the recipe above a one-step recipe, and
also what makes a well-used button a long menu. Name the apps you actually
reach and you get a short menu in the order you named. Nothing is lost by
leaving an app out; it just needs a gesture or another mode to open it.

**When an app has earned its own gesture**
The launcher costs a double tap plus a press or two of cycling, which is the
right trade for most apps and the wrong one for the app you open twenty times
a day. Wire that one straight: **Home** → **Triple tap** → **Enter a mode** →
**Stopwatch**. Weigh it first, though — there are six gestures and nine apps a
gesture can start, and every longer burst you bind slows the shorter ones
(§2). Note that this is the same triple tap the count readout above wanted:
you get one of the two. That squeeze, in miniature, is why the launcher
exists.

**Wake-up alarm, weekdays at 7 am**
Add mode → name "Wake up" → **Alarm** (message "Wake up", snooze 9,
log on dismiss `woke_up`) → **At a set time each day** 07:00, days Mon–Fri.
At 7 am it rings; tap to dismiss, hold to snooze 9 minutes. This one spends no
gesture at all: a clock starts it, which is why Alarm and Reminder are the
only two kinds offered **At a set time each day** (§6).

**Morning meds reminder that goes quiet once taken**
Add mode → "Morning meds" → **Actions** (double tap → Log
`meds_taken`) → **Only during certain hours** 05:00–07:00 → set **Skip if
already logged today** = `meds_taken`. Between 5 and 7, a double tap logs your
meds and the reminder stands down for the day. It is also a clean look at
first-match-wins: inside the window your double tap logs instead of opening
the launcher, and the moment the mode stands down it goes back to opening the
launcher, because Home was underneath it the whole time.

---

## 8. LED & sound reference

The RGB LED shows device state; short feedback sounds confirm what happened.

**The colours are yours to change.** In the web menu, open the **Lights**
tab. Every state gets a style, its colours, and how fast it moves; **Save &
apply** sends them straight to the button — no restart, no reflashing. The
swatch beside each row animates exactly as the LED will.

The first five states below belong to the button itself and are edited here,
once. The rest belong to whichever app is running, so they are edited on that
app's own card — a mode you have to configure in two places is not really one
mode. The colours here stay as the fallback an app with no colour of its own
wears.

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
| **Alarm ringing** | red/white alternating | an alarm or a reminder is going off |
| **Stopwatch running** | cyan breathe (1.6 s) | a stopwatch or a countdown is open |
| **Counter open** | magenta breathe (2.2 s) | a counter is open |
| **Working** | slow orange breathe (5 s) | an intervals work block is running |
| **Resting** | slow green breathe (5 s) | an intervals rest is running |
| **Metronome running** | amber flash at the tapped tempo | a metronome is open |

The two games, the signal light and the launcher have no state of their own on
this list, deliberately: every frame they show is a colour they worked out for
themselves — how close your guess was, which position you are on, which app
the menu is offering — so a fixed colour would only ever be the wrong one. A
control surface rests on **Listening** between commands, flashing Success or
Error for each one it sends and then going back to waiting.

| Sound | Tone | When |
|---|---|---|
| **Ack** | single high beep | a press was registered |
| **Success** | rising two-tone | action succeeded |
| **Error** | low triple buzz | action failed |
| **Alarm** | urgent repeating | an alarm is ringing (loops until you stop it) |

Feedback sounds can be turned off on the **Device** tab → **Feedback sounds**.

---

## 9. The dashboard

The header carries the live state, and a side pane holds the things you press
to test with — fold it away with the toggle beside it when you want the whole
width for editing.

- **State badge & last action** — current state, and the last gesture → mode →
  result.
- **Recent events** — your logged events and timer durations, newest first, on
  the **Events** tab.
- **Press** — one button per gesture the button can send, fired through the
  real pipeline, handy for testing a mode without touching the hardware. The
  row is built from the gesture table rather than written out, so it always
  offers exactly what a config can bind — including the four- and five-tap a
  hand is slow at. A simulated press arrives instantly, where a real one waits
  for the multi-tap window to close; anything timing you already accounts for
  that difference.
- **Sounds** — plays each of the button's four tones in the browser, useful
  when the button itself is in another room.
- **Clock** — set the time the device *thinks* it is (e.g. 06:59) to try
  a time-windowed mode or watch a 07:00 alarm fire seconds later. It keeps
  ticking, never persists across restarts, and never changes your event
  history timestamps.
- **Virtual device** (whenever no real button is connected) — mirrors the LED
  animations and plays the device's actual tones in the browser.

---

## 10. Bluetooth

The button and the computer are two halves of one device: the button detects
your gestures and shows the LED and tones, the computer runs everything else.
They talk over Bluetooth LE, and the button advertises under the name set on
the **Device** tab → **Bluetooth name**.

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
  or adjust a mode so the gesture is covered — **Home**, the always-on mode,
  is your safety net; keep at least one gesture mapped there.
- **An alarm won't stop** → any press dismisses it; if only long-press seems
  to act, you have a snooze set (long-press snoozes, any other press
  dismisses).
- **The button ignores everything and rests on a dim glow** → it is asleep.
  Something is bound to **Sleep / wake the button**; the same gesture wakes it,
  and so does restarting the service. Nothing else gets through while it is
  asleep, which is the point.
- **A gesture does nothing and the button says so** → it names an action that
  isn't in the pool any more. Open the mode, and the gesture will show
  "(missing)" against the name it is looking for — point it at an existing
  named action, or write one straight onto the gesture.
- **You are stuck inside something** → long press. Out of an app, out of the
  menu, back to the everyday layer, every time.

---

Everything in this manual is live, on real hardware: an ESP32 detects your
gestures and shows the lights and tones, the computer runs everything else.
With no button attached, the browser's virtual device stands in for it and
every word above still applies.

Implementation detail and rationale: [DESIGN.md](DESIGN.md) for the mode
machine, [DESIGN-ESP32.md](DESIGN-ESP32.md) for the hardware split. What is
coming next — swappable apps, and a button that keeps working when you walk
away from the computer: [ROADMAP.md](ROADMAP.md).
