// One way to choose a colour, used everywhere a colour is chosen. One control
// that can validate *and* push a look at the hardware, with callers turning
// parts off - a picker that could do one but not the other is the wrong seam.
//
// **Pushing at the hardware is the load-bearing half.** It answers with the
// *device's* rendering rather than the config's intent, which is how you tell
// a wiring fault from a config one (README's WS2812 gotchas), so it belongs
// beside every colour picker rather than on a bench of its own.
//
// Returns the widget contract the rest of the app uses - `{ el, validate }` -
// so this drops into a form beside any other field (Liskov, as widgets.js).

import { clear, el } from './dom.js';
import {
  CURVES, DRIVES, LED_FIELDS, LED_STYLES, LED_STYLE_BY_TYPE, LOOK_PRESETS,
  LOOK_PRESET_GROUPS, describeEffect, presetIsSequence, presetLook,
} from './schema.js';
import { createField } from './widgets.js';
import { paint as applySwatch } from './ledPreview.js';

/**
 * Whether `style` renders `spec`. Two specs share the key `color` - a hue
 * picker and a brightness slider - so a spec may declare which *reading* it
 * is with `shows`, and the style's `uses` list names the reading it wants.
 */
function usedBy(style, spec) {
  return style.uses.includes(spec.shows || spec.key);
}

// Known colours for diagnosing the hardware, kept apart from the aesthetic
// library on purpose: these are not looks anybody wants, they are the ones
// that *talk*. README's byte-order gotcha turns on exactly this - red, green,
// cyan and magenta have unequal components and so reveal a channel swap, while
// blue, yellow and white are fixed points of an R/G swap and look perfect
// while it is broken. Offered only where a live push is possible, because
// staring at a swatch in a browser proves nothing about a wire.
const DIAGNOSTIC = [
  { label: 'Red', color: '#ff0000' },
  { label: 'Green', color: '#00ff00' },
  { label: 'Blue', color: '#0000ff' },
  { label: 'Yellow', color: '#ffff00' },
  { label: 'Cyan', color: '#00ffff' },
  { label: 'Magenta', color: '#ff00ff' },
  { label: 'White', color: '#ffffff' },
];

const FALLBACK_FLOOR = 1 / 3;  // device.SAFE_MIN_PERIOD_S, for a model with none

/**
 * What a period slider needs to know: how slow it has to stay. Only the hard
 * on/off styles are floored, so a breathe keeps the full range - the limit is
 * about strobing, not about being fast. Read off the live config so raising
 * the setting widens the slider rather than lying about what will be accepted.
 */
function ledCtx(style, floor) {
  const configured = Number(floor);
  const limit = Number.isFinite(configured) && configured > 0 ? configured : FALLBACK_FLOOR;
  return { minFlashPeriod: style?.strobes ? limit : 0.05 };
}

// --- sequences ----------------------------------------------------------
// A look with a `stops` key is a stop list (sequencer.Sequence, host-side)
// rather than a device-animated effect: several colours the *host* walks
// through and pushes one at a time. The firmware never sees the shape, which
// is why it has none of LED_STYLES' machinery (sequencer.py: "a sequence is
// not an effect").

/** What a stop *is*: a colour, and how long it stays once it has arrived.
 *  Module-level like DIAGNOSTIC - pure data, no `o`.
 *
 *  Deliberately two fields. A stop briefly also carried a style and a period,
 *  so one node of a list could be "flashing yellow" (TODO 36c, removed in
 *  36e): a list that walks colours *and* animates inside them is two clocks on
 *  one light, and no layout made it clear which one you were setting.
 *  Everything it could say is sayable as more stops - a flash is on, off, on. */
const STOP_FIELDS = [
  { key: 'color', label: 'Colour', kind: 'color' },
  { key: 'hold_s', label: 'Hold (s)', kind: 'number', min: 0, step: 0.05,
    hint: 'How long this colour stays once it has arrived.' },
];

/** What happens in the *gap* between two stops. Both keys live on the later
 *  of the two - a fade belongs to the stop being arrived at - but a field
 *  called "Fade" sitting inside a row full of that stop's own settings is the
 *  question "between which two colours?" with no answer on screen. So they are
 *  edited in the gap they actually occupy, and the gap says what it joins. */
const FADE_FIELDS = [
  { key: 'fade_s', label: 'Fade (s)', kind: 'number', min: 0, step: 0.05 },
  // The shape of that fade (TODO 36b). Basic tier, not tinker: it is the
  // difference between a colour changing and a colour *arriving*, which is
  // the whole reason the field exists.
  { key: 'curve', label: 'Shape', kind: 'select',
    options: CURVES.map((c) => ({ value: c.value, label: c.label })),
    hint: 'Slow start then a rush reads as a build; slow finish reads as a landing.' },
];

/** `label` with the unit `drive` actually measures in. The values are the
 *  same two keys either way - `hold_s`/`fade_s` keep the `_s` because renaming
 *  them would break every config written before drives existed - so this is a
 *  label change, and the label is the only place the unit is ever stated. */
const UNITS = { clock: 's', progress: 'share', beats: 'beats' };

function unitFields(specs, drive) {
  if (drive === 'clock') return specs;
  const unit = UNITS[drive] || 's';
  return specs.map((spec) => (
    spec.key === 'hold_s' || spec.key === 'fade_s'
      ? { ...spec, label: `${spec.label.replace(/ \(.*\)$/, '')} (${unit})`,
        ...(drive === 'beats' ? { step: 1 } : {}) }
      : spec));
}

/**
 * The floor `config.sequence_safe` applies to a stop's dwell (hold_s +
 * fade_s), once the sequence can sustain a strobe (it repeats, or runs past
 * three stops): half the configured flash period, the same maths
 * `flash_safe` already applies to a plain effect's `period_s` - see
 * CLAUDE.md's flash-floor invariant. Read off the live config exactly like
 * `ledCtx` does, so raising the setting widens what this hint promises
 * instead of lying about it.
 *
 * Informational only. The clamp itself stays host-side; a second one here
 * would be the "floor in three places" CLAUDE.md warns against, and this
 * floor is conditional (repeat, or >3 stops) and combined across two
 * fields - not a bound either field's `min` could honestly express alone.
 */
function sequenceFloor(floor) {
  const configured = Number(floor);
  const limit = Number.isFinite(configured) && configured > 0 ? configured : FALLBACK_FLOOR;
  return limit / 2;
}

// --- Morse (TODO 83) ------------------------------------------------------
// A look shaped `{morse, dpm, color|ramp, repeat}` - config.py's
// `_parse_morse_look` compiles it into the stop list that actually plays.
// Nothing here re-implements that compiler (see ledPreview.js's colorAt on
// why); this widget only edits the authored fields.

// 60 / dpm seconds per unit - mirrors morse.UNIT_S_PER_DPM. Dots per minute
// rather than words per minute: a WPM figure needs the PARIS-standard "a
// word is 50 units" convention before it means a duration, where dpm is
// just this division, directly. Informational only, exactly like
// sequenceFloor above: the real cap (and the warning if a save asks for
// more) is applied host-side in _parse_morse_look, and this hint would only
// ever be stale in the harmless direction (asking to lower the flash floor
// further than actually necessary).
const MORSE_UNIT_S_PER_DPM = 60;

function maxMorseDpm(floor) {
  const configured = Number(floor);
  const limit = Number.isFinite(configured) && configured > 0 ? configured : FALLBACK_FLOOR;
  return (2 * MORSE_UNIT_S_PER_DPM) / limit;
}

/**
 * A colour control bound to one effect object, which it mutates in place.
 *
 * @param {object}   o
 * @param {Function} o.get       - () => the effect being edited
 * @param {Function} o.onChange  - called after any edit
 * @param {number}   o.floor     - the configured min flash period
 * @param {object}   [o.api]     - enables live preview when it has showLook()
 * @param {string}   [o.label]   - shown in the head
 * @param {string}   [o.meaning] - a subtitle for the head
 * @param {Function} [o.rename]  - (next) => boolean; makes the label editable
 * @param {Function} [o.onRemove]- shows a Delete button
 * @param {string}   [o.previewState] - LED state a live preview reports as
 * @param {boolean}  [o.openPresets] - start with the library expanded
 * @param {object}   [o.namedLook] - lets this control answer "a named look"
 *   instead of a style: `{ get, set, names, look }`. Offered where a *state*
 *   is being coloured (the Lights tab), not where a look itself is being
 *   edited - a pool entry that could name another pool entry would be the
 *   one-level-only guarantee `resolve_action` gets for free, thrown away.
 * @param {boolean}  [o.allowSequence] - offer switching this look to a stop
 *   list (sequencer.Sequence). Off by default: only the named-look pool may
 *   hold a sequence - the system palette must stay effect-only, because a
 *   palette entry ships to the device and renders unattended while a
 *   sequence is a schedule only the host can walk (config.py's
 *   `_parse_looks`). A caller editing a pool entry opts in; a caller editing
 *   `led_palette` must not.
 * @returns {{el: Element, validate: Function, refresh: Function}}
 */
export function createLookEditor(o) {
  const row = el('div', { className: 'palette-row' });
  const swatch = el('span', { className: 'palette-swatch' });
  const summary = el('span', { className: 'palette-summary' });
  const status = el('span', { className: 'menu-status' });
  const fields = el('div', { className: 'settings-grid' });
  const validators = [];

  const effect = () => o.get();
  const isSequence = () => Array.isArray(effect().stops);
  const isMorse = () => typeof effect().morse === 'string';
  // The three shapes a look-pool entry may take (config.py's `_parse_look`
  // dispatches on the same key presence, in the same order): a Morse message,
  // a stop list, or a plain effect - whichever no earlier check claimed.
  const shapeOf = (obj) => (
    typeof obj.morse === 'string' ? 'morse' : Array.isArray(obj.stops) ? 'sequence' : 'single'
  );

  const refresh = () => {
    // What the *button* will do, which is not always what this control is
    // editing: a state wearing a named look shows that look, and the palette
    // entry underneath it is the offline fallback. Showing the fallback here
    // was the whole "named looks don't work" report - the runtime had it
    // right and this line was describing the other layer.
    //
    // All three shapes: ledPreview's colorAt and schema.js's describeEffect
    // know stop lists and Morse looks - they had to, because a pool look in
    // either shape also shows up in modeEditor.js's compact swatch, well
    // outside this control.
    const name = namedName();
    const look = shownLook();
    applySwatch(swatch, look);
    summary.textContent = name
      ? (o.namedLook.look(name)
        ? `${name} - ${describeEffect(look)}`
        : `${name} (missing) - falling back to ${describeEffect(look)}`)
      : describeEffect(look);
  };

  // --- live preview ---------------------------------------------------
  // Optional by construction: the offline editor (build_editor.py swaps the
  // API for a file one) has no device to talk to, and a control that only
  // works when a service is running would be the wrong thing to build the
  // whole app's colour picking on.
  const canPreview = Boolean(o.api && typeof o.api.showLook === 'function');

  const show = async (body) => {
    if (!canPreview) return;
    status.textContent = 'sending…';
    try {
      // The state byte rides along because it is what the status line reports
      // and what a device too old for effects falls back to rendering. The
      // *caller* names it rather than the user picking it from a dropdown, as
      // the old bench made you do: whoever mounted this control already knows
      // which state it is editing, so asking was always a question with a
      // knowable answer.
      const res = await o.api.showLook(
        body.clear || !o.previewState ? body : { ...body, state: o.previewState },
      );
      if (res.warnings && res.warnings.length) {
        // What went out is not what was typed - say so, or this reports the
        // LED's answer to a question it was not asked.
        status.textContent = `sent (adjusted): ${res.warnings.join('; ')}`;
      } else if (!res.connected) {
        status.textContent = 'sent, but the button is not connected';
      } else {
        status.textContent = body.clear
          ? 'back to the configured colours'
          : `showing ${describeEffect(res.effect)}`;
      }
    } catch (err) {
      status.textContent = `failed: ${err.message}`;
    }
  };

  // --- naming a look instead of choosing a colour -----------------------
  // A named look is not a *style* - it is a whole other object, possibly a
  // sequence - but it is the same question the Style dropdown already asks
  // ("what does this state look like?"), and answering one question in two
  // controls is what made the old separate picker read as belonging to the
  // row below it. So it becomes the last option in that dropdown, and the
  // pool picker appears only once it is chosen.
  const NAMED_STYLE = '__look__';
  // Kept locally as well as in the config because the empty pool has to be
  // reachable: picking "a named look" with nothing to name has to leave the
  // control in that mode saying so, rather than snapping back to a style.
  let wantNamed = Boolean(o.namedLook && o.namedLook.get());

  /** The name this state currently wears, or '' - only ever non-empty when
   *  the caller offered the option at all. */
  const namedName = () => (o.namedLook && wantNamed ? o.namedLook.get() || '' : '');

  /** What the light will actually show: the named look when one resolves,
   *  the edited effect otherwise (which is also what a dangling name falls
   *  back to, exactly as `config.look_for` does). */
  const shownLook = () => {
    const name = namedName();
    return (name && o.namedLook.look(name)) || effect();
  };

  // --- the fields -----------------------------------------------------

  /** The Style dropdown, with "a named look" appended where the caller allows
   *  one. Bound to a scratch object rather than to the effect, because
   *  `__look__` is not a style and must never be written into one. */
  const renderStyleField = () => {
    const base = LED_FIELDS.find((spec) => spec.key === 'style');
    const style = LED_STYLE_BY_TYPE[effect().style] || LED_STYLE_BY_TYPE.solid;
    if (!o.namedLook) {
      const field = createField(base, effect(), () => {
        refresh();
        o.onChange?.();
        renderFields();  // switching style changes which fields belong here
      }, ledCtx(style, o.floor));
      validators.push(field.validate);
      fields.append(field.el);
      return;
    }

    const scratch = { style: wantNamed ? NAMED_STYLE : effect().style };
    const spec = {
      ...base,
      options: [...base.options, { value: NAMED_STYLE, label: 'A named look…' }],
      hint: 'The styles are single colours the button renders on its own. A '
        + 'named look is one you have built and named below - it can be a whole '
        + 'sequence, and it is what this state wears while the service is running.',
    };
    const field = createField(spec, scratch, () => {
      if (scratch.style === NAMED_STYLE) {
        wantNamed = true;
        // Land on something rather than on an empty picker when the pool has
        // anything in it: choosing "a named look" and getting no look is a
        // dead end, and the picker right below makes changing it one click.
        const first = o.namedLook.names()[0];
        if (first && !o.namedLook.get()) o.namedLook.set(first);
      } else {
        wantNamed = false;
        o.namedLook.set('');
        effect().style = scratch.style;
      }
      refresh();
      o.onChange?.();
      renderFields();
    }, ledCtx(style, o.floor));
    validators.push(field.validate);
    fields.append(field.el);
  };

  /** The pool picker plus the fallback drawer, shown only while the Style
   *  dropdown says "a named look". */
  const renderNamedLookFields = () => {
    const names = o.namedLook.names();
    const current = o.namedLook.get() || '';

    const pick = el('select', {
      className: 'inp',
      onchange: () => {
        o.namedLook.set(pick.value);
        refresh();
        o.onChange?.();
        renderFields();
      },
    });
    if (!names.length) {
      pick.append(el('option', { value: '', textContent: '- no named looks yet -' }));
    } else if (!current) {
      pick.append(el('option', { value: '', textContent: '- pick one -' }));
    }
    // A look deleted from the pool stays selected and marked, for the reason a
    // dangling action name does: silently falling back would change what the
    // button does without saying so.
    if (current && !names.includes(current)) {
      pick.append(el('option', { value: current, textContent: `${current} (missing)` }));
    }
    for (const name of names) pick.append(el('option', { value: name, textContent: name }));
    pick.value = current;

    fields.append(el('label', { className: 'fld' }, [
      el('span', { className: 'fld-label', textContent: 'Which look' }),
      pick,
      el('span', {
        className: 'fld-hint', 'data-help': true,
        textContent: names.length
          ? 'Edit the look itself under Named looks below - every state and mode '
            + 'pointing at it changes together, which is what naming one is for.'
          : 'Add one under Named looks below, then come back and pick it here.',
      }),
    ]));

    // The palette entry does not go away and that is the design (TODO 36a):
    // it ships to the device and is what a host-less button renders, where a
    // named look is a schedule only the service can walk. Folded away rather
    // than deleted, because it is the second question about this state and
    // leaving it open beside the picker is what made this tab crowded.
    const fallback = el('div', { className: 'settings-grid' });
    const style = LED_STYLE_BY_TYPE[effect().style] || LED_STYLE_BY_TYPE.solid;
    for (const spec of LED_FIELDS) {
      if (!usedBy(style, spec)) continue;
      const field = createField(spec, effect(), () => {
        refresh();
        o.onChange?.();
      }, ledCtx(style, o.floor));
      validators.push(field.validate);
      fallback.append(field.el);
    }
    fields.append(el('details', { className: 'fallback-drawer' }, [
      el('summary', { textContent: 'What it shows with nothing connected' }),
      el('p', {
        className: 'menu-hint', 'data-help': true,
        textContent: 'The button keeps a copy of these colours and renders them '
          + 'on its own when no service is attached. A named look cannot go there, '
          + 'so this stays as the plain-colour version of the same idea.',
      }),
      fallback,
    ]));
  };

  const renderEffectFields = () => {
    renderStyleField();
    if (namedName() || wantNamed) {
      renderNamedLookFields();
      return;
    }
    const style = LED_STYLE_BY_TYPE[effect().style] || LED_STYLE_BY_TYPE.solid;
    for (const spec of LED_FIELDS) {
      // Hide what this style ignores: a rainbow has no hue to pick.
      if (spec.key === 'style' || !usedBy(style, spec)) continue;
      const field = createField(spec, effect(), () => {
        refresh();
        o.onChange?.();
      }, ledCtx(style, o.floor));
      validators.push(field.validate);
      fields.append(field.el);
    }
  };

  const renderSequenceFields = () => {
    const seq = effect();
    if (!Array.isArray(seq.stops)) seq.stops = [];
    if (typeof seq.repeat !== 'boolean') seq.repeat = true;
    if (typeof seq.drive !== 'string') seq.drive = 'clock';
    // Fill in the key a stop written before TODO 36b does not carry. The
    // parser defaults it anyway, so this changes no behaviour - but a `select`
    // whose value is absent from its options renders *blank*, which would show
    // every existing sequence as having no fade shape at all. Normalised here,
    // at the one place a stop list is about to be edited, rather than asking
    // each author to spell out the default.
    for (const stop of seq.stops) {
      if (typeof stop.curve !== 'string') stop.curve = 'linear';
    }

    // Adding, removing or reordering a stop changes which rows and which gaps
    // exist, so that gets a full rebuild rather than a targeted patch. A row's
    // own field edits don't touch row count and skip this - except `color`,
    // which the gap below it paints a swatch of, so the colour field asks for
    // a repaint of the gaps rather than of everything.
    const commitStructure = () => {
      renderFields();
      refresh();
      o.onChange?.();
    };

    const rowBtn = (text, title, className, disabled, onclick) => el('button', {
      type: 'button', className: `mini ${className}`, textContent: text, title, disabled, onclick,
    });
    const swap = (a, b) => {
      [seq.stops[a], seq.stops[b]] = [seq.stops[b], seq.stops[a]];
      commitStructure();
    };

    // Every gap's "from" swatch is some other stop's colour, so one repaint
    // function serves all of them and a colour edit calls it instead of
    // rebuilding the list.
    const gapPainters = [];
    const repaintGaps = () => { for (const paint of gapPainters) paint(); };

    // A proportional read of the whole list in one strip, before you scroll
    // through the rows that produced it. Flex-grow/-shrink set to the raw
    // duration is not a shortcut standing in for the maths - it *is* the
    // maths: the browser distributes space by that exact ratio, so a 2s hold
    // next to a 1s hold comes out twice the width with no rounding of my own,
    // and a zero-duration fade collapses to nothing rather than a sliver.
    // Works the same under any drive - it reads proportions of the numbers
    // typed in, not wall-clock time, so "share" and "beats" scale exactly
    // like seconds do.
    const timelineEl = el('div', { className: 'seq-timeline' });
    const paintTimeline = () => {
      clear(timelineEl);
      const unit = UNITS[seq.drive] || 's';
      seq.stops.forEach((stop, index) => {
        const prev = index > 0
          ? seq.stops[index - 1].color
          : (seq.repeat ? seq.stops[seq.stops.length - 1].color : '#000000');
        const fade = Math.max(0, Number(stop.fade_s) || 0);
        const hold = Math.max(0, Number(stop.hold_s) || 0);
        const fadeSeg = el('span', {
          className: 'seq-timeline-seg',
          title: `fade ${fade}${unit} → ${stop.color}`,
        });
        fadeSeg.style.flex = `${fade} ${fade} 0`;
        fadeSeg.style.background = `linear-gradient(to right, ${prev}, ${stop.color})`;
        const holdSeg = el('span', {
          className: 'seq-timeline-seg',
          title: `${stop.color} · hold ${hold}${unit}`,
        });
        holdSeg.style.flex = `${hold} ${hold} 0`;
        holdSeg.style.background = stop.color;
        timelineEl.append(fadeSeg, holdSeg);
      });
    };
    paintTimeline();

    /**
     * The gap above stop `index`: what its fade crosses, and the two fields
     * that shape it. Named from both ends, because "Fade 0.3s" sitting in a
     * row of that stop's own settings never said which two colours were
     * involved - the complaint this layout exists to answer.
     *
     * The *first* gap is the one worth spelling out: a one-shot arrives out of
     * black and a repeat arrives out of its own last stop, and that difference
     * is invisible anywhere else in the editor.
     */
    const gap = (index) => {
      const stop = seq.stops[index];
      const fromSwatch = el('span', { className: 'gap-swatch' });
      const toSwatch = el('span', { className: 'gap-swatch' });
      const label = el('span', { className: 'gap-names' });

      const paint = () => {
        const prev = index > 0
          ? seq.stops[index - 1].color
          : (seq.repeat ? seq.stops[seq.stops.length - 1].color : '#000000');
        applySwatch(fromSwatch, { style: 'solid', color: prev });
        applySwatch(toSwatch, { style: 'solid', color: stop.color });
        const from = index > 0
          ? `stop ${index}`
          : (seq.repeat ? 'the last stop, looping round' : 'off');
        label.textContent = `${from} → stop ${index + 1}`;
      };
      gapPainters.push(paint);
      paint();

      const gapFields = el('div', { className: 'gap-fields' });
      for (const spec of unitFields(FADE_FIELDS, seq.drive)) {
        const field = createField(spec, stop, () => { paintTimeline(); refresh(); o.onChange?.(); });
        validators.push(field.validate);
        gapFields.append(field.el);
      }
      return el('div', { className: 'sequence-gap' }, [
        el('span', { className: 'gap-label' }, [fromSwatch, label, toSwatch]),
        gapFields,
      ]);
    };

    const rows = el('div', { className: 'sequence-rows' });
    seq.stops.forEach((stop, index) => {
      const rowFields = el('div', { className: 'sequence-row-fields' });
      for (const spec of unitFields(STOP_FIELDS, seq.drive)) {
        const field = createField(spec, stop, () => {
          if (spec.key === 'color') repaintGaps();
          paintTimeline();
          refresh();
          o.onChange?.();
        });
        validators.push(field.validate);
        rowFields.append(field.el);
      }

      // The gap first, then the stop it leads into: a list you read downwards
      // is arrive, hold, arrive, hold.
      rows.append(gap(index));
      rows.append(el('div', { className: 'sequence-row' }, [
        el('span', { className: 'sequence-index', textContent: String(index + 1) }),
        rowFields,
        el('div', { className: 'sequence-row-actions' }, [
          rowBtn('↑', 'Move earlier', '', index === 0, () => swap(index - 1, index)),
          rowBtn('↓', 'Move later', '', index === seq.stops.length - 1,
            () => swap(index, index + 1)),
          // Never offer to remove the last one - same rule the ramp widget
          // (widgets.js) already follows: an empty sequence is not a thing you
          // can mean, and the parser would just hand back the default look.
          rowBtn('×', 'Remove this stop', 'danger', seq.stops.length <= 1, () => {
            seq.stops.splice(index, 1);
            commitStructure();
          }),
        ]),
      ]));
    });

    const add = el('button', {
      type: 'button', className: 'mini', textContent: '+ Stop',
      onclick: () => {
        const last = seq.stops[seq.stops.length - 1];
        seq.stops.push({
          color: last ? last.color : '#ffffff', hold_s: 0.5, fade_s: 0, curve: 'linear',
        });
        commitStructure();
      },
    });

    // What moves the list along (TODO 36d). A full rebuild on change, because
    // the unit words on every Hold and Fade label depend on it - the same
    // numbers mean seconds, weights or beats depending on what is driving, and
    // a label saying "(s)" under a beats drive would be a lie.
    const driveField = createField(
      {
        key: 'drive', label: 'Driven by', kind: 'select',
        options: DRIVES.map((d) => ({ value: d.value, label: d.label })),
        hint: DRIVES.map((d) => `${d.label}: ${d.hint}`).join(' '),
      },
      seq,
      () => { commitStructure(); },
    );
    validators.push(driveField.validate);

    const repeatField = createField(
      {
        key: 'repeat', label: 'Repeat', kind: 'checkbox',
        hint: seq.drive === 'clock'
          ? 'On loops until the light is told to show something else. Off '
            + 'plays the list once, then the light falls back to its configured colour.'
          : 'On wraps the list, so a short pattern repeats across a long run. '
            + 'Off spreads it once across the whole thing and holds the last stop '
            + 'at the end.',
      },
      seq,
      // Repeat decides what the *first* gap fades out of - off for a one-shot,
      // the last stop for a loop - so its label and swatch have to follow.
      () => { repaintGaps(); paintTimeline(); refresh(); o.onChange?.(); },
    );
    validators.push(repeatField.validate);

    const floorHint = el('span', {
      className: 'menu-hint', 'data-help': true,
      // Only the clock drive is floored, and saying so matters: under the other
      // two the app's own rate decides how fast stops go by, so a number of
      // seconds here would describe a limit that is not being applied.
      textContent: seq.drive === 'clock'
        ? 'A repeating sequence, or one longer than 3 stops, cannot move faster '
          + 'than the flash safety limit: each stop\'s hold + fade together is floored '
          + `to at least ${sequenceFloor(o.floor).toFixed(2)}s, the same way a fast flash `
          + 'or alternate is slowed down. A one-shot of 3 stops or fewer is exempt.'
        : 'How fast stops go by is set by whatever is driving this, not by the '
          + 'numbers here - so the usual dwell limit does not apply.',
    });

    // Caught here rather than left to `_parse_sequence`'s own fallback: that
    // fallback is silent recovery for a *saved* config (CLAUDE.md: a bad
    // config never crashes the service), and Save should refuse before it
    // ever gets there, the same way every other required field does.
    validators.push(() => (seq.stops.length ? null : 'A sequence needs at least one stop'));

    // Drive and Repeat go *above* the stops, not below them. They are
    // properties of the whole list, and the drive decides what the Hold and
    // Fade numbers even mean - reading eighteen rows before finding out
    // whether they are seconds, shares or beats is the wrong way round. The
    // timeline goes with them, above the rows it summarises.
    fields.append(el('div', { className: 'sequence-edit' }, [
      driveField.el, repeatField.el, timelineEl, rows, add, floorHint,
    ]));
  };

  const renderMorseFields = () => {
    const msg = effect();
    if (typeof msg.dpm !== 'number') msg.dpm = 400;
    if (typeof msg.repeat !== 'boolean') msg.repeat = true;

    // Set once, read by every swatch this look reaches (refresh() above,
    // and modeEditor.js's compact one) - none of them animate the real
    // rhythm, on purpose (see ledPreview.js's colorAt). Said here, next to
    // the fields, because a solid dot that never flashes reads as broken if
    // nothing tells you it was never meant to.
    fields.append(el('p', {
      className: 'menu-hint', 'data-help': true,
      textContent: 'The swatch above shows one representative colour, not '
        + 'the rhythm - there is no second Morse player in the browser to '
        + 'keep in step with the real one. "Show on the button" is what '
        + 'actually plays the message, on whatever is connected.',
    }));

    const messageField = createField(
      { key: 'morse', label: 'Message', kind: 'text', required: true,
        placeholder: 'SOS',
        hint: 'Letters and digits only - anything else (punctuation, spaces '
          + 'aside) is dropped when this plays, with no gap left in its '
          + 'place. A space is a pause between words.' },
      msg,
      () => { refresh(); o.onChange?.(); },
    );
    validators.push(messageField.validate);
    fields.append(messageField.el);

    const dpmField = createField(
      { key: 'dpm', label: 'Speed (dots per minute)', kind: 'number',
        min: 1, max: 3000, step: 10,
        hint: 'How many dot-lengths fit in a minute - concrete rather than '
          + '"words per minute", which needs a wire-code convention before '
          + 'it means a duration at all. Capped against the flash safety '
          + `limit at roughly ${maxMorseDpm(o.floor).toFixed(0)}/min - `
          + 'asking for more is honoured up to that cap and said so on '
          + 'Save. Lower the flash floor on the Device tab to send faster.' },
      msg,
      () => { refresh(); o.onChange?.(); },
    );
    validators.push(dpmField.validate);
    fields.append(dpmField.el);

    const repeatField = createField(
      { key: 'repeat', label: 'Repeat', kind: 'checkbox',
        hint: 'On sends the message as a beacon, over and over, with a '
          + 'longer pause between each so the loop reads as a loop. Off '
          + 'sends it once, then the light falls back to its configured '
          + 'colour.' },
      msg,
      () => { refresh(); o.onChange?.(); },
    );
    validators.push(repeatField.validate);
    fields.append(repeatField.el);

    // Solid colour, or a ramp sampled across the whole message (TODO 83's
    // colour-changes-during-the-message follow-up): each dot and dash is
    // painted by how far into the message it falls, and the gaps stay dark
    // either way. Two sub-shapes of one field, the same relationship
    // `switchShape` below has with the whole look, just one level shallower -
    // so it gets its own toggle rather than reusing the outer tabs, which
    // answer a different question ("what kind of look is this" vs "how is
    // this look's colour chosen").
    const wantsRamp = Array.isArray(msg.ramp);
    const switchColorMode = (toRamp) => {
      if (toRamp === wantsRamp) return;
      if (toRamp) {
        const carried = typeof msg.color === 'string' ? msg.color : '#ff0000';
        delete msg.color;
        msg.ramp = [carried, '#0000ff'];
      } else {
        const first = msg.ramp?.[0];
        const carried = (typeof first === 'string' ? first : first?.color) || '#ff0000';
        delete msg.ramp;
        msg.color = carried;
      }
      renderFields();
      refresh();
      o.onChange?.();
    };
    const colorModeTabs = el('div', { className: 'look-mode-toggle' }, [
      el('button', {
        type: 'button', className: `mini${wantsRamp ? '' : ' active'}`,
        textContent: 'Solid colour', onclick: () => switchColorMode(false),
      }),
      el('button', {
        type: 'button', className: `mini${wantsRamp ? ' active' : ''}`,
        textContent: 'Colour ramp', onclick: () => switchColorMode(true),
      }),
    ]);
    fields.append(colorModeTabs);

    if (wantsRamp) {
      const rampField = createField(
        { key: 'ramp', label: 'Colour across the message', kind: 'ramp',
          hint: 'Left = the start of the message, right = the end. Each dot '
            + 'and dash is coloured by how far into the message it falls; '
            + 'the gaps between them stay dark.' },
        msg,
        () => { refresh(); o.onChange?.(); },
      );
      validators.push(rampField.validate);
      fields.append(rampField.el);
    } else {
      const colorField = createField(
        { key: 'color', label: 'Colour', kind: 'color' },
        msg,
        () => { refresh(); o.onChange?.(); },
      );
      validators.push(colorField.validate);
      fields.append(colorField.el);
    }

    // Caught here for the same reason the sequence editor catches an empty
    // stop list before Save: `_parse_morse_look`'s own fallback is silent
    // recovery for a *saved* config, and this should refuse before it gets
    // there.
    validators.push(() => (
      typeof msg.morse === 'string' && msg.morse.trim()
        ? null : 'A message needs at least one character'
    ));
  };

  const renderFields = () => {
    clear(fields);
    validators.length = 0;
    if (activeTab === 'preset') fields.append(presetBody());
    else if (isMorse()) renderMorseFields();
    else if (isSequence()) renderSequenceFields();
    else renderEffectFields();
    syncTabs();
  };

  // --- the library ----------------------------------------------------

  const applyPreset = (preset) => {
    const target = effect();
    // Choosing a colour out of the library is an answer to "what does this
    // state look like", so it replaces a named look rather than being written
    // underneath one and never seen.
    if (o.namedLook && wantNamed) {
      wantNamed = false;
      o.namedLook.set('');
    }
    // Assigned key by key rather than replaced, because callers hold a
    // reference to this object - the whole point of editing in place.
    //
    // A sequence preset and an effect preset are different *shapes*, so the
    // keys of whichever one is being replaced have to go first - leaving
    // `stops` behind after picking a plain effect would make the result read
    // as a sequence that happens to carry a style, and `isSequence()` keys
    // off exactly that.
    // Every key the incoming shape might *not* carry has to go first, not just
    // the other shape's keys. A clock-driven sequence omits `drive` entirely
    // (it is the default), so assigning one over a beats-driven preset would
    // leave the old `drive` behind and silently mis-drive the new look - which
    // is exactly what happened before this line listed it.
    //
    // A preset is never a Morse message, so those keys go first unconditionally
    // - the third shape neither branch below was written to expect.
    for (const key of ['morse', 'dpm', 'ramp']) delete target[key];
    if (presetIsSequence(preset)) {
      for (const key of ['style', 'color', 'color2', 'period_s', 'drive']) delete target[key];
    } else {
      for (const key of ['stops', 'repeat', 'drive']) delete target[key];
    }
    Object.assign(target, presetLook(preset));
    // Land on whichever tab shows what you just picked, rather than leaving
    // the picker up over a result you can't see.
    activeTab = presetIsSequence(preset) ? 'sequence' : 'single';
    renderFields();
    refresh();
    o.onChange?.();
    if (canPreview) show(effect());
  };

  const presetBody = () => {
    const body = el('div', { className: 'preset-groups' });
    for (const group of LOOK_PRESET_GROUPS) {
      const dots = el('div', { className: 'preset-dots' });
      // A sequence preset is only offered where a sequence is allowed - the
      // system palette rows opt out, because a palette entry ships to the
      // device and a stop list is a schedule only the host can walk. Filtered
      // here rather than disabled, so the drawer never shows you a look the
      // Save would drop.
      const offered = LOOK_PRESETS.filter(
        (pr) => pr.group === group && (o.allowSequence || !presetIsSequence(pr)),
      );
      if (!offered.length) continue;
      for (const preset of offered) {
        const look = preset.sequence || preset.effect;
        // The colour goes on an inner swatch rather than the button, so the
        // label stays readable against the page instead of against whatever
        // the preset happens to be.
        const chip = el('span', { className: 'preset-dot-swatch' });
        applySwatch(chip, look);  // animates exactly as the LED does
        const dot = el('button', {
          type: 'button',
          className: 'preset-dot',
          title: `${preset.label} - ${describeEffect(look)}`,
        }, [chip, el('span', { className: 'preset-dot-label', textContent: preset.label })]);
        dot.addEventListener('click', () => applyPreset(preset));
        dots.append(dot);
      }
      body.append(
        el('span', { className: 'preset-group-name', textContent: group }),
        dots,
      );
    }

    if (canPreview) {
      const dots = el('div', { className: 'preset-dots' });
      for (const known of DIAGNOSTIC) {
        const chip = el('span', { className: 'preset-dot-swatch' });
        chip.style.background = known.color;
        const dot = el('button', {
          type: 'button', className: 'preset-dot',
          title: `${known.label} - solid ${known.color}, pushed straight at the button`,
        }, [chip, el('span', { className: 'preset-dot-label', textContent: known.label })]);
        dot.addEventListener('click', () => {
          applyPreset({ effect: { style: 'solid', color: known.color } });
        });
        dots.append(dot);
      }
      body.append(
        el('span', { className: 'preset-group-name', textContent: 'Diagnostic' }),
        dots,
        el('span', {
          className: 'menu-hint', 'data-help': true,
          textContent: 'Known colours for checking the wiring. Red, green, cyan '
            + 'and magenta reveal a channel swap; blue, yellow and white look '
            + 'right even when one is broken.',
        }),
      );
    }

    return body;
  };

  // --- the head -------------------------------------------------------

  const head = [swatch];
  if (o.rename) {
    const input = el('input', { className: 'inp palette-name', value: o.label || '' });
    input.addEventListener('change', () => {
      if (!o.rename(input.value.trim())) input.value = o.label || '';
    });
    head.push(input);
  } else if (o.label) {
    head.push(el('span', { className: 'palette-name', textContent: o.label }));
  }
  if (o.meaning) head.push(el('span', { className: 'palette-meaning', textContent: o.meaning }));
  head.push(summary);
  if (o.onRemove) {
    const del = el('button', { type: 'button', className: 'danger', textContent: 'Delete' });
    del.addEventListener('click', o.onRemove);
    head.push(del);
  }

  const actions = el('div', { className: 'test-actions' });
  if (canPreview) {
    const tryIt = el('button', { type: 'button', className: 'primary', textContent: 'Show on the button' });
    // The look that will actually run, not the fallback underneath it - see
    // `refresh`. A preview that showed the other layer is what made a working
    // named look read as a broken one.
    tryIt.addEventListener('click', () => show(shownLook()));
    const stop = el('button', { type: 'button', textContent: 'Stop' });
    stop.addEventListener('click', () => show({ clear: true }));
    actions.append(tryIt, stop, status);
  }

  // --- switching shape --------------------------------------------------
  // Sequence and Morse are only offered where a schedule is a legal look at
  // all (see the `allowSequence` doc above) - both are walked by the host
  // rather than rendered by the device, which a palette entry cannot be.
  // The object is mutated in place, key by key, like `applyPreset` above -
  // callers hold a reference to it.
  //
  // A flip used to `delete` every key with nothing kept, so one accidental
  // click on "Single colour" discarded a stop list with no way back (item
  // 76). Each shape now parks the exact fields it is leaving, in this
  // widget's own closure - never written to the model, so it costs the saved
  // config nothing - and a flip back restores them rather than rebuilding
  // from the one carried colour. Only the *first* flip into a shape (nothing
  // parked yet) falls back to that reconstruction.
  let parkedEffect = null;
  let parkedSequence = null;
  let parkedMorse = null;

  /** The colour to carry into whichever shape comes next - read before the
   *  object is cleared, since it lives under a different key in each shape
   *  (`color` on a plain effect, `stops[0].color` on a sequence, `color` or
   *  the first `ramp` stop on a Morse look). */
  const carryColorFrom = (obj, shape) => {
    if (shape === 'sequence') return obj.stops?.[0]?.color;
    if (shape === 'morse') {
      if (typeof obj.color === 'string') return obj.color;
      const first = obj.ramp?.[0];
      return typeof first === 'string' ? first : first?.color;
    }
    return typeof obj.color === 'string' ? obj.color : undefined;
  };

  const switchShape = (wantShape) => {
    const cur = effect();
    const curShape = shapeOf(cur);
    if (curShape === wantShape) return;
    const carryColor = carryColorFrom(cur, curShape) || '#ffffff';

    if (curShape === 'sequence') {
      parkedSequence = { ...cur, stops: cur.stops.map((s) => ({ ...s })) };
    } else if (curShape === 'morse') {
      parkedMorse = { ...cur };
    } else {
      parkedEffect = { ...cur };
    }
    for (const key of Object.keys(cur)) delete cur[key];

    if (wantShape === 'sequence') {
      if (parkedSequence) {
        Object.assign(cur, parkedSequence);
      } else {
        // Starts from the one colour already chosen rather than blank: a
        // single-stop sequence *is* the plain effect it replaces, minus the
        // animation, so nothing about the current pick needs re-deciding.
        cur.stops = [{
          color: carryColor, hold_s: 0.5, fade_s: 0,
          curve: 'linear', style: 'solid', period_s: 1,
        }];
        cur.repeat = true;
      }
    } else if (wantShape === 'morse') {
      if (parkedMorse) {
        Object.assign(cur, parkedMorse);
      } else {
        Object.assign(cur, { morse: 'SOS', dpm: 400, color: carryColor, repeat: true });
      }
    } else if (parkedEffect) {
      Object.assign(cur, parkedEffect);
    } else {
      Object.assign(cur, { style: 'solid', color: carryColor, color2: '#000000', period_s: 1 });
    }
    renderFields();
    refresh();
    o.onChange?.();
    if (canPreview) show(cur);
  };

  // --- the tab bar ------------------------------------------------------
  // Single Color / Sequence / Morse / Preset, replacing what used to be a
  // two-button shape toggle plus a separate "Start from a preset" drawer -
  // one control answering "how is this look specified", not two stacked on
  // top of each other. Sequence and Morse are offered only where
  // `allowSequence` allows a schedule at all (see the doc above); Preset is
  // always offered, as a picker rather than a persisted shape - applying one
  // lands on whichever of the other tabs shows the result (see `applyPreset`).
  let activeTab = o.openPresets ? 'preset' : shapeOf(effect());

  const singleTab = el('button', {
    type: 'button', className: 'mini', textContent: 'Single Color',
    title: 'One colour or animation the device renders on its own.',
    onclick: () => { switchShape('single'); activeTab = 'single'; renderFields(); },
  });
  const seqTab = o.allowSequence ? el('button', {
    type: 'button', className: 'mini', textContent: 'Sequence',
    title: 'A list of colours the host walks through in order.',
    onclick: () => { switchShape('sequence'); activeTab = 'sequence'; renderFields(); },
  }) : null;
  const morseTab = o.allowSequence ? el('button', {
    type: 'button', className: 'mini', textContent: 'Morse',
    title: 'Spell out a message in Morse code, played as a stop list.',
    onclick: () => { switchShape('morse'); activeTab = 'morse'; renderFields(); },
  }) : null;
  const presetTab = el('button', {
    type: 'button', className: 'mini', textContent: 'Preset',
    title: 'Start from a built-in look.',
    onclick: () => { activeTab = 'preset'; renderFields(); },
  });
  const tabsEl = el('div', { className: 'look-mode-toggle' },
    [singleTab, seqTab, morseTab, presetTab].filter(Boolean));

  const syncTabs = () => {
    singleTab.classList.toggle('active', activeTab === 'single');
    seqTab?.classList.toggle('active', activeTab === 'sequence');
    morseTab?.classList.toggle('active', activeTab === 'morse');
    presetTab.classList.toggle('active', activeTab === 'preset');
  };

  renderFields();
  refresh();
  row.append(
    el('div', { className: 'palette-head' }, head),
    tabsEl,
    fields,
    actions,
  );

  return {
    el: row,
    refresh,
    validate() {
      for (const validate of validators) {
        const error = validate();
        if (error) return error;
      }
      return null;
    },
  };
}
