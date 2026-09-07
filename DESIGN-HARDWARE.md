# Design: the physical button

**Status: proposal.** Nothing here is decided. It exists because the shopping
cart is open and several of these choices are cheap now and expensive later —
the same reason [ROADMAP.md](ROADMAP.md)'s cross-cutting table exists.

It is **not** a wiring reference. When a part lands, its pins go in
[firmware/hardware.py](firmware/hardware.py) and its capability bit in
[firmware/protocol.py](firmware/protocol.py), which stay the only authoritative
statements of either.

## The answer in one line

> The ESP32-S3 can drive every peripheral on the list. The **battery** cannot,
> the **board you are about to buy** has nowhere to plug them in, and the
> **2.4 GHz antenna** is the part that will actually bite you. All three are
> solvable, and the order matters.

---

## Three constraints, in the order they bind

### 1. Pins — the board, not the chip

The ESP32-S3 die has 45 GPIOs, two I2C, two I2S, four SPI, three UART, RMT
(hardware IR carrier generation), 14 capacitive touch channels and two 12-bit
SAR ADCs. That is more than enough for everything below.

The **Melife S3 Super Mini** this project runs on breaks out roughly eleven
usable pins, and [firmware/hardware.py](firmware/hardware.py) already spends
four of them (button 10, LED data 12, buzzer 5, onboard LED 48) with 0/3/45/46
strapping, 26–32 flash, 33–37 PSRAM and 19/20 USB all excluded.

**This is not actually a pin problem, and that is the important part.** Every
sensor on the wishlist except GPS speaks I2C: IMU, haptic driver, RTC, fuel
gauge, LED driver, NFC, temperature. One bus, two pins, up to 127 addresses.
The pins that must be *dedicated* are few:

| Needs its own pin(s) | Why |
|---|---|
| I2C SDA + SCL | 2 pins, shared by 6–7 parts |
| Button | 1 pin (already GPIO10) |
| IMU interrupt | 1 pin — the whole point is wake-on-motion, which needs a real edge |
| IR receive, IR transmit | 2 pins, RMT-capable (any GPIO) |
| I2S mic (BCLK/WS/DIN) | 3 pins |
| I2S speaker (BCLK/LRCLK/DIN) | 3 pins, or share BCLK/WS with the mic → 4 total for both |
| Solar cell Voc sense | 1 ADC1 pin — **use ADC1**. On the S3, ADC2 is shared with Wi-Fi and arbitrated, so reads can simply fail rather than being locked out. Not worth debugging |
| Touch electrodes | 1 pin each, touch-capable |

Roughly 15 pins for the maximal build. **Buy a board that breaks out more than
eleven.** The ESP32-S3-DevKitC-1 for bench work (every pin, including GPIO15/16);
the XIAO ESP32S3 or a Feather S3 if you want the final footprint to stay small.
Keep a Super Mini too — it is the board the firmware is proven on, and it is the
right thing to leave the current build running.

**No S3 devkit will solve the crystal problem for you.** The ESP32-S3-WROOM-1
module populates only the 40 MHz crystal; X1, the 32.768 kHz position, is marked
`(NC)` — no component — in Espressif's own reference design, and the DevKitC-1
schematic adds none. GPIO15 and GPIO16 *are* XTAL_32K_P and XTAL_32K_N, and they
are broken out as ordinary header pins, which they could not be if a crystal were
fitted. So the Super Mini is not the exception here; nothing is. Buy the RTC.

**Stay on the S3, do not switch to the C6.** The C6 is the better *battery*
part (see below) but the S3 has native USB OTG and
[firmware/spike_hid.py](firmware/spike_hid.py) exists. The C6 has no USB OTG,
only USB-Serial/JTAG. HID keeps you on S3, and that is a fine reason.

### 2. Power — the constraint that kills features

Measured ESP32-S3 figures, and they are not flattering:

| State | Current | 500 mAh cell lasts |
|---|---|---|
| Deep sleep | **13.4 µA** | 4+ years |
| Light sleep | **692 µA** | 30 days |
| BLE connected, duty-cycled (est.) | 1–2 mA | 10–21 days |
| BLE connected, 30 ms interval (est.) | ~12 mA | ~1.7 days |
| Full-face glow, 8 RGB @ 5 mA/ch | **120 mA** | 4.2 hours |

Two things fall out of that table.

**The S3 is the worst modern Espressif part in light sleep** — 692 µA against
the C3's 193 µA and the C6's 220 µA, because the S3's 512 KB of SRAM sits in
several retention domains that each draw current. [ARCHITECTURE.md](ARCHITECTURE.md)
already says "MicroPython → C will not win battery life." Correct, and the
corollary is sharper than the doc states: **the language is not the lever and
neither is the firmware — the silicon is.** The 7-day Stage-4 gate is reachable
on the S3. The 30-day aspiration is reachable only radio-off, and if 30 days
ever becomes a requirement it is a chip decision, made once, at the PCB.

**A full-face glow is affordable because it is an event, not a state.** A 2 s
acknowledgment pulse at 120 mA costs 0.067 mAh — about **7,500 presses per
charge**, which is not the binding constraint on anything. The same 120 mA held
continuously empties the cell in an afternoon. So: bright, whole-face, generous
flashes — yes. An ambient always-glowing pet rock — no, and no battery
chemistry fixes it. That is a constraint on the *looks*, not on the hardware,
and it belongs in the look vocabulary before the enclosure is drawn.

### 3. The antenna — the one nobody writes down

A LiPo pouch is a metal bag. A solar cell has a metal back electrode. An NFC
coil is a metal spiral. A Qi coil is a bigger one. **Every one of those wants
the same flat area directly behind the face, and the 2.4 GHz antenna needs that
area to be empty.**

On a Super Mini the antenna is a PCB trace at the board edge with a keepout
zone. Pack a 40 mm rounded square with a battery, a cell and a coil and you
will detune it — and detuning presents as *intermittent range*, which reads
exactly like a firmware bug and will cost days.

Rules, cheap to follow and expensive to retrofit:

- Antenna at the **rim**, pointing out, with nothing conductive within its
  keepout — no battery, no cell, no coil, no ground pour.
- Battery **behind** the radio in the stack-up, never beside it.
- If NFC or Qi goes in, **ferrite between the coil and everything metal**, and
  the coil gets its own layer in the stack-up. Not an afterthought.
- Test range with the battery installed and the case closed. A bench test with
  the lid off proves nothing.

---

## Full-face light

### The LED family has to change, and the LiPo is why

[firmware/hardware.py](firmware/hardware.py) documents the 3V3 WS2812 fault
(TODO 0c): white comes out orange because the green and blue dies starve on a
3.3 V rail. **A LiPo makes that permanent.** The WS2812C-2020 datasheet is
VDD 3.7–5.3 V with VIH ≥ 2.7 V. A single cell runs 4.2 V down to 3.0 V and
spends most of its life at 3.5–3.9 V — *below* the part's minimum for the back
half of every discharge. So the colour cast would not just persist, it would
drift as the battery drains. Boosting to 5 V costs a converter, its quiescent
current and its noise, to feed parts that then burn 15 mA each.

**Use a constant-current LED driver instead of smart LEDs.** The
**TI LP5024** (or LP5018 / LP5030 / LP5036 for 6/10/12 RGB) is the part:

| Spec | Value | Why it matters here |
|---|---|---|
| Supply | **2.7–5.5 V** | Spans the entire LiPo curve. The fault disappears |
| Channels | 24 (8 RGB) | 12-bit PWM at 29 kHz with dithering |
| Per channel | 25.5 mA, 35 mA when VCC ≥ 3.3 V | Headroom for a bright face |
| Quiescent | **10 µA** power-save, 1 µA shutdown | Sits inside the sleep budget |
| Dimming | **Logarithmic** or linear | The low end of a WS2812 is ugly; this is not |
| Interface | I2C | **No data-timing threshold to fail as flicker** |
| Autonomous | 3-phase PWM shifting, bank control | See below — this one is a real win |

That last row is worth more than it looks. **Bank control plus autonomous PWM
shifting means an idle "breathing" look runs with the MCU asleep.** Today
[firmware/led.py](firmware/led.py) drives every frame from the MicroPython run
loop, which means an idle animation pins the core awake. Move the animation into
the driver and light sleep becomes compatible with a visibly alive button — the
single biggest power/UX unlock on this list, and it costs one I2C part.

Cost: plain RGB LEDs need 3 traces each instead of 1, so this is a PCB decision,
not a breadboard one. Prototype with WS2812s on 5 V from USB; put the driver on
the first real board.

### Getting the whole face to glow evenly

Three options, in increasing order of how good it looks:

1. **Direct array behind a diffuser.** 12–24 LEDs on a grid behind 3–5 mm of
   frosted acrylic. Rule of thumb: **LED pitch ≈ standoff distance** or you see
   hotspots. Thick, hungry, and the easiest to get wrong.

2. **Edge-lit light guide.** 6–8 side-firing LEDs around the rim shooting
   *into* the edge of a clear PMMA disc. Light total-internal-reflects across
   the disc; a sandblasted or laser-etched pattern on the back face scatters it
   out the front. Thin, even, few LEDs, and it is how every LCD backlight works.
   **This is the one to build.**

3. **Light the enclosure itself.** Print the shell in translucent resin or
   light-diffusing filament at 1–1.5 mm wall and let the whole rounded square
   glow, edges included. Best-looking for a worry stone, worst for control —
   light leaks everywhere, including out the back at your leg in a dark room.

Option 2 also happens to solve the solar question, which is next.

---

## Solar, and "can the light shine through a photocell?"

### The literal answer: no, not with anything you can buy

Fully transparent PV is a Michigan State lab result — Richard Lunt's group — at
about **1% efficiency**, against a 5% target.
Commercially available "transparent" panels are semi-transparent
with a tint — 5–15% efficient, passing roughly 40% of visible light — and none
are made at button scale. The transparency/efficiency trade is fundamental:
photons that reach your eye are photons the cell did not absorb.

### The architectural answer: yes, via a light guide

Option 2 above gets it for free. The light guide is **optically clear** and the
LEDs fire in from the **edge**, so:

- Ambient light enters the face, passes straight through the clear guide, and
  reaches a cell mounted flat on the PCB behind it.
- LED light enters at the rim, TIRs, and exits the face.

Both paths use the same window and neither blocks the other. The etched
extraction pattern scatters some incoming light, so budget 40–70% transmission
to the cell. That is a real cost and it is the good deal here.

### The honest numbers, which change the plan

Room lighting is **several hundred times weaker than sunlight** — roughly
0.5–3 W/m² for 200–1000 lux, against 1000 W/m² at AM1.5. Purpose-built indoor
cells (Epishine OneCell: 0.61 V open circuit, 0.50 V at MPP) put out
**17.5 µW/cm² at 500 lux**, which back-solves to about 1.7 W/m² incident — call
it 600× down on full sun. Run that out:

| Scenario | Harvest |
|---|---|
| 9 cm² indoor PV, 500 lux, 12 h/day | **0.51 mAh/day** |
| ...minus deep sleep (0.32 mAh/day) | **+0.19 mAh/day net** |
| what that net funds, at 2 mA duty-cycled BLE | **under 6 minutes of connected radio per day** |
| 9 cm² c-Si, bright window (200 W/m²), 4 h/day | **39 mAh/day** |
| 9 cm² c-Si, direct sun (1000 W/m²), 4 h/day | **195 mAh/day** |

Read those four rows together and the design falls out:

**Indoor harvesting cannot power this device.** Not close. It offsets deep sleep
and buys a few minutes of radio. Any organic/indoor-PV plan is a dead end here,
and it is a dead end by two to three orders of magnitude, not by a factor you can
engineer away.

**Ordinary silicon in actual window light can.** A light-sleep day costs
16.6 mAh; a bright windowsill supplies 39. **A button parked in daylight covers
its own idle and then some**, and in direct sun it refills a 200 mAh cell in a
day. That is a genuinely good feature.

**Which means the solar decision is really a dock decision.** Solar pays only
when the device is parked, face-up, in real light. So if solar is in, so is a
**cradle** — and a cradle is a good idea anyway: it is where the "light pointing
back at the user" constraint in [ROADMAP.md](ROADMAP.md)'s Stage 4 stops
fighting pocketability, and it is where Qi belongs if Qi ever happens.
**[ROADMAP.md](ROADMAP.md) has no dock in it. It should.**

### The charging part

Two paths, and the cheap one is right for you:

- **Outdoor/window silicon → TP4056 or MCP73831.** A 5 V-nominal panel already
  sits near its maximum-power voltage, so a linear charger lands at 70–75%
  efficiency for about a quarter's worth of parts. Measured, published, and
  good enough.
- **Indoor harvesting → BQ25570 / AEM10941 / SPV1050.** 80–90% efficient with
  real MPPT and cold-start from a fraction of a volt, at €4–6 plus an inductor.
  **Mandatory** for indoor light and **pointless** given the row above that says
  indoor light is not a power source. Skip it.

So: **one small c-Si or poly panel, one TP4056, one Schottky, done.** And add
the resistor divider in the next section, because the cell you just bought is
also a sensor.

---

## The worry stone

Ergonomics and optics are the same problem, which is convenient.

**Form.** A squircle (superellipse, n ≈ 4–5) rather than a rounded rectangle —
it is the profile that reads as "smooth" in the hand instead of "rounded off."
Target 40–45 mm across, 10–14 mm thick. Under 10 mm it stops feeling like an
object and starts feeling like a chip; over ~15 mm it stops being pocketable.

**The indent.** A spherical concave dish, radius **20–25 mm**, depth **2–3 mm**,
placed off-centre toward the thumb's natural resting arc rather than dead
middle. Deeper than 3 mm and the thumb gets trapped instead of resting.

**The indent is where three things converge, and that is the design.**

- **Optically**, a concave dish in the light guide is a lens. It will pool
  brightness at its centre. Lean into it — the indent becomes the visibly
  "live" spot, and the face reads as having a focus instead of being a
  uniform slab.
- **Mechanically**, it is where force lands. Put the pressure sensor there.
- **Capacitively**, it is where skin touches. Put the touch electrode there,
  as a ring around the dish.

**Mass matters.** A worry stone that feels good has heft — 40–60 g. A LiPo, a
brass or steel weight ring at the rim, and an LRA's moving mass all help.
Do not fight for the lightest possible build; this is one of the rare cases
where the battery you need is also the ballast you want.

**Material.** Polished PMMA face (machined or cast and hand-polished), shell in
resin or aluminium. Note the conflict: **potting the whole thing in clear
urethane** makes a genuinely waterproof, genuinely stone-like object — and
forecloses USB-C, battery replacement and any repair. That is a real fork, and
the potted version demands Qi, which demands a coil, which fights the antenna.
Decide it before the enclosure is drawn, not after.

---

## Peripheral verdicts

[ROADMAP.md](ROADMAP.md)'s Stage 6 table already ruled on most of this against
one test — *does it make the button smarter, or does it give the button an
interface?* This column adds the second test the roadmap did not have: **does
protocol v1 already have a bit for it?**
[firmware/protocol.py](firmware/protocol.py) reserves `CAP_HAPTICS`,
`CAP_BATTERY`, `CAP_IMU`, `CAP_MIC` and `CAP_OTA`. Those five are pre-blessed.
Everything else spends a new bit — cheap, but a decision.

| Peripheral | Verdict | Part | Cost to the budget | Note |
|---|---|---|---|---|
| **Vibration** | **Yes, first** | DRV2605L + LRA | 4–7 µA standby, ~50–100 mA while buzzing | 2–5.2 V, I2C, **auto-resonance tracking**, 100+ licensed Immersion effects, 1.5 mm package. `CAP_HAPTICS` is already reserved. An **LRA, not an ERM** — crisp clicks instead of a phone-on-a-table rattle, and its moving mass is heft you want. **The one peripheral that works in a pocket, in the dark, in a meeting**, which is exactly the device you are describing |
| **IMU / gyro** | **Yes** | LSM6DS3TR-C, BMI270 or ICM-42670-P | 15–500 µA, **wake-on-motion interrupt** | `CAP_IMU` reserved. Biggest gesture-vocabulary win available, per the roadmap. The real prize is the interrupt: **the button can wake from deep sleep on a shake or a pickup without being pressed.** Needs one dedicated GPIO for INT |
| **Fuel gauge** | **Yes** | MAX17048 | ~23 µA | `CAP_BATTERY` is reserved and there is nothing behind it. A voltage divider is not enough — a LiPo's curve is flat through the middle, so a divider reads "about half" for most of the discharge |
| **RTC** | **Yes — required** | **RV-3028-C7** | **45 nA** | 45 nA at 3 V, **±1 ppm**, crystal integrated, I2C, alarm interrupt, 43 bytes of EEPROM, 3.2 × 1.5 mm. [ARCHITECTURE.md](ARCHITECTURE.md) already calls a 32.768 kHz crystal a BOM requirement for ≤ 2 s/day; this beats it by an order of magnitude in a smaller footprint than the crystal plus its caps, and the alarm interrupt means **scheduled apps can fire from deep sleep**. And it is not optional in the way a crystal would be: **no S3 devkit populates a 32.768 kHz crystal** — not the Super Mini, not the DevKitC-1, because the WROOM-1 module leaves X1 unfitted. There is no board you can buy your way out of this with |
| **Speaker** | **Yes, but** | MAX98357A (I2S) + 8 Ω micro speaker | 10–100 mA while playing | **The S3 has no DAC** — Espressif removed it. So I2S amp, or I2S-PDM into a filter; there is no analog-out shortcut. Needs a sealed cavity and a port, which fights the smooth worry stone. Roadmap's "reading one thing back is fine, a navigable audio menu is a screen" still governs. **If the speaker goes in, the piezo comes out** |
| **Mic** | **Yes** | ICS-43434 / INMP441 (I2S) | ~500 µA active, µA-range sleep | `CAP_MIC` reserved. Can share BCLK/WS with the speaker. Capture, not conversation — transcription stays a host concern. Needs an acoustic port; same enclosure fight |
| **IR emit + receive** | **Yes, cheap** | IR LED + AO3400 MOSFET; TSOP38238 receiver | ~0 idle; 100 mA in pulses | **RMT generates the carrier in hardware** so this costs almost no firmware. And the good trick: **IR passes through acrylic that looks opaque to the eye** (Acrylite 1146 / Plexiglas 3143) — the window hides inside the face and nothing shows. Spends a new capability bit |
| **NFC** | **Yes — but the passive kind** | **ST25DV-I2C**, not PN532 | **zero idle** | A PN532 is a *reader*: ~100 mA with its field up, needing power to do anything. The ST25DV is a **dynamic tag** — passive on the RF side, I2C to the MCU, and it *harvests* from the phone's field: ST's own AN4913 measures up to 3.2 V @ 2.7 mA, or 2.57 V @ 4.9 mA, at 5.5 A/m. Which means: **a phone can read and write the button's config with the battery flat.** [ARCHITECTURE.md](ARCHITECTURE.md)'s degradation table says "phone alone, button flat: changes apply at next connect." A dynamic tag partly deletes that row. Best product-level idea on this list. **Its coil fights the solar cell and the antenna** — ferrite, and settle the stack-up early |
| **GPS** | **No** | — | 25–40 mA continuous | The only item that fails your own tests. 25–40 mA is more than everything else combined (u-blox NEO-M8N: 32 mA acquiring, 30 mA tracking), it needs sky view a pocket does not give, a cold fix takes ~26 s — and **the phone is already a required tier and already has a GPS.** [ARCHITECTURE.md](ARCHITECTURE.md): "no peripheral is allowed to become a hard dependency of the core." Geofencing is a phone-side activation feeding TODO **70**'s sensor slot. **The button should never know where it is** |

---

## What else to include — the ones not on your list

Ordered by value per dollar, and the first three are nearly free.

**1. Capacitive touch. Free, and it changes the gesture grammar.** 14 channels
on-chip, zero added parts — an electrode is a copper pad or a screw. A ring
around the thumb indent gives you **grip detection**: the button knows the
difference between *in your hand* and *in your pocket*. That kills phantom
presses, enables wake-on-pickup, and adds "touched but not pressed" to
[firmware/trigger.py](firmware/trigger.py)'s vocabulary without adding a
control — exactly the test Stage 6 applies to pressure sensitivity.
*Caveat, and it is a real one:* MicroPython's `machine.TouchPad` was **broken on
the S3** — it returned a constant maximum — until a fix merged in November 2024.
Use a current MicroPython build and verify it reads before designing around it.

**2. Ambient light, from the solar cell you already bought.** A divider from the
cell into an **ADC1** pin gives open-circuit voltage, which is a light reading.
Auto-dim at night, know it is in a pocket, know it is face-down. **This is the
useful answer to your photocell question** — the cell is a better sensor than it
is a power source, and it is the same part either way.

**3. Force sensitivity in the indent.** [ROADMAP.md](ROADMAP.md) already grades
pressure "Smarter — widens the gesture grammar without adding a control." An FSR
or a piezo disc under the dish, on an ADC1 pin. A press *and* a squeeze, from
one physical affordance.

**4. A magnet plus a hall sensor.** Dock detection (which the solar plan needs
anyway), fridge-mounting, and a magnet is a genuinely nice worry-stone
affordance — it snaps into its cradle. Watch the LRA and the speaker: both
contain magnets, and they will confuse the hall sensor if they are close.

**5. Temperature and humidity.** SHT40 or similar, I2C, sub-µA idle, a couple of
dollars. Not compelling on its own — compelling because TODO **70** is building
the sensors-as-activations slot and this is the cheapest thing to plug into it.

**6. Reconsider where wireless charging sits.** [ROADMAP.md](ROADMAP.md) files
Qi as Stage 6, "Neutral — convenience, no design impact." **That is wrong.** A Qi
coil, an NFC coil and a solar cell all compete for the same flat area behind the
face, Qi's coil needs ferrite, and the potted-waterproof version of this object
*requires* Qi because it cannot have a USB port. Qi is not a bolt-on convenience;
it is a stack-up decision that has to be made before the enclosure is drawn —
the same slot as the crystal, and for the same reason.

---

## Decisions this proposes baking in

- **Constant-current LED driver, not smart LEDs**, from the first real PCB.
  Resolves TODO 0c permanently instead of moving it to a new rail, and lets the
  face animate while the MCU sleeps.
- **Edge-lit light guide**, which makes full-face glow and solar the same
  window.
- **Full-face light is event-driven.** Bright flashes are nearly free; ambient
  glow is not affordable at any brightness worth having. This constrains the
  look vocabulary, and the constraint should be written down before looks are
  authored against it.
- **Silicon PV plus a linear charger, and a dock.** No indoor-PV harvester,
  because indoor light is three orders of magnitude short.
- **The cell is a sensor as well as a source** — one ADC pin.
- **Haptics first, IMU second.** Both bits are already reserved, both work in a
  pocket, and neither needs a hole in the enclosure.
- **No GPS on the device, ever.** Location is a phone-side activation.
- **Antenna keepout is a first-class constraint**, decided with the stack-up and
  verified with the case closed.
- **Stay on the S3.** The C6 is the better battery part; USB HID is the better
  reason.

## What this refuses

- **A display.** Unchanged, and none of the above is a display.
- **Indoor energy harvesting as a power source.** The number is 0.5 mAh/day.
- **An always-on glowing object.** The battery says no, and pretending otherwise
  designs a look that ships broken.
- **A single board that carries everything at once.** The maximal build is a
  bench rig for finding out which peripherals earn their volume. The product
  gets a subset, chosen from that.

---

## BOM

### Buy now — with the S3 and the LiPo, this cart

| Part | Why | Approx |
|---|---|---|
| **ESP32-S3-DevKitC-1** | The Super Mini runs out of pins immediately. Every GPIO on a header, including 15/16 | $15 |
| **RV-3028-C7** breakout | 45 nA, ±1 ppm. Already a stated BOM requirement, and **no S3 board ships the crystal that would substitute for it**. Alarm interrupt fires apps from deep sleep | $8 |
| **DRV2605L** breakout **+ coin LRA** | Highest-value single addition. `CAP_HAPTICS` is waiting | $10 + $5 |
| **LSM6DS3TR-C** or **BMI270** breakout | `CAP_IMU`. Wake-on-motion is the reason | $10 |
| **MAX17048** breakout | `CAP_BATTERY` has been reserved with nothing behind it | $10 |
| **TP4056** charging module | Handles USB *and* the panel | $2 |
| **Small c-Si solar panel**, 5 V nominal, 30×30 to 50×50 mm | The real-light experiment. Skip anything sold as "indoor" | $5 |
| **Schottky diode** (SS14 or similar) | Panel reverse-current block | $1 |
| 300–500 mAh LiPo **with protection PCM** | Sizes the whole budget. Confirm it has protection — many bare pouch cells do not | $8 |
| Copper tape | Touch electrodes, for free | $5 |

### Buy at the power spike (ROADMAP 3c)

A **USB power monitor or current-sense meter** — a Nordic PPK2, or a shunt plus
a scope. Every number in this document is either measured by someone else or
estimated, and [ROADMAP.md](ROADMAP.md) 3c exists to replace them with yours.
**Buy this before buying any more peripherals**: it is the instrument that
decides which of them the battery can afford, and without it the rest of the
cart is guesswork.

### Buy when the enclosure is real

| Part | Note |
|---|---|
| **LP5024** or LP5036 + plain RGB LEDs | Needs a PCB. Prototype with WS2812s on USB 5 V first |
| Cast or machined **PMMA** light guide | The optics experiment. Sandblast the back, test the extraction pattern before committing to a geometry |
| **ST25DV-I2C** + coil + **ferrite sheet** | And settle the coil/cell/antenna stack-up in the same sitting |
| **MAX98357A** + 8 Ω micro speaker | Only once the cavity and port are drawn |
| **ICS-43434** I2S mic | Same |
| IR LED + AO3400, **TSOP38238**, IR-pass acrylic | Cheap, but the window is an enclosure feature |
| **SHT40** | Whenever TODO 70's slot exists |
| Brass or steel weight ring | Heft. Do not skip it — it is most of why the object will feel good |

**Not on any list: a GPS module.**

---

## The four things to actually measure first

Everything above is a proposal resting on other people's numbers. These four
turn it into a design, and they are cheap:

1. **Does the light guide work?** Sandblasted acrylic, 6 LEDs at the rim, a
   phone camera. An afternoon, and it decides the whole optical architecture.
2. **What does the panel make on your actual windowsill?** Not in a datasheet —
   in West Jordan, in the window the button would sit in, in February. This
   decides whether solar is a feature or a decoration.
3. **The four numbers from [ROADMAP.md](ROADMAP.md) 3c** — idle-connected draw,
   advertising draw, light-sleep draw, wake latency. They size the battery,
   which sizes the enclosure, which constrains everything else.
4. **BLE range with the battery in and the case shut.** Before the enclosure is
   final, not after.
