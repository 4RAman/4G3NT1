# The light library format

What a row is, what gets rejected, and what the browser fetches (TODO **113**).

Two audiences, and the document is written for both:

- **Curating the table** — sections 1 to 4. No code. Section 4 is a brief you
  can paste straight into an LLM.
- **Building the page** — sections 5 to 7. Especially section 7, which is the
  one that is easy to get wrong and impossible to notice.

The importer is [tools/import_light_library.py](../tools/import_light_library.py);
the tests are [tests/test_light_library.py](../tests/test_light_library.py).

```bash
./.venv/Scripts/python tools/import_light_library.py                     # seed from schema.js
./.venv/Scripts/python tools/import_light_library.py --source looks.csv  # a curated table
./.venv/Scripts/python tools/import_light_library.py --source looks.csv --dry-run
```

---

## 1. A row

Six fields. Nothing else is read, and anything else in a `look` is a
rejection.

| field | what it is | example |
|---|---|---|
| `id` | a stable slug. Lowercase letters, digits and hyphens. **Never reused**, ever, for anything else. | `flag-jp` |
| `name` | what a person reads. Trademark-safe — see section 3. | `Rising Sun - White & Red` |
| `tags` | what search matches on. Lowercase words. This is where a row becomes findable. | `flag, japan, asia, red, white, minimal` |
| `family` | **one** colour family, for the filter chips. From the closed list below. | `red` |
| `group` | the coarse bucket, and also the file the row is shipped in. | `flags` |
| `look` | the body — what the light actually does. Three shapes, section 2. | see below |

**The families**, and it is exactly these — a facet is a closed set or it is
not a facet:

```
red  orange  yellow  green  teal  cyan  blue  indigo  violet
magenta  pink  brown  white  grey  black  rainbow
```

Leave `family` blank and the importer works one out from the look's brightest
colour, and says how many rows it had to do that for. That is a safety net,
not the plan: a curator filing a look deliberately always wins.

**A seventh thing every row carries on the way out, and it is never a column
in the way in: `quiet`.** Section 6 has the rule; the short version is that
`family` is a fact a curator may know better than the derivation, so stating
it wins - but `quiet` is a claim about how comfortable a look is to sit near,
and that is not something this tool takes a curator's word for. It is always
computed, on every row, the same way the flash floor itself cannot be talked
down.

**Tags are the whole game.** The advertised number is meaningless if nobody
can reach row 6,000. Give every row the obvious search words *and* the
non-obvious ones: what it depicts, where it is from, what mood it is, what you
would use it for, and every colour in it by name.

---

## 2. The three shapes a `look` can take

### A plain effect — one colour and one style

```json
{ "style": "breathe", "color": "#ff7a1a", "color2": "#000000", "period_s": 2.5 }
```

- `style` is one of `solid`, `breathe`, `flash`, `alternate`, `rainbow`, `fade`.
- `color` is `#rrggbb`. Required.
- `color2` only means anything on `alternate` and `fade` (the second colour)
  and on `rainbow` (where it is the cycle's *saturation*, brightest channel,
  `#000000` meaning full). On every other style it is dropped, because a
  colour nothing renders is invisible clutter.
- `period_s` is one full cycle in seconds. `solid` ignores it.
- On `rainbow`, `color` is not a hue — it is the *brightness*, taken from its
  brightest channel, with `#000000` meaning full.

### A stop list — a walk between flat colours

```json
{ "stops": [
    { "color": "#00ff2a", "hold_s": 0.1 },
    { "color": "#000000", "hold_s": 0.08 },
    { "color": "#00ff2a", "hold_s": 0.5, "fade_s": 0.2, "curve": "ease_out" }
  ],
  "repeat": false }
```

- Each stop: `color`, `hold_s` (how long it stays), `fade_s` (how long
  arriving takes, `0` is a hard cut), `curve` (one of `linear`, `ease_in`,
  `ease_out`, `ease_in_out`, `exponential`).
- **A stop is one flat colour.** It cannot flash or breathe on its own. A
  flash is three stops: on, off, on.
- `repeat`: `true` loops forever, `false` plays once.
- `drive` (optional, default `clock`): what moves it along.
  - `clock` — seconds. Works anywhere.
  - `progress` — `hold_s`/`fade_s` are read as *weights* across a countdown or
    a pomodoro block, `0` to `1`.
  - `beats` — same, but across a metronome's bar.
  A `progress` or `beats` row that never changes colour is rejected: it is a
  flat colour with extra steps.

### A Morse message

```json
{ "morse": "SOS", "dpm": 300, "color": "#ff0000" }
```

Kept in this compact form all the way through — the button expands it. `dpm`
is dots per minute; above about 360 it trips the safety floor (section 6).

**The `messages` group is Morse, curated, and it is pure curation with no new
code:** `aibutton/morse.py` (TODO 83) already turns any text into a stop
list, so the row is just the text somebody would recognise. The checked-in
table is [data/light-library/messages.csv](../data/light-library/messages.csv)
— data, not a list hardcoded into the importer, so curating more of it is a
spreadsheet edit. **Length is the enemy**: Morse is up to five symbols a
digit and four a letter, so a long message is a light show nobody watches to
the end. `MAX_MORSE_MESSAGE_CHARS` in the importer (**12**, trivial to
retune) rejects anything longer, checked on the written message before the
parser ever expands it — a `look`-kind rejection like any other malformed
body, not a special path. `tags` carry the plaintext (`sos`, `on air`, …) so
a search for the word finds the row; `name` reads as the message itself, not
as dots and dashes.

---

## 3. The naming policy — read this one

> **Colour pairs are not protectable. Club, franchise and brand names are.**
>
> **The `name` stays generic. The trademark goes in the `tags`.**

```
name  "Green Bay - Green & Gold"      <- ships, appears on screen
tags  green bay, packers, nfl, ...    <- searchable, never displayed as a claim
```

Somebody typing "packers" still finds the row. Nothing the product *ships*
claims the name.

**What is checked, and what is not.** Rows in a trademark-sensitive group get
their *name shape* checked: it must read
`<Place or generic label> - <Colour> & <Colour>`, and every word after the
dash must be a colour word. Anything else is reported under `NAMING` and the
run exits non-zero (pass `--allow-names` to override deliberately).

The sensitive groups are listed in `TRADEMARK_SENSITIVE_GROUPS` in the
importer — `teams`, `clubs`, `franchises`, `brands`, `esports`, `colleges`,
`universities`, `sports`. **Add a group slug there when you add a bank of club
or brand colours.**

This is deliberately a list of *groups*, not a list of trademarks. A blocklist
of brand names would be endless, wrong within a month, and would miss exactly
the row somebody added last. And it warns rather than deletes, because a
heuristic that eats content is a heuristic somebody switches off.

**Flags, holidays, colour theory, nature and Morse carry no such problem.**
Name those whatever reads best.

---

## 4. The brief to hand an LLM

Everything above, compressed to something you can paste. Adjust the count, the
theme and the group.

> Produce a CSV with exactly this header row:
>
> `id,name,tags,family,group,style,color,color2,period_s`
>
> One row per lighting preset for a product with a single RGB LED. Produce
> **200** rows covering **national flags**.
>
> - `id` — a unique lowercase slug, letters/digits/hyphens only, e.g.
>   `flag-jp`. Never repeat one.
> - `name` — the display name, in Title Case.
> - `tags` — **pipe-separated** (`|`), lowercase, at least five per row. Include
>   what it depicts, its country or region, its mood or use, and every colour
>   in it by name. Search runs on these, so be generous.
> - `family` — exactly one of: red, orange, yellow, green, teal, cyan, blue,
>   indigo, violet, magenta, pink, brown, white, grey, black, rainbow.
> - `group` — `flags` for every row in this batch.
> - `style` — exactly one of: `solid`, `breathe`, `flash`, `alternate`,
>   `rainbow`, `fade`.
> - `color` — `#rrggbb`, lowercase.
> - `color2` — `#rrggbb`, but **only** for `alternate` and `fade`; leave the
>   cell empty for every other style.
> - `period_s` — one full cycle in seconds, a number. Use `1` for `solid`.
>
> **Hard safety rule:** if `style` is `flash` or `alternate`, `period_s` must
> be **at least 0.34**. Anything faster is a seizure risk and will be thrown
> out.
>
> **A softer note, not a rule:** a `flash`/`alternate` row easily clears that
> floor at 0.4-0.9s and still reads as an alarm from across a room. The
> library files anything at `period_s < 1.0` as "busy" and anything at or
> above it as "quiet" (a searchable filter, not a rejection) — so a batch that
> is all 0.4s flashes ships fine but gives someone nothing to pick for a
> shared room. Spread `period_s` across the range rather than clustering it
> just above the safety floor.
>
> **Naming rule:** colour pairs are not protectable, but club, franchise and
> brand names are trademarks. If a row is a team's or a brand's colours, the
> `name` must be generic — `Green Bay - Green & Gold`, never
> `Green Bay Packers` — and the team or brand name goes in the `tags` instead.
> Flags, holidays and colour theory have no such restriction.
>
> Prefer looks that are **visibly different from each other**. Two rows that
> differ only slightly in colour or by a fraction of a second get merged into
> one, so near-identical variants are wasted rows.
>
> Output only the CSV. No commentary, no code fences.

For **stop-list** rows, swap the last four columns for a single `stops` column
holding a JSON array (quoted, since it contains commas), plus optional
`repeat` and `drive` columns. A `look` column holding the whole JSON object
also works, and is the easiest thing for a model to get right.

JSON is accepted too: either a top-level array of row objects, or
`{"rows": [ ... ]}`, each row carrying `id`, `name`, `tags` (an array),
`family`, `group` and `look`.

---

## 5. What the importer does to the table

Run it and read the report. The report is the deliverable — a rejection nobody
sees is a clamp with extra steps.

```
light library import
  read       : 8412 rows
  rejected   : 37
  collapsed  : 1904 near-duplicates merged into their keepers
  accepted   : 6471 (142 curated, 6329 generated)
  groups     : 24
  families   : red 812, blue 774, green 690, ...
  written    : index.json + 24 shard(s), 1841.2 KB

REJECTED (37)
  flag-xx    parser   config: library[flag-xx].color must be a colour like "#ff8800" - using #0000ff   [flags.csv:412]
  siren-3    floor    flash at 0.2s is under the 0.333s flash floor - slow it down, or use a style
                      outside alternate/flash   [flags.csv:889]
  pulse-9    look     unknown key(s) in an effect: perod_s   [moods.csv:31]

NAMING (2) - a club or franchise name belongs in the tags, not the name
  team-gb  'Green Bay Packers': name must read "<Place or generic label> - <Colour> & <Colour>"
```

Every rejection carries the row's **id**, the **kind** of problem, the reason
in the parser's own words, and **where it came from** — `flags.csv:412` is a
line number you can jump to in a spreadsheet of any size.

The five kinds:

| kind | means |
|---|---|
| `row` | the row itself is unusable — no id, no tags, a family outside the list |
| `look` | the body's keys are wrong, or a stop list says nothing |
| `parser` | the real config parser would have fallen back on a field |
| `floor` | the safety floor would have had to rewrite it — section 6 |
| `duplicate` | that `id` was already used by an earlier row |

Exit code is `0` only when there are no rejections and no naming flags.

**One normalisation, and only one.** A `color2` on a style that never renders
it is dropped. That cannot change what the light does, which is exactly why it
is allowed where clamping is not.

**What ships is the parser's own output.** Every accepted look is re-built
from what the config parser produced, so the bytes in the library are by
construction the bytes the parser makes. Keys equal to the parser's defaults
are left out to save space — omitted means default, on both sides. (Morse is
the exception: it keeps its written form, because expanding "SOS" is two
hundred stops and the compact form is what a config stores anyway.)

---

## 6. The two rules a row cannot argue with

### The flash floor is a gate, never a clamp

CLAUDE.md: clamping a setting silently makes it a lie. Clamping a *preset* is
worse — the swatch that sold it renders one thing and the button does another.
So a row the floor would rewrite is **rejected with a reason**, exactly as
[appc.py](../aibutton/appc.py)'s `_look_bytes` applies the floor where the
bytes are made.

Both floors apply, through the same functions the running button uses:

- **`config.flash_safe`** — a `flash` or `alternate` style needs
  `period_s >= min_flash_period_s` (3 Hz, WCAG 2.3.1, `0.334` at the default).
  `breathe` and `fade` cross the same distance smoothly and are not floored.
- **`config.sequence_safe`** — every stop's *dwell* (`hold_s + fade_s`) needs
  to be at least **half** the flash period (`0.167` at the default). A stop
  list has no period, so the floor is defined over its transitions.
  **Exempt: a one-shot of three stops or fewer** — the confirmation-flash
  rule. A handful of transitions played once sustains nothing.

`--min-flash-period` gates against a different number, for a config that moved
the setting.

### The quiet facet is a preference, never a gate

TODO 108's honest finding: the floor above is a *safety* threshold sized for
a display filling the visual field, and it says nothing about whether a fast
blink is pleasant to sit near. A look that clears it can still be the wrong
thing to leave running next to someone's desk — so the importer also computes
`quiet`, a plain preference filter over rows that already passed the gate
above. **The two must never be confused.** The floor rejects a row outright
and a rejected row does not exist; `quiet` never rejects anything — it only
says which surviving rows are calm enough for a shared room, so the page can
offer "hide anything busy" as a checkbox rather than as a second silent
clamp wearing the first one's name.

`QUIET_MIN_PERIOD_S` (default **1.0 s**, three times the flash floor) is the
one number behind it, and it is a judgement call stated as one, not a
measurement. A `flash` or `alternate` style clears the safety floor at
0.333s but reads as *quiet* only once its full cycle is about a second or
slower — roughly "a deliberate blink"; anything faster starts to read as an
alarm from across a room. `breathe`, `fade`, `solid` and `rainbow` never
hard-cut, so they are quiet by construction whatever their period — the same
set `device.STYLE_STROBES` names for the opposite reason. A stop list has no
`style` to check, so what is judged is its *fastest transition*, not any one
stop's dwell — two adjacent short holds read as a strobe even if every other
stop in the list is slow — with the same one-shot-of-three-or-fewer
exemption `sequence_safe` already makes: a handful of transitions played
once cannot sustain a strobe either way.

Every accepted row carries its own `"quiet": true|false`, and the counts are
also a facet in `index.json` — `{"id": "quiet"|"busy", "count": …}` — exactly
like `group` and `family`, so a chip can be drawn before any shard is
fetched. Change the threshold by editing the one named constant; nothing
else reads it.

### Dedupe on perceptual distance

TODO 113: *"a library of 8,000 looks anybody can find in three keystrokes
beats 40,000 nobody can tell apart."* Two rows are one look when:

1. the **style class** matches exactly (a flash is not a breathe; a
   clock-driven repeat is not a one-shot);
2. the **rates** are within `--rate-ratio`, default **1.25** — rate is
   perceived logarithmically, so "the same speed" is a ratio, not a
   difference. `solid` has no rate at all, so two solids of the same colour
   are one look whatever their `period_s` says;
3. every corresponding **colour** is within `--delta-e`, default **5.0**, in
   CIELAB (CIE76). A laboratory just-noticeable difference is about 2.3; 5 is
   deliberately looser, because the thing rendering this is one diffused LED
   across a room.

A stop list's colours are its **rendered** samples — 16 points across one
cycle — so two lists that look the same collapse however differently they were
written.

**The survivor inherits the loser's tags.** That is the point, not a
politeness: collapsing "Rising Sun" and "Denmark Red" into one red is only an
improvement if both words still find it.

**Curated rows never collapse.** A row marked `curated` (and everything
`--seed` emits) is kept whole; a generated row that lands on one is the one
that goes.

**Changing the thresholds.** `--delta-e 3` gives a bigger library with more
near-neighbours; `--delta-e 8` gives a smaller, sharper one. Same for
`--rate-ratio`. Advertise the number that comes out of the run, not the number
that went in. For calibration: 20,000 randomly-coloured breathe looks collapse
to about 8,200 at the defaults.

---

## 7. What the browser fetches

```
aibutton/web/library/
  index.json         the manifest - counts, facets, and the shard list
  alert.json         one shard per group
  calm.json
  countdown.json
  ...
  bulk-2.json        a group over --max-shard-rows splits into numbered parts
```

**Why shards by group rather than one file.** 30,000 rows is ~4 MB, and
schema.js is an ES module the browser parses before the editor draws — TODO
113's first limit. Sharding by `group` makes the *browse* axis and the *fetch*
axis the same axis: picking a group chip is one bounded fetch, which is the
common case. No shard exceeds `--max-shard-rows` (default 2000), so no single
request is ever the thing blocking the page.

**Why a manifest rather than a directory listing.** The page has to draw its
chrome — group chips and family chips, each with a count — *before* it has any
rows. `index.json` carries those counts, the shard list with row counts and
byte sizes, and the settings the library was built at. A free-text search
fetches shards in manifest order and merges as they land; the row counts are
what let the page say "searching 12 of 24 groups" honestly instead of
freezing.

`index.json`:

```json
{
  "format_version": 1,
  "generated": "2026-09-09",
  "generator": "tools/import_light_library.py",
  "fallback": "aibutton/web/static/schema.js:LOOK_PRESETS",
  "settings": { "delta_e": 5.0, "rate_ratio": 1.25,
                "min_flash_period_s": 0.333, "max_shard_rows": 2000 },
  "counts":   { "total": 142, "curated": 142, "generated": 0 },
  "facets": {
    "group":  [ { "id": "alert", "label": "Alert", "count": 6 }, ... ],
    "family": [ { "id": "red", "count": 25 }, ... ],
    "quiet":  [ { "id": "quiet", "count": 118 }, { "id": "busy", "count": 24 } ]
  },
  "shards": [ { "file": "alert.json", "group": "alert", "label": "Alert",
                "part": 1, "rows": 6, "bytes": 1168 }, ... ]
}
```

A shard:

```json
{ "format_version": 1, "group": "alert", "label": "Alert", "part": 1,
  "rows": [ { "id": "klaxon", "name": "Klaxon", "tags": ["alert","klaxon","flash"],
              "family": "red", "group": "alert",
              "look": { "style": "flash", "color": "#ff0000", "period_s": 0.5 },
              "quiet": false, "curated": true } ] }
```

Sniff a `look`'s shape by its keys, the way `presetIsSequence` does in
schema.js: **`stops` present** is a stop list, **`morse` present** is a Morse
message, otherwise it is a plain effect. `curated` is absent on generated rows.

`format_version` goes up only when the *shape* changes in a way a page written
against the old one would misread. Adding a key nothing reads is not that.

### Two things the page author must not get wrong

**1. The library is not served yet.** The static mount in
[webui.py](../aibutton/webui.py) covers `/static` → `aibutton/web/static`
only. Serving this directory is one line beside it:

```python
app.mount("/library", _NoStoreStatic(directory=_WEB / "library"), name="library")
```

**2. The page MUST work with no library at all.**
`tools/build_editor.py` inlines schema.js into a single offline HTML file.
There is no server, so there is nothing to fetch, and a page that waits for
`index.json` is a page that never draws. So:

- Try `index.json`. **Any failure — 404, a file URL, a parse error — is a
  normal state, not an error.** No dialog, no console noise.
- Fall back to the curated `LOOK_PRESETS` already inlined in schema.js. The
  manifest names that fallback in its `fallback` field so the contract is data
  rather than folklore.
- Say which one is showing. "142 built-in presets" and "6,471 in the library"
  are honestly different things, and a user who searched and found nothing
  deserves to know they were searching the small one.
- The *shape* of a `LOOK_PRESETS` entry is not the shape of a library row —
  it carries `label`, and its body is under `effect`/`sequence` rather than
  `look`. Map it once at the boundary; do not teach the page two shapes.

### And one that is not a mistake

**A preset is a starting point, never a stored thing.** Picking one *copies*
its body into the look being edited. Nothing in the library reaches
`config.json` — no id, no reference. That is the only reason it can be this
big at all, and it is why an id that is never reused matters more than an id
that is stable.
