# AI Button — User Manual

This manual describes the **minimum viable product**: a single physical button
whose meaning changes with the **mode** it is in. It is the complete usage
reference and a validation target for the build — the rationale behind the
mode machine is in [DESIGN.md](DESIGN.md).

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
the menu that opened it, then back to your menus. It is the one
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
- any live state it keeps (a running stopwatch, a tally total).

There are two kinds of mode:

- **Menus** sit quietly and *answer* your presses — always live, fired
  without thinking. **Home** — the always-on mode a fresh button ships with —
  is a menu, and is the floor that is always available. You can add other
  menus scoped to a time window (e.g. a different behaviour 5–7 am).
- **Apps** *take over* the button. When one launches — an alarm ringing, a
  stopwatch running, a tally open — every press goes to that app until you
  exit it, then the button drops back to your menus. While an app is
  running, your menus are muted; that is the point.

And one thing that is not a mode: a **reaction** (§5.8), where the button acts
with nobody pressing it.

You build the device by defining modes and the **trigger** that activates each.

---

## 4. The web menu

Open **http://&lt;device&gt;:8080** on any phone or laptop on the same network
(during development, `http://localhost:8080`). Down the left is the
navigation — four destinations, **Events**, **Lights**, **Device** and
**Apps**, and under them everything you have, grouped into **Menus**, **Apps**
and **Reactions**.
Clicking a mode opens it. The page lands on **Events**, because most visits
are to see what the button has been doing rather than to change what it does.

The **◧ Test panel** button in the header opens the bench: what the light is
showing right now, buttons that press the button for you, its tones, and a
test clock. It is a popover — it appears when you ask for it and closes on
Escape, on the button again, or on a click outside it.

While an alarm is **ringing**, a **Dismiss** button appears in the header
beside the state badge. It sends an ordinary short press, which is what
dismisses an alarm anyway — it is there because a ringing alarm is the one
state the page could report and not act on, and because if the button is out
of range there is nothing in the room to press either. It shows for a ringing
alarm and nothing else: every other app is one you chose to open and can leave
with a long press.

### 4.1 The mode list

The left-hand list is your modes, each with a dot of the colour it runs in, a
mark saying **what sets it off**, and one line saying what makes *this* one
different from its siblings. This is what a button with no config of its own
starts out holding:

```
◦ Events                    |
◦ Lights                    |   whichever section or mode
◦ Actions                   |   you picked on the left
◦ Device                    |
◦ Apps                      |
                            |
MENUS                       |
  Home                      |
  short->Log "button_press" |
  ▸ Launcher                |
  over every app            |
                            |
APPS                        |
  ▸ Pomodoro                |
  25m/5m (auto)             |
  ▸ Stopwatch               |
  logs "stopwatch"          |
  + Add menu                |
                            |
                            [Save & apply] [Check] [Revert]  Saved
```

**The mark in front of a name says what starts it**, which is the one thing you
cannot work out by looking at the mode itself:

| | Started by |
|---|---|
| *(nothing)* | it is always listening - every menu is |
| **▸** | a press somewhere opens it |
| **◷** | a clock does, with nobody pressing anything |
| **⚡** | a reaction does (§5.8) |
| **⊘** | **nothing can reach it.** You can configure this mode and never get to it - bind a gesture to *Launch an app*, or add it to a launcher |

That last one is the reason the marks exist. An app nothing points at looks
exactly like a working one until you go hunting for it on the button.

**Home** is your baseline menu and the only mode that is always on. Its double
tap opens the **Launcher** — a menu too, since all it does is let a press pick
between things — which reaches every app you add later without you wiring
anything (§7), and its long press opens the Pomodoro. Those four modes are
also the floor a broken config falls back to, so this list is what the button
does when nothing else is true.

Your **named actions** and your **reactions** live together under **Actions**,
because a reaction is a circumstance with an action attached and the pool is
where those actions come from. Both start empty (§5.8).

Click a mode in the list and it opens on the right; the list stays where it
is, so moving between modes is one click rather than two. Device plumbing
lives under **Device** so it stays out of your way, and the colours under
**Lights** (§8).

One button sits under the list: **+ Add menu** writes a new gesture map here
and now. Installing an app happens on the **Apps** tab instead (§4.6), up at
the top of this same nav — including the sixteen ready-made ones: an Alarm and
a Reminder, Pomodoro, Tabata and HIIT intervals, a Gratitude tally, a
Stopwatch, a 10-minute Countdown, a 5AM alarm, a Metronome, the Hot/Cold and
Reaction games, a Status light, and three footswitch/transport remotes for a
DAW (OSC and MIDI). Quicker than assembling one field by field, and a decent
tour of what the button can do.

### 4.2 Anatomy of a mode

Every mode is edited with the same three-part card, no matter its kind:

1. **Name** — your label; shown in summaries, the status line, and over
   Bluetooth.
2. **What it does** — *what kind* of mode it is: **Actions** for a menu,
   or one of the ten apps — Notice (an alarm or a gentler reminder,
   depending on one setting), Stopwatch, Tally, Intervals, Metronome,
   Countdown, Hot/Cold, Reaction timer, Signal light, Control surface — plus
   the **App launcher** that reaches them all (§5).
   Choosing it swaps the fields below to match.
3. **When it's on** — (Always on / Only during certain hours / At a set time
   each day / Only when another mode starts it). Choosing it swaps the scope
   fields.

Because the card shape is always the same, the menu never grows new sections
as you add capability — new mode types just appear in the **What it does**
dropdown.

Modes are listed in two groups, because they turn on in completely different
ways: **Menus** answer presses in list order, and **Apps** own every press
until you leave them. Each app's card says in plain words how to launch it and
how to get back out, and warns you if nothing can launch it at all.

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
./.venv/Scripts/python -m aibutton.scenes check focus
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

### 4.5 On a phone

The page is built to work at phone width. Narrower than 900px the two
columns stop being two columns: the navigation sits above whatever you are
editing, capped so it never fills the screen, and the page scrolls normally
from there. The Events log scrolls sideways inside its own box rather than
dragging the page with it, and **Save & apply** sticks to the bottom of the
screen so it is never a scroll away.

The test panel costs nothing while it is closed, which is why it is a popover
rather than a column — on a phone the column it replaced took a third of the
screen for controls you only want when the real button is *not* connected.

**On the same wifi**, that is all there is to it: open
`http://<the computer's address>:8080`.

**Away from home** the honest answer is a mesh VPN rather than hosting
anything. Install [Tailscale](https://tailscale.com) on the machine running
the service and on the phone, sign both into the same account, and the UI is
at `http://<machine-name>:8080` from anywhere. Nothing is exposed to the
internet, no ports are forwarded, and no password is needed — which matters,
because **the web UI has no authentication of its own** and must never be put
on a public address.

The one thing to know: the service must still be *near the button*. Bluetooth
range is a room, not a country. Reaching the page from a cafe lets you edit
the config; it does not let the button hear you.

### 4.6 Apps — what you have, and what can reach it

The **Apps** destination lists every app the button can run, each in one of
three states:

| State | Means |
|---|---|
| **Available** | the button can run it; you have not installed it |
| **Installed** | installed, and something can open it |
| **Unreachable** | installed, and *nothing* can open it |

**That last one is the reason the page exists.** Whether an app can be reached
is not a fact about the app: it depends on what *other* modes do — a gesture
bound to **Launch an app**, a clock, or a launcher that offers it. So no
single mode's page can answer it, and an app you configured carefully but
never wired up looks perfectly healthy right up until you reach for it.

Reachability is followed through, not guessed. A launcher makes everything it
offers reachable — but only if the launcher itself can be opened. Install one
that no gesture points at and the page says so, and says the apps under it are
still stranded, which is exactly what the button would do.

Each installed copy is listed with **how** it is reached (“Triple tap → Home”,
“at 07:00 Mon-Fri”), or what to do about it if it is not. Click one to open its
page. **+ Install** adds a blank one; the dropdown beside it adds a ready-made
one. An app already installed offers **+ Add another** instead.

The page also calls out a gesture pointing at a mode that does not exist — a
name left behind by a rename or a deletion. Nothing is repointed for you: the
button fails loudly there rather than quietly doing something nobody chose.

### 4.7 An app's page is the app

Open one of your apps and the first thing on the page is **what it has
actually done**, above its settings. A stopwatch lists its runs — longest,
shortest, average, and how each run compared with the one before it. A tally
shows how many a day held. An alarm shows whether you answered it.

None of this is new data. It is the event log, filtered to that app's own
rows, which is why it costs nothing and why it is only as good as what the app
logs: an app whose event-name field is blank keeps no history, and its page
says so rather than showing an empty list.

An app with **more than one of something** — two alarms, three countdowns —
also lists the others at the top of the page, so you move between them without
going back to the list. One of anything shows no such row; there would be
nothing to move to.

### 4.8 Events — the log, and four ways to read it

**Events** opens on the log: every row, newest first, with the filter bar
above it. Search a name, pick a kind, choose a range. What you filter is what
you export.

Beside **Log** are three pages of charts over the same filtered rows:

| Page | Answers |
|---|---|
| **Overview & Activity** | when you use it — a weekday × hour heatmap, events per day, hour of the day, and what the log is made of |
| **Mode & Time** | where the time goes — total time per app, how long a session lasts, and which apps you open most |
| **Patterns & Metrics** | what gets logged most, and every number the button has recorded, over time |

Two things worth knowing about what they mean.

**Time inside an app is counted from the app's own rows**, not its timers. A
stopwatch writes both, so adding them up would count a stopwatch session
twice — which is why "where the time goes" and "most opened apps" are two
charts: an app you open twenty times for ten seconds and one you open once for
an hour are different facts, and neither chart shows the other.

**Numbers are never pooled.** The log has one number column, and a metronome
puts a tempo in it while a reaction timer puts milliseconds and an alarm puts
a yes-or-no. They share a column and nothing else, so each event name gets its
own panel with its own scale. A single chart of all of them would render
perfectly and mean nothing.

The offline editor has none of this — it has no service behind it, and so no
events at all.

---

## 5. What a mode does

One kind of menu, twelve apps, and a launcher that reaches them:

| Kind | What it is | Getting out |
|---|---|---|
| **Actions** | the menu kind: one action per gesture, answered without taking the button over (§5.1) | — it never takes over |
| **Alarm** | rings at a set time until you stop it, and can act if you *don't* (§5.2) | any press; long press snoozes if you set one |
| **Reminder** | a gentler alarm: shows at a set time, chimes once, gives up on its own after a while | any press |
| **Stopwatch** | times something, with laps (§5.3) | long press stops and logs |
| **Tally** | a count you press up — today's, or a running total it remembers (§5.5) | long press |
| **Intervals** | work/rest blocks — Pomodoro, Tabata or HIIT from the one template (§5.4) | whichever gesture you put "leave" on; long press by default |
| **Metronome** | tap a tempo and the light keeps it, or follow a DAW's MIDI clock (§5.6) | long press |
| **Countdown** | counts a set number of minutes down, the colour walking as the time goes, then rings | long press; at zero it rings until any press |
| **Hot / Cold** | a guessing game: stop a spinning colour wheel on the hidden target | long press (short press stops the wheel) |
| **Reaction timer** | the light goes out at a random moment; press as fast as you can | long press (short press is your answer) |
| **Signal light** | wears one of your positions — Free / Busy / On air — and can send something on each change, which makes it an OSC or MIDI footswitch too | long press (short = next, double tap = send again) |
| **Control surface** | a remote: one command per gesture, held open so you can send several. Bind a gesture to **Launch an app** and it becomes a menu page; give it **positions** and it also shows what the far end says it is doing (§7) | long press |
| **Light show** | plays a playlist of your named looks, one after another (§5.7) | long press (short = next, double tap = hold) |
| **App launcher** | steps through your apps so you don't need a gesture wired to each one | long press (short = next app, **double tap launches**) |

Everything except **Actions** is an *app*: it owns every press until you
leave. Each app's card in the menu says in plain words how to launch it and how
to get back out.

### 5.1 Actions — the everyday menu

A **menu**. Each gesture is mapped to one action; unmapped gestures
do nothing. Pick a different action per gesture from a dropdown.

Available actions:

| Action | What it does |
|---|---|
| **Log an event** | records a timestamped event (meds, habits); counted and streak-tracked |
| **Show a count on the light** | blinks today's count for an event back at you without opening anything: tens as slow pulses, units as quick ones, so 27 is two slow then seven quick. It only reads — it never adds a count of its own |
| **Start / stop a timer** | toggles a named stopwatch; the elapsed time is logged when stopped |
| **Call a webhook** | POSTs to any URL — the IFTTT / Make / n8n / Home Assistant hook. Pick a service and it fills in a template for you, and **Preview payload** shows the exact body before you send anything |
| **Send an OSC message** | fires one OSC message over the network at anything listening — Reaper, QLab, Resolume, TouchOSC, VCV Rack |
| **Send a MIDI message** | sends one note or CC to a MIDI port, for a DAW that speaks MIDI and not OSC. Start from a DAW command (Play, Record, Loop…) and it works unlearned |
| **Launch an app** | opens one of your apps — how you start a stopwatch, a tally or the launcher by hand. The picker shows each app's light beside its name, so you choose the one you recognise rather than the one you remembered naming |
| **Change an app's number** | adds to (or sets) a value an app remembers — "smoking +1" without opening the tally. Only apps that keep a value appear in the picker |
| **Sleep / wake the button** | puts your menus to sleep; the same gesture wakes them |
| **Do several things in order** | one gesture, several actions, each able to wait a moment first. Up to eight steps and ten seconds, and the button is held until the last one finishes. This is how you send a *press and a release* to a DAW that wants a button rather than a trigger, or the *Stop, Stop* that Mackie Control uses for return-to-zero |

**About the count readout.** Zero is a single dim blink rather than no blinks
at all, so "counted nothing today" reads differently from a button that just
sat there. Nothing about it depends on telling colours apart — the *rhythm*
carries the number — so it still works across a warm-tinted room and for a
colourblind reader. And because it only reads, it is safe on a gesture that
some other mode already logs to: you will not double-count anything.

**About seeing what a webhook sends.** A webhook's body is three things
merged: the event's identity (`trigger`, `mode`, `ts`), whatever the app
reports as it finishes, and the payload you typed. Which keys actually arrive
was previously something you found out by standing up a receiver, so every
webhook now has **Preview payload** — the exact body, sent nowhere — and
**Send a test**, which really posts it and reports what came back. Identity
wins over an app's numbers, and your own payload wins over both.

**About changing an app's number.** An app that keeps a value — today, a
tally with *Keep counting past midnight* switched on — can be written from
anywhere, without opening it. Pick the app, pick the value, and choose **add
to it** (the everyday one) or **set it to** (which is how you reset it to
zero). The app shows the same number the next time you open it, because it is
the same number rather than two that agree. An action naming an app you later
delete stays as it is and says so, rather than quietly pointing somewhere else.

**About Sleep / wake.** While asleep the button answers nothing — no tone, no
light, no logged event — except the gesture you bound to this, which is what
wakes it again. The resting light dims to a dark glow rather than going out,
because "off" and "unplugged" have to look different. What sleeps is your
menus *only*: an app already running keeps running, and an alarm you
set still rings, since a stray five-tap should not be able to cancel your
morning. It lasts as long as the service does — restart and the button is
awake. A five-tap is its natural home.

**Where each action works.** Actions appear in three places: on the gestures
of a menu, on the gestures of a control surface, and on a signal light's
positions. Two of them are menu-only. **Show a count on the light** takes
the light over for as long as it counts, and **Sleep / wake** changes what the
*next* press means — both are things only the menu layer handles, so binding
either inside an app gets you the error flash rather than the behaviour.
**Launch an app** works on a menu and on a control surface (that is how one
page opens another), but not on a signal position.

Optional: **Skip if already logged today** — give an event name and the whole
mode is skipped for the rest of the day once that event has been logged (e.g.
a meds reminder that goes quiet after you have taken them).

**Named actions — one action, several gestures.** An action can live in a
shared pool instead of on a single gesture. Name it once under **Named
actions** at the foot of any mode's page (with the other fringe controls,
behind the header's **⚙ Tinker** toggle), then point as many gestures at the
name: the three gestures that all send the same webhook become one thing to
edit rather than three. Naming is optional and most actions never need it — an
action used once is better written straight on the gesture. Rename one in the
menu and everything pointing at it follows. Delete one and the gestures that
named it are left pointing at nothing *on purpose*: the menu shows
"(missing)" and the button says so plainly when you press it, which is more
honest than quietly re-aiming several gestures at something you never chose.

### 5.2 Alarm — rings until you stop it

An **app**. When it activates, the device rings: urgent red/white LED
and a repeating alarm tone. It keeps ringing until you act.

| While ringing | Result |
|---|---|
| **Any press** | dismisses the alarm |
| **Long press** (if snooze set) | snoozes for the configured minutes, then rings again |

Fields:

- **Message** — shown while ringing.
- **Short label** — optional name for status/Bluetooth.
- **Urgent** — on for an alarm's loop-and-hard-flash; off for a gentler
  chime-once-and-breathe (this is the one setting that turns the same app
  into a Reminder — see below).
- **Snooze minutes** — `0` means long-press just dismisses like any other press.
- **Log as** — every clear logs `1` and every miss logs `0` under this name,
  automatically — there is nothing to opt into, it always happens.

Activate an alarm with **At a time** (a real alarm clock) — see §6.

**A dead man's switch.** Set **Give up after** to a number of minutes and give
the alarm an **If nobody answers** action, and it stops being a thing that
waits forever: it rings, and if nothing has answered by then it runs that
action once and stops. A webhook that texts someone, a log row, an OSC
message — anything a hook can run.

Give it an action with **Give up after** still at `0` and the editor's log
says so — that action could structurally never fire. The other half needs no
warning any more: **Log as** already records every miss, action or not.

Each outcome is recorded under the same event name, so **Events** answers "did
I check in?" for both: `1` for answered, `0` for unanswered.

> **It is a nudge, not a safety device.** It runs on this PC. If the service
> stops, the machine sleeps, or Bluetooth drops, the alarm does not ring and
> the switch cannot fire — and it has no way to know that it didn't. Do not
> put it anywhere a missed alert is worse than no alert.


### 5.3 Stopwatch — time something

An **app**. Starting it begins timing (LED shows a running state).

| Gesture | Result |
|---|---|
| **Short press** | lap (records a marker) |
| **Long press** | stop and exit; total elapsed time is logged |

Field: **Timer name** — what the elapsed time is logged as (e.g. `focus`).
Daily totals accumulate, so you can see total focus time for the day.

### 5.4 Intervals — work in blocks (Pomodoro, Tabata, HIIT)

An **app**, and one template behind three ready-made modes: a
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

### 5.5 Tally — count something

An **app**. Opening it starts a tally (LED shows a counting state).

| Gesture | Result |
|---|---|
| **Short press / double tap** | +1 (each is logged, so counts and streaks build up) |
| **Long press** | exit |

Fields:

- **Event name** — what each increment is logged as (e.g. `water`).
- **Keep counting past midnight** — which question the number answers. Off
  (the default), it is *today's* presses and it starts again each day, which
  is what a habit tally wants. On, it is a **running total the app
  remembers**: it survives midnight, restarts and power cuts, and you reset it
  by setting it to 0.

Either way every press is logged, so the Events page, streaks and this app's
own history read the same.

**A running total can be added to from anywhere.** Bind a gesture — in your
everyday menu, on a control surface, anywhere an action goes — to **Change an
app's number**, name the tally and add 1. That is "smoking +1" without
opening the app, and the tally shows the same number when you next do open
it, because it is the same number rather than two that agree.

The action has three parts: which **app**, which of its **values** (a tally
keeps one, called `count`), and whether to **add to it** or **set it to** a
number. Only apps that keep a value of their own appear in the picker.

### 5.6 Metronome — tap out a tempo

An **app**, and the only one with nothing to configure — the tempo is
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

### 5.7 Light show — a playlist for the light

Give it a list of your named looks and it walks them, one every few seconds.
Short press jumps to the next, **double tap holds it** on the one you like,
long press leaves.

The looks do the work. A named look can be a whole stop list — fading, holding
and looping inside a single cue — so a "show" of three cues can run for
minutes without repeating. That is also why cues *name* looks rather than
carrying colours: retune **Ember** once and every show using it changes.

**Seconds per look** has a floor of one second. The flash guard that protects
you elsewhere watches how fast a look flashes *inside itself*; nothing else
watches how fast the show swaps between looks, so this axis has its own floor.

A cue naming a look you have since deleted is left in place and reported, not
skipped — a show quietly one shorter than the list on screen would be worse
than one that shows a gap.

---

### 5.8 Reactions — the button acting on its own

Everything above answers a press. A **reaction** does not: it is a circumstance
with an action attached, and something *outside* the button sets it off.

Give it a name and an action, and it gets an address:

```
POST http://<device>:8080/api/reaction/moisture_low
```

Anything that can make an HTTP request can fire it — a sensor, a cron job, a
deploy script, Home Assistant, an iPhone Shortcut, or `curl` from a terminal:

```bash
curl -X POST http://localhost:8080/api/reaction/moisture_low
```

**If you wired something up before this was renamed, it still works.** These
were called *reflexes*, and `POST /api/reflex/<name>` answers exactly as it
always did and always will — the address is the one thing about this button
that gets written down somewhere you cannot edit from here, so it does not get
retired. Only the word changed.

The action is any action the button already has, plus **Launch an app** — so
"the plant is dry, ring the alarm" is one reaction, and so is "the build passed,
send the MIDI note". A reaction can also point at a **named action**, the same
shared pool a gesture uses, so several reactions can share one webhook.

**Only when — testing what arrived.** Post a flat JSON object and a reaction can
read one field of it: `moisture` `<` `30`. That is the whole test — one field,
one operator, one number, and deliberately no way to write a second condition
(a sensor that needs one can decide for itself and post a different name).

```bash
curl -X POST http://localhost:8080/api/reaction/moisture_low   -H 'content-type: application/json' -d '{"moisture": 12}'
```

**The number is recorded either way.** Whether or not it crossed the line, the
reading lands in the event log under the reaction's name — so the Events page
charts your sensor, not just the times it set something off. A field that is
missing from the body never fires: a renamed sensor key should look like
silence, not like an alarm that will not stop.

**Fired by MIDI, not just by its address.** A reaction can also listen to a MIDI
port: pick *a MIDI note* or *a control change* under **Fired by**, give it the
port and the number, and every matching message arrives as if it had been
posted — `{"note": 95, "velocity": 127, "channel": 1}` — for **Only when** to
test. The URL keeps working either way, which is how you try a reaction out with
the DAW closed.

This is what makes the button hear a DAW rather than guess at it. A control
surface protocol is two-way: the DAW lights the Record lamp on the surface by
sending *note 95, velocity 127* back, and darkens it with *velocity 0*. Point
your DAW's control-surface output at a loopMIDI port, listen on it here, and
"we are recording" becomes a fact that arrived instead of something the button
inferred from what you last pressed — which is the difference between a light
that is right and one that is right until you click something in the DAW.

Three more things worth knowing:

- **A reaction is not a press.** Nothing acks, nothing flashes as if a finger
  arrived; the light shows the result of the action, and what gets logged is
  attributed to no mode, because none was running.
- **A busy button finishes what it is doing first.** Presses made while an app
  owns the button are dropped — their moment has passed — but a reaction waits
  its turn, because a plant that has gone dry still means it. Up to sixteen
  wait; past that the service says no rather than queueing an hour of them.
- **"Only while"** is how a reaction reaches *into* an app that is already
  running. Name the app and the reaction is delivered to it while it runs —
  which is what **Put an app on a position** is for: with a signal light or a
  control surface open, something outside can move it between its positions,
  and the light follows without anyone pressing anything. The position's own
  message is *not* sent when it changes this way — something out there just
  told you that is where you are, and sending it back would be an echo.

A typo in the name is told to you at the moment you make it: posting to a
reaction that does not exist answers `404` and lists the ones that do.


## 6. When it's on

| Setting | For | You set | Behaviour |
|---|---|---|---|
| **Always on** | the menu floor — **Home**, as shipped | — | active whenever nothing else has taken over. Exactly one mode is Always on. |
| **Only during certain hours** | menus | start + end time, optional days | active only inside the window (it may cross midnight, e.g. 22:00–06:00); overrides Home for the gestures it defines |
| **At a set time each day** | Alarm, Reminder | a clock time, optional days | fires at that time and takes over — this is how you set an alarm |
| **Only when another mode starts it** | every other app | — | never starts on its own; you reach it with a **Launch an app** action on a gesture in another mode, or from the App launcher |

Only the two clock-started apps get **At a set time each day**; the other
nine, and the launcher, are started by a gesture and offer only **Only when
another mode starts it**. The menu offers each mode kind exactly the
activations it can actually use, so there is no wrong combination to pick.

With nine apps and six gestures, wiring one gesture per app runs out fast —
that is what the **App launcher** is for. Point one gesture at the launcher
and it steps through your apps: short press moves to the next, double tap
opens it, long press comes home.

How they interact when you press the button:

1. If an **app** is running, the press goes to it.
2. Otherwise the device checks **ambient** modes top to bottom — time-window
   modes first, then the always-on one (**Home**) — and the first one that
   defines the pressed gesture wins. (Same first-match-wins logic throughout.)

A scheduled alarm can fire at any time; if one is due while another app
is running, the alarm takes priority.

---

## 7. Recipes

**Some of this already works.** A button with no config of its own starts with
**Home**, your baseline menu — short press logs `button_press`, double tap
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
Either open **Home** → **Long press** → **Launch an app** and pick a different
app — or leave the gesture alone and edit the **Pomodoro** mode itself, since
Tabata and HIIT are that same app with different numbers in it (§5.4).
Clearing the long press entirely is a fine third option: every app is still a
double tap and a few short presses away through the launcher.

**Add an app without spending a gesture**
Apps tab → Tally → Install → name it "Water" (event `water`) → **Only when another mode
starts it**. That is the whole recipe; there is no second step. The launcher
offers every app in list order unless you name a shorter list, so the new
tally turns up on your double tap with nothing else wired. Open it, tap once
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
a day. Wire that one straight: **Home** → **Triple tap** → **Launch an app** →
**Stopwatch**. Weigh it first, though — there are six gestures and nine apps a
gesture can start, and every longer burst you bind slows the shorter ones
(§2). Note that this is the same triple tap the count readout above wanted:
you get one of the two. That squeeze, in miniature, is why the launcher
exists.

**Wake-up alarm, weekdays at 7 am**
Apps tab → Alarm → Install → name it "Wake up" (message "Wake up", snooze 9,
logged as `woke_up`) → **At a set time each day** 07:00, days Mon–Fri.
At 7 am it rings; tap to dismiss, hold to snooze 9 minutes. This one spends no
gesture at all: a clock starts it, which is why Alarm and Reminder are the
only two kinds offered **At a set time each day** (§6).

**Morning meds reminder that goes quiet once taken**
+ Add menu → "Morning meds" (double tap → Log
`meds_taken`) → **Only during certain hours** 05:00–07:00 → set **Skip if
already logged today** = `meds_taken`. Between 5 and 7, a double tap logs your
meds and the reminder stands down for the day. It is also a clean look at
first-match-wins: inside the window your double tap logs instead of opening
the launcher, and the moment the mode stands down it goes back to opening the
launcher, because Home was underneath it the whole time.

**A transport remote for your DAW** *(verified against Studio One, 2026-08-27)*

Four steps, and the two in the middle are the ones that quietly waste an
evening if you skip them.

1. **Make a MIDI port.** Windows cannot hand MIDI from one program to another
   on its own, so install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html)
   and add one port — call it whatever you like. (Why a third-party download is
   needed at all, and what would remove it, is written up as a project item;
   short version: a hardware controller *is* a MIDI port, and this one is not
   yet.)
2. **Install the app**: Apps tab → **Control surface** → the ready-made
   *DAW remote (MIDI)*. Its gestures come pre-mapped to Record, Stop, Play,
   Click and Loop, and you start it from a gesture like any other app.
3. **Name the port on every binding.** Put part of your port's name in the
   **MIDI port** field. **Leaving it blank takes the first output on the
   machine**, which on Windows is usually *Microsoft GS Wavetable Synth*: your
   DAW hears nothing, the built-in synth hears everything, and nothing reports
   an error.
4. **Tell the DAW it has a control surface.** In Studio One: Settings →
   **External Devices** → **Add…** → **Mackie** → **Control**, and set
   **Receive From** to your port. This is the step that makes note 94 mean
   *Play*. Add the port as a *keyboard* instead and the notes arrive, show in
   the MIDI monitor, get recorded into tracks — and move nothing. If the port
   is already listed under a keyboard device, remove it from that one first.

Now a press moves the transport with nothing learned or assigned, because a
DAW told it has a Mackie Control already knows the note numbers.

**If the DAW wants a press *and* a release** — some do — bind the gesture to
**Do several things in order** instead: the same note at velocity 127, then
the same note at 0 with a wait of `0.05`.

**The other direction** — the DAW telling the *button* what it is doing, so
the light follows the transport rather than guessing — needs a second loopMIDI
port for the DAW's **Send To**, and a reaction listening on it (§5.8). Two
cables, because one carries each direction.

Give the control surface **positions** to show it: a name and one of your
named looks each, say *Stopped* in dark blue and *Recording* in a slow red
breathe. Then one reaction per position, each listening on the return port for
note 95, scoped with **Only while** to the surface, running **Put an app on a
position**. Velocity tells them apart — `velocity == 127` is the DAW's Record
lamp coming on, `velocity == 0` is it going off.

Nothing you press moves a position, and that is the point: arming record *by
clicking in the DAW* turns the light red, because the DAW said so rather than
because the button assumed. A surface with positions and nothing able to
report one **says it is guessing** instead of showing the first as if it were
a fact.

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
| **Tally open** | magenta breathe (2.2 s) | a tally is open |
| **Working** | slow orange breathe (5 s) | an intervals work block is running |
| **Resting** | slow green breathe (5 s) | an intervals rest is running |
| **Metronome running** | amber flash at the tapped tempo | a metronome is open |

The two games, the signal light and the launcher have no state of their own on
this list, deliberately: every frame they show is a colour they worked out for
themselves — how close your guess was, which position you are on, which app
the menu is offering — so a fixed colour would only ever be the wrong one. A
control surface rests on **Listening** between commands, flashing Success or
Error for each one it sends and then going back to waiting — or, if you have
given it positions, going back to whichever position the world last reported
(§7).

| Sound | Tone | When |
|---|---|---|
| **Ack** | single high beep | a press was registered |
| **Success** | rising two-tone | action succeeded |
| **Error** | low triple buzz | action failed |
| **Alarm** | urgent repeating | an alarm is ringing (loops until you stop it) |

Feedback sounds can be turned off on the **Device** tab → **Feedback sounds**.

---

## 9. The dashboard

The header carries the live state, and the **◧ Test panel** button beside
Tips opens the things you press to test with. It is a popover: it appears
when you ask for it, and closes on Escape, on the button again, or on a click
outside it.

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
- **The button is connected and the light works, but pressing it does
  nothing** → that is the switch, not the software. Use the board's own
  **BOOT** button in the meantime: it is a second input, always on, and it
  makes every gesture the real one does. **Press it while the board is
  running, never while it is starting up** — held down at power-on it puts
  the chip into its firmware-loading mode, where it sits silent until you
  unplug and replug it.
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
  menu, back to your menus, every time.

---

Everything in this manual is live, on real hardware: an ESP32 detects your
gestures and shows the lights and tones, the computer runs everything else.
With no button attached, the browser's virtual device stands in for it and
every word above still applies.

Implementation detail and rationale: [DESIGN.md](DESIGN.md) for the mode
machine, [DESIGN-ESP32.md](DESIGN-ESP32.md) for the hardware split. What is
coming next — swappable apps, and a button that keeps working when you walk
away from the computer: [ROADMAP.md](ROADMAP.md).
