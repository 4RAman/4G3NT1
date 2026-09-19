# The scene library

An index of what is actually in [scenes/library/](../scenes/library/) today
(TODO **114**). Each file there is a scene - a raw dict layered over
`config.json` inside `load_config_full`, the same mechanism `scenes/default.json`
and `scenes/personal.json` already use - with four header fields a picker
reads before it loads anything: `title`, `blurb`, `for`, and `assumes`.

**This set is incomplete.** Thirteen scenes exist; the research they are
drawn from ([ARCHETYPES.csv](../ARCHETYPES.csv)) scores thirty archetypes.
The first seven were written in one run, cut short by a spend limit
mid-sprint; a second pass (also TODO 114) added the next six by score -
Nerds/collectors/fandom, Sports fans, Events & entertainment fans,
Gigging/live performers, Remote & hybrid desk workers and Home automation
people. Seventeen archetypes remain unwritten, one of them (**The household
button**, 67) deliberately skipped for now because it is blocked on the
multi-button work TODO **116** names. Nothing below should be read as "the
library," only as what has shipped so far.

**On archetype 9 versus `desk-default`.** Before writing "Remote & hybrid
desk workers" (archetype 9, score 71), it was checked against `desk-default`
(archetype 29, "The desk generalist," score 81) for overlap - CLAUDE.md's "no
two scenes that are the same scene" rule. They are not the same: `desk-default`
is the honest, hand-configured all-purpose scene with no automation, and the
new `on-a-call` scene exists specifically *because* it does something
`desk-default` cannot - a status light a calendar's own secret feed URL can
flip on its own, ten minutes before a meeting starts, with nobody touching the
button. That is a real, working feature (`poll.py`'s iCalendar reader, shipped
for TODO 99/100), not a restatement of the generalist scene with different
words.

## The thirteen

| Scene (file) | Title | For | Assumes |
|---|---|---|---|
| `desk-default` | The Desk Default | Anyone with a computer and a desk who wants one object doing the four small things they reach for all day, rather than a niche use. | a voice-chat or conferencing app with a global mute hotkey |
| `game-night` | Game Night Rig | PC gamers who want a physical key outside the keyboard, and a light that means something without alt-tabbing to check. | a voice-chat app with a global mute hotkey |
| `gm-table` | The GM's Table | Weekly tabletop game masters who want a physical prop at the table, not another screen. | *(none)* |
| `home-studio` | Home Studio | Solo producers and songwriters working in a DAW most evenings. | a DAW; a loopMIDI port named "Button" |
| `streamers-deck` | Streamer's Deck | Twitch/YouTube/TikTok streamers running OBS at a busy desk. | OBS Studio with matching global hotkeys (Settings > Hotkeys); a voice-chat app with a global mute hotkey |
| `time-not-numbers` | Time, Not Numbers | People who are time-blind, pay a real cost to task-switch, and want an off-screen way to feel time passing. | *(none)* |
| `tinkerers-bench` | Tinkerer's Bench | Makers who read the schematic before the manual and want to see the whole vocabulary in one file before they start editing it. | an external script that can POST to the button's REST reflex endpoint |
| `collectors-shelf` | Collector's Shelf | Collectors and fandom-deep fans who want a shelf object that wears their colours at rest and looks up the moment something worth knowing happens. | an external script that can POST to the button's REST reflex endpoint |
| `matchday` | Matchday | Season-ticket holders and watch-party hosts who want their team's colours on the desk and an easy way to mark the big moments without checking a score app. | an external script that can POST to the button's REST reflex endpoint |
| `festival-wristband` | Festival Wristband | Concert, festival and con-goers who want a light-up keepsake that is actually theirs - configured once, and ready again at the next show. | *(none)* |
| `stage-cues` | Stage Cues | Gigging musicians running backing tracks and patch changes who need one hand-reachable control that works without a glance. | a DAW; a loopMIDI port named "Button" |
| `on-a-call` | On a Call | Remote and hybrid workers whose desk sits by a door people walk through, who want the do-not-disturb light to know about a meeting before they do. | a voice-chat or conferencing app with a global mute hotkey; a calendar that publishes a secret .ics link (Google/Outlook/iCloud "secret address in iCal format") |
| `smart-home-panel` | Smart Home Panel | Home Assistant and MQTT tinkerers who want one physical control wired into automations they already have, not a phone app nobody else in the house opens. | an external script that can POST to the button's REST reflex endpoint |

**The blurbs, in full** - each is one sentence, written to answer "what does
pressing this button actually do":

- **The Desk Default** - "One button, four things: a focus timer, a mute
  key, a do-not-disturb light, and a shortcut - the honest all-purpose scene
  for anyone at a computer."
- **Game Night Rig** - "A push-to-talk toggle you can feel without looking,
  three macro presses beside your mouse hand, and a light that says whether
  your mic is live."
- **The GM's Table** - "A press sets the room's mood light, a second app
  steps through whose turn it is - a table-side prop that does two jobs
  without a laptop open."
- **Home Studio** - "Arms record, drops a marker and taps tempo without
  leaving the take - the light doubles as your DAW's transport state."
- **Streamer's Deck** - "The LED is your on-air light and it is on camera -
  one press flips the scene, one mutes the mic, one starts the clip."
- **Time, Not Numbers** - "Start a timer with one press and watch time pass
  as colour instead of digits - no screen, no nagging, no app to open."
- **Tinkerer's Bench** - "A stocked reference config, not a demo - one of
  every look shape, a reflex listening for a webhook, and a control surface
  wired to a generic script hook, all ready to rename."
- **Collector's Shelf** - "Sits on the shelf in your fandom's colours, flares
  when a script spots a restock or a drop, and keeps the tally of every
  grail you've landed."
- **Matchday** - "Idles in your team's colours, steps through the stages of
  the game with a press, and tallies every scoring play."
- **Festival Wristband** - "A press cycles the crowd moments you actually
  want at a show, a light show plays your own sequence for the encore, and a
  tally keeps count of every event you've brought it to."
- **Stage Cues** - "One press panics the backing track to silence, a second
  opens patch-and-transport control wired to your rig over MIDI, and a
  tally counts the sets you've played."
- **On a Call** - "One press mutes your call and flips the light to busy;
  ten minutes before your calendar's next meeting, it goes red on its own."
- **Smart Home Panel** - "A control surface fires the automations you
  already built over webhook, and the light mirrors whatever your setup
  already knows - a door open, the laundry done, someone home."

## The `assumes` vocabulary

`assumes` is a list of plain-English strings naming the external things a
scene needs that this machine might not have - the picker's honest-degradation
warning (TODO 114) reads these, so **one vocabulary across every scene
matters more than any single phrase reading well on its own**: a picker that
has to recognise "a voice-chat app" and "a voice-chat or conferencing app" as
the same requirement is a picker that cannot recognise anything reliably.

**114b's picker has since landed** (`aibutton/scenes.py`'s `ASSUMPTIONS` and
`ASSUMPTION_ALIASES`), and it is the machine's copy of this same vocabulary -
this section is the curator's copy, and the two must not drift. The canonical
phrases, one row each:

- `a voice-chat or conferencing app with a global mute hotkey` (`desk-default`, `on-a-call`) -
  `game-night` and `streamers-deck` still write the shorter `a voice-chat app
  with a global mute hotkey`; the two-word drift this section used to flag is
  now papered over by `ASSUMPTION_ALIASES` rather than by editing either
  scene, so both phrasings resolve to one requirement in the picker. New
  scenes should still write the longer form - the alias exists for what
  already shipped, not as licence to keep drifting.
- `OBS Studio with matching global hotkeys (Settings > Hotkeys)` (`streamers-deck`)
- `a DAW` (`home-studio`, `stage-cues`)
- `a loopMIDI port named 'Button'` (`home-studio`, `stage-cues`)
- `an external script that can POST to the button's REST reflex endpoint`
  (`tinkerers-bench`, `collectors-shelf`, `matchday`, `smart-home-panel`)
- `a calendar that publishes a secret .ics link (Google/Outlook/iCloud
  "secret address in iCal format")` (`on-a-call`) - **new**, added for this
  run. `on-a-call` needed something none of the first seven scenes did: a
  reflex that polls a URL and reads it as iCalendar (`poll.py`, TODO 99/100),
  which is a real, working way to make a light change on its own before a
  meeting. Nothing in the first six phrases said "calendar," so this is a
  genuine seventh phrase rather than a rewording. It carries no probe (no
  code can see whether *your* calendar publishes a secret address), so it
  shows and degrades exactly like `a DAW` does - listed, never checked -
  which `ASSUMPTIONS` already does correctly with no row at all; the row that
  has since been added there only supplies the sentence explaining why.

`gm-table`, `time-not-numbers` and `festival-wristband` assume nothing beyond
the button itself, which is worth keeping true rather than padding with a
speculative entry - `assumes` is a warning list, and a warning that fires for
nothing is the kind that trains people to ignore the next one.
