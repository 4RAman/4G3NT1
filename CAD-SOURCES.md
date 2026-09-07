# CAD sources for the button

**Status: reference.** Companion to [DESIGN-HARDWARE.md](DESIGN-HARDWARE.md).
Updated for the no-solar, no-light-guide, direct-lit build.

## Read this before downloading anything

**"CAD" means two unrelated things here, needed at different times.**

| | What it is | When you need it | Where it comes from |
|---|---|---|---|
| **ECAD** | Schematic symbol + PCB footprint (+ a small 3D body for the board view) | When you draw the schematic and lay out the board | SnapMagic, Ultra Librarian, DigiKey, KiCad's own libraries |
| **MCAD** | A 3D solid, usually STEP, of the real physical object | When you draw the enclosure and check that things fit | Manufacturer download pages, GrabCAD, vendor GitHub repos |

**You need almost none of it yet, and here is the arithmetic that says so.** A
52 mm squircle has about **2,500 mm²** of face area. Twelve small Qwiic/STEMMA
breakouts at 25.4 × 17.8 mm each come to **5,425 mm²** — **2.2× the entire face
area of the device**, before the dev board and the battery. The DevKitC-1 alone
is roughly 63 × 26 mm, which is *longer than the finished object is wide.*

So the breadboard rig and the product are two different machines:

- **Bench rig (now).** Breakout boards, jumper wires, no enclosure. What you
  need here is **pinouts and I2C addresses, not CAD.** Downloading STEP files at
  this stage is procrastination that feels like progress.
- **The product (later).** One custom PCB with **bare ICs**, not breakouts. Then
  you need ECAD for every part and MCAD for maybe eight of them.

Which means: **do not collect breakout-board CAD at all.** Collect ECAD for the
bare parts you will actually solder down, and MCAD only for the things whose
physical size decides the enclosure.

---

## Start here — four sources cover most of the list

**1. DigiKey's per-part model pages — the best single entry point.**
Every DigiKey product page with CAD support has a companion page at
`digikey.com/en/models/<id>`, aggregating Ultra Librarian and SnapEDA models plus
generic symbols and footprints. Since you are buying there anyway, the workflow
is: find the part, click the CAD tab, done. Requires a free account for some
downloads. Example: [RV-3028-C7 models](https://www.digikey.com/en/models/10499248).

**2. [SnapMagic Search](https://www.snapeda.com/kicad/)** (formerly SnapEDA) —
millions of parts, IPC-7351B footprints, **STEP and WRL 3D included**, native
KiCad export, no login required. First stop for anything DigiKey does not have.

**3. [Ultra Librarian](https://app.ultralibrarian.com/)** — 16M+ models,
manufacturer-verified, 30+ CAD formats. Use this when SnapMagic's footprint
looks wrong and you want a second opinion before committing to a board run.

**4. KiCad's own official libraries** — already installed, free, community
reviewed. **Check here first every time.** Generic parts (SOT-23 MOSFETs,
passives, USB-C connectors, common sensors) are already there and you will waste
an account signup finding out otherwise.

Two tools worth installing once:

- **[Import-LIB-KiCad-Plugin](https://github.com/Steffen-W/Import-LIB-KiCad-Plugin)** —
  ingests downloads from SnapEDA, SamacSys, Ultra Librarian, Octopart and
  LCSC/EasyEDA automatically instead of hand-unzipping into library folders.
- **kicad-jlcpcb-tools** — searches LCSC from inside KiCad, which matters if you
  ever have JLCPCB assemble the board. Their basic-parts library is what keeps an
  assembly quote from tripling.

Also: **[SamacSys / Component Search Engine](https://componentsearchengine.com/)**
— Mouser-integrated, 3D included.

**Skip the [DigiKey KiCad library](https://github.com/Digi-Key/digikey-kicad-library).**
It gets recommended everywhere, but its own README says it "should be considered
unmaintained," and the maintainers are soliciting contract work to bring it up to
**KiCad 6** — meaning it predates 6 and is several major versions behind. Use
DigiKey's per-part model pages instead; those are current.

One more trap: **`kicad.github.io` and the `KiCad/*` GitHub mirrors are frozen at
KiCad 5.1.7 (2020)** and will tell you the ESP32-S3 parts do not exist. They do.
GitLab is the authoritative library source.

---

## Per component

**"3D needed?"** answers only one question: does this part's physical size or
shape constrain the enclosure? A 0.5 mm-tall SOT-23 does not. Model those as
nothing.

### The MCU

| Part | ECAD | MCAD | 3D needed? |
|---|---|---|---|
| **ESP32-S3-WROOM-1** (module, for the real board) | [Ultra Librarian](https://app.ultralibrarian.com/details/113e5d19-2200-11ec-9033-0a34d6323d74/Espressif-Systems/ESP32-S3-WROOM-1-N8) · [SnapMagic](https://www.snapeda.com/parts/ESP32-S3-WROOM-1-N8/Espressif%20Systems/view-part/) · KiCad has `RF_Module:ESP32-S3-WROOM-1` symbol **and** footprint built in | Included with both ECAD sources | **Yes** — it is tall, it sits at the rim, and its **antenna keepout is the single most important volume in the design**. Do not grab the **1U** by mistake: that variant is U.FL external-antenna and 18.0 × 19.2 mm, against the **-1**'s on-board PCB antenna and 18.0 × 25.5 mm. Wrong length, and no antenna to keep clear of |
| **ESP32-S3-DevKitC-1** (bench only) | [SnapMagic](https://www.snapeda.com/parts/ESP32-S3-DEVKITC-1-N8R2/Espressif%20Systems/view-part/) | [GrabCAD](https://grabcad.com/library/esp32-s3-wroom-1-devkit-1) · [Marathon OS](https://marathon-os.com/library/esp32s3wroom1-devkit-downloadable-cad-6814b2ebfcc7c6ee36fcf753) | No — it never goes in the enclosure |

### I2C peripherals — search the part number at DigiKey → SnapMagic → Ultra Librarian

| Part | Function | Bench breakout | 3D needed? |
|---|---|---|---|
| **RV-3028-C7** | RTC, 45 nA, ±1 ppm | [Melopero Qwiic RV-3028](https://www.melopero.com/shop/components/sensors/real-time-clock/meloperorv3028realtimeclockbreakoutqwiic/) — **out of stock as of writing**, and it is the only convenient breakout. If it stays out, hand-solder the bare part to a SON-8 adapter or accept the DevKitC's drift on the bench | No — 3.2 × 1.5 × 0.8 mm |
| **DRV2605L** | Haptic driver | [Adafruit 2305](https://github.com/adafruit/Adafruit_CAD_Parts) — **STEP is in `2305 DRV2605L/`** | No — 1.5 mm DSBGA |
| **LSM6DS3TR-C** | IMU | Adafruit 4503 / SparkFun | No |
| **MAX17048** | Fuel gauge | Adafruit 5580 | No |
| **LP5036** | 36-ch LED driver | none — bare IC only | No, but **verify the footprint twice**; it is a fine-pitch QFN and it is the part with no hobbyist board to fall back on |
| **ST25DV64KC** | Dynamic NFC tag | [SparkFun 21274](https://www.sparkfun.com/products/21274) · [design files](https://github.com/sparkfun/SparkFun_Qwiic_RFID_Tag_ST25DV64KC) · [hookup guide](https://learn.sparkfun.com/tutorials/qwiic-dynamic-nfcrfid-tag-hookup-guide/all) | **The IC, no. The coil, yes** — it is a flat spiral in the back shell and it needs a modeled pocket plus a ferrite layer |
| **SHT40** | Temp / humidity | Adafruit 4885 | No |
| **VEML7700** | Ambient light | Adafruit 4162 | No — but it needs a **light path** to the outside, which is an enclosure feature even though the part is tiny |

### Dedicated-pin parts

| Part | Function | Source | 3D needed? |
|---|---|---|---|
| **TSOP38238** | 38 kHz IR receiver | KiCad has **no `TSOP38238` footprint** — the one to use is **`OptoDevice:Vishay_MINIMOLD-3Pin`**. Vishay's datasheet has the mechanical drawing | **Yes** — a through-hole 3-lead package with a domed lens that must aim at an IR window. Model it |
| **IR LED** (any 3 mm / SMD) | IR emit | Generic KiCad footprint | Yes if through-hole, no if SMD |
| **AO3400A** | IR LED drive MOSFET | KiCad `Package_TO_SOT_SMD:SOT-23` | No |
| **Hall sensor** (e.g. DRV5032) | Dock / magnet detect | SnapMagic / DigiKey | No |
| **Tactile switch** (backup press path) | Parallel to `BOOT` | KiCad built-in | Only if it protrudes |

### Audio

| Part | Source | 3D needed? |
|---|---|---|
| **MAX98357A** amp | [Adafruit 3006 STEP](https://github.com/adafruit/Adafruit_CAD_Parts/blob/main/3006%20MAX98357/3006%20MAX98357.step) — confirmed present. Bare IC on SnapMagic/DigiKey | No |
| **ICS-43434** or **INMP441** mic | SnapMagic / TDK | No, but the **acoustic port** is an enclosure feature |
| **Micro speaker** (8 Ω, ~15–20 mm) | Vendor drawing; GrabCAD for generics | **Yes** — and it needs a sealed cavity behind it, which is volume you must reserve now |

### Power

| Part | Source | 3D needed? |
|---|---|---|
| **TP4056** module (bench) | [GrabCAD, Type-C version](https://grabcad.com/library/tp4056-charging-module-type-c-1) · [more variants](https://grabcad.com/library/tag/tp4056) | No |
| **TP4056** bare IC (product) | SnapMagic / LCSC via easyeda2kicad | No |
| **LiPo pouch, 500–600 mAh** | [Adafruit CAD Parts](https://github.com/adafruit/Adafruit_CAD_Parts) has `1578 500mAh battery`, `1317 150mAh`, `1570 100mAh` | **Yes — model this first.** It is the largest single object in the device and it sizes the enclosure. Add 0.5 mm of swell allowance on every face |
| **USB-C receptacle** | KiCad built-in; SnapMagic for a specific part | **Yes** — it defines the rim cutout |

### Mechanical — no ECAD, model these yourself

| Part | Where the dimensions come from |
|---|---|
| **Coin LRA** — Vybronics [VG1040003D](https://www.vybronics.com/coin-vibration-motors/lra/v-g1040003d): 10.0 × 4.0 mm, 170 Hz, 170 mA max / 145 mA typ. (**Not** VG1040001D — that one is EOL, zero stock, and this is its named replacement) | Vybronics publishes a **downloadable 3D CAD file per part** (a `.rar`, not a bare STEP) plus a dimensioned PDF. [Full LRA range](https://www.vybronics.com/products/coin-vibration-motors/lra) — the 8 mm [VG0840001D](https://www.vybronics.com/coin-vibration-motors/lra/v-g0840001d) (8.0 × 4.05 mm, 170 Hz, 90 mA max) is the smaller option and is in stock |
| **FSR** — Interlink 402 | Datasheet says 12.7 mm active area; Interlink's own product page says 14.7 mm and contradicts it. **Neither number is the one you need** — the enclosure cares about the **overall round head: 18.28 mm dia, 0.55 mm thick**, on a 2.375 in tail. Flat film, so a simple extrude is exact |
| **Frosted opal acrylic diffuser** | Model it. It is a 52 mm squircle, 3 mm thick, with a spherical dish — a two-sketch part |
| **Diffuser film** | A 0.2 mm offset surface. Do not bother with a separate body |
| **Neodymium magnets** | K&J Magnetics publishes exact dimensions per SKU; a cylinder primitive is exact |
| **Ferrite shield sheet** | Model as a 0.3 mm sheet. Vendor tolerance is irrelevant at this stage |
| **Brass weight ring** | Yours to design — it exists only to hit a mass target |

---

## What has no usable CAD, and does not need it

**Bare passives, the SOT-23 MOSFET, the hall sensor, most of the I2C ICs.**
Every one is under 1.2 mm tall. Model the PCB as a flat plate with a single
"components: 2 mm" clearance block on the populated side and you have captured
everything they do to the enclosure. Chasing individual STEP files for these is
the classic way to spend a weekend and learn nothing.

**Generic Chinese modules** (TP4056 boards, no-name speakers, cells). Community
GrabCAD models exist and are usually close but **not authoritative** — nobody
verified them. If one of these is load-bearing for fit, measure the actual part
with calipers and model it yourself. That is fifteen minutes and it is correct.

---

## The order to actually do this in

1. **Nothing yet.** Breadboard the rig. Collect pinouts and I2C addresses,
   confirm no address collisions, get every peripheral talking. No CAD.
2. **Then the three that size the box** — battery, speaker + cavity, ESP32-S3
   module with its antenna keepout. Model those three and you will know whether
   52 × 17 mm is real or whether it needs to grow again.
3. **Then ECAD for the schematic**, part by part, as you draw it. Not in advance.
4. **Then the rest of the MCAD**, once the board outline exists and you are
   drawing the shell around it.

Step 2 is the one that can still change the industrial design, so it is the one
worth doing early. Everything else is downstream of a board that does not exist.
