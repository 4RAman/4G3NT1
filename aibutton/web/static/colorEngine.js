// One way to choose a colour, used everywhere a colour is chosen.
//
// This replaces three near-identical things: the Lights tab's palette rows,
// the named-looks rows, and the test bench. They had drifted into different
// capabilities for no reason anyone chose - only the bench could show you a
// look on the actual hardware, and only the palette rows could validate. A
// colour control that can do one but not the other is the wrong seam, so
// there is now one control that does both and callers turn parts off.
//
// **The bench is not gone, it is distributed.** Its genuinely useful property
// was that it answered with the *device's* rendering rather than the config's
// intent, which is how you tell a wiring fault from a config one (README's
// WS2812 gotchas). That belonged next to every colour picker, not on its own
// page at the bottom of one tab.
//
// Everything returns the widget contract the rest of the app uses -
// `{ el, validate }` - so this drops into a form beside any other field
// (Liskov, same as widgets.js).

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
 * Module-private: this used to live in menu.js, and now that one component
 * asks the question there is nobody else to ask it.
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
// through and pushes one at a time, not a style the firmware renders on its
// own. That is why it has none of LED_STYLES' machinery - no `style`, no
// `uses`, nothing schema.js needs to know about, because the firmware never
// sees the shape (sequencer.py: "a sequence is not an effect").

/** One row per stop: the engine's own colour field, plus the two seconds a
 *  stop knows about. Module-level like DIAGNOSTIC - pure data, no `o`. */
const STOP_FIELDS = [
  { key: 'color', label: 'Colour', kind: 'color' },
  { key: 'hold_s', label: 'Hold (s)', kind: 'number', min: 0, step: 0.05,
    hint: 'How long this colour stays once it has arrived.' },
  { key: 'fade_s', label: 'Fade (s)', kind: 'number', min: 0, step: 0.05,
    hint: "How long arriving here takes. 0 is a hard cut from the stop before it." },
  // The shape of that fade (TODO 36b). Basic tier, not tinker: it is the
  // difference between a colour changing and a colour *arriving*, which is
  // the whole reason the field exists.
  { key: 'curve', label: 'Fade shape', kind: 'select',
    options: CURVES.map((c) => ({ value: c.value, label: c.label })),
    hint: 'Only applies while fading. Slow start then a rush reads as a build; '
      + 'slow finish reads as a landing.' },
  // What the *hold* does (TODO 36c). A fade is always a plain crossfade, so
  // this never applies mid-arrival - that would be two clocks on one light.
  { key: 'style', label: 'Movement', kind: 'select',
    options: LED_STYLES.map((st) => ({ value: st.type, label: st.label })),
    hint: 'How this stop moves once it has arrived. Solid is a held colour; '
      + 'anything else animates for as long as the stop lasts.' },
  { key: 'period_s', label: 'Movement rate (s)', kind: 'number', min: 0.05, step: 0.05,
    tier: 'tinker',
    hint: 'Only used when Movement is not Solid. Floored the same way any '
      + 'other flashing look is.' },
];

/** `STOP_FIELDS` with the Hold and Fade labels saying what their numbers
 *  actually mean under `drive`. The values are the same two keys either way -
 *  `hold_s`/`fade_s` keep the `_s` because renaming them would break every
 *  config written before drives existed - so this is a label change, and the
 *  label is the only place the unit is ever stated. */
function stopFieldsFor(drive) {
  if (drive === 'beats') {
    return STOP_FIELDS.map((spec) => (
      spec.key === 'hold_s' ? { ...spec, label: 'Hold (beats)', step: 1 }
        : spec.key === 'fade_s' ? { ...spec, label: 'Fade (beats)', step: 1 }
          : spec));
  }
  if (drive === 'progress') {
    return STOP_FIELDS.map((spec) => (
      spec.key === 'hold_s' ? { ...spec, label: 'Hold (share)' }
        : spec.key === 'fade_s' ? { ...spec, label: 'Fade (share)' }
          : spec));
  }
  return STOP_FIELDS;
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

  const refresh = () => {
    // Both shapes: ledPreview's colorAt and schema.js's describeEffect know
    // stop lists now - they had to, because a pool look that is a sequence
    // also shows up in modeEditor.js's compact swatch, well outside this
    // control. One implementation there beats a private twin here.
    const eff = effect();
    applySwatch(swatch, eff);
    summary.textContent = describeEffect(eff);
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

  // --- the fields -----------------------------------------------------

  const renderEffectFields = () => {
    const style = LED_STYLE_BY_TYPE[effect().style] || LED_STYLE_BY_TYPE.solid;
    for (const spec of LED_FIELDS) {
      // Hide what this style ignores: a rainbow has no hue to pick.
      if (spec.key !== 'style' && !usedBy(style, spec)) continue;
      const field = createField(spec, effect(), () => {
        refresh();
        o.onChange?.();
        // Switching style changes which fields belong here.
        if (spec.key === 'style') renderFields();
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
    // Fill in the keys a stop written before TODO 36 does not carry. The
    // parser defaults all three anyway, so this changes no behaviour - but a
    // `select` whose value is absent from its options renders *blank*, which
    // would show every existing sequence (and every preset that leaves a
    // default implicit) as having no fade shape and no movement at all.
    // Normalised here, at the one place a stop list is about to be edited,
    // rather than asking each author to spell out the defaults.
    for (const stop of seq.stops) {
      if (typeof stop.curve !== 'string') stop.curve = 'linear';
      if (typeof stop.style !== 'string') stop.style = 'solid';
      if (typeof stop.period_s !== 'number') stop.period_s = 1;
    }

    // Adding, removing or reordering a stop changes which rows and which up
    // /down buttons exist, so - like a style switch above - that gets a full
    // rebuild rather than a targeted patch. A row's own field edits (colour,
    // hold, fade) don't touch row count and skip this, same split as the
    // effect fields above.
    const commitStructure = () => {
      renderFields();
      refresh();
      o.onChange?.();
    };

    const rows = el('div', { className: 'sequence-rows' });
    seq.stops.forEach((stop, index) => {
      const rowFields = el('div', { className: 'sequence-row-fields' });
      for (const spec of stopFieldsFor(seq.drive)) {
        const field = createField(spec, stop, () => { refresh(); o.onChange?.(); });
        validators.push(field.validate);
        rowFields.append(field.el);
      }

      const up = el('button', {
        type: 'button', className: 'mini', textContent: '↑', title: 'Move earlier',
      });
      up.disabled = index === 0;
      up.addEventListener('click', () => {
        [seq.stops[index - 1], seq.stops[index]] = [seq.stops[index], seq.stops[index - 1]];
        commitStructure();
      });

      const down = el('button', {
        type: 'button', className: 'mini', textContent: '↓', title: 'Move later',
      });
      down.disabled = index === seq.stops.length - 1;
      down.addEventListener('click', () => {
        [seq.stops[index], seq.stops[index + 1]] = [seq.stops[index + 1], seq.stops[index]];
        commitStructure();
      });

      const remove = el('button', {
        type: 'button', className: 'mini danger', textContent: '×', title: 'Remove this stop',
      });
      // Never offer to remove the last one - same rule the ramp widget
      // (widgets.js) already follows: an empty sequence is not a thing you
      // can mean, and the parser would just hand back the default look.
      remove.disabled = seq.stops.length <= 1;
      remove.addEventListener('click', () => {
        seq.stops.splice(index, 1);
        commitStructure();
      });

      rows.append(el('div', { className: 'sequence-row' }, [
        el('span', { className: 'sequence-index', textContent: String(index + 1) }),
        rowFields,
        el('div', { className: 'sequence-row-actions' }, [up, down, remove]),
      ]));
    });

    const add = el('button', { type: 'button', className: 'mini', textContent: '+ Stop' });
    add.addEventListener('click', () => {
      const last = seq.stops[seq.stops.length - 1];
      seq.stops.push({
        color: last ? last.color : '#ffffff', hold_s: 0.5, fade_s: 0,
        curve: 'linear', style: 'solid', period_s: 1,
      });
      commitStructure();
    });

    // What moves the list along (TODO 36d). A full rebuild on change, because
    // the unit words on every row's Hold and Fade labels depend on it - the
    // same numbers mean seconds, weights or beats depending on what is
    // driving, and a row saying "(s)" under a beats drive would be a lie.
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
      () => { refresh(); o.onChange?.(); },
    );
    validators.push(repeatField.validate);

    const floorHint = el('span', {
      className: 'menu-hint', 'data-help': true,
      // Only the clock drive is floored on dwell, and saying so matters: under
      // the other two the app's own rate decides how fast stops go by, so a
      // number of seconds here would describe a limit that is not being
      // applied. A stop's *movement* is floored under every drive, because
      // that one is `flash_safe` and runs on every push.
      textContent: seq.drive === 'clock'
        ? 'A repeating sequence, or one longer than 3 stops, cannot move faster '
          + `than the flash safety limit: each stop's hold + fade together is floored to at `
          + `least ${sequenceFloor(o.floor).toFixed(2)}s, the same way a fast flash or `
          + 'alternate is slowed down. A one-shot of 3 stops or fewer is exempt.'
        : 'How fast stops go by is set by whatever is driving this, not by the '
          + 'numbers here - so the usual dwell limit does not apply. A stop whose '
          + 'Movement flashes is still slowed to the flash safety limit.',
    });

    // Caught here rather than left to `_parse_sequence`'s own fallback: that
    // fallback is silent recovery for a *saved* config (CLAUDE.md: a bad
    // config never crashes the service), and Save should refuse before it
    // ever gets there, the same way every other required field does.
    validators.push(() => (seq.stops.length ? null : 'A sequence needs at least one stop'));

    // Drive and Repeat go *above* the stops, not below them. They are
    // properties of the whole list, and the drive decides what the Hold and
    // Fade columns even mean - reading eighteen rows of "Hold" before finding
    // out whether they are seconds, shares or beats is the wrong way round.
    fields.append(el('div', { className: 'sequence-edit' }, [
      driveField.el, repeatField.el, rows, add, floorHint,
    ]));
  };

  const renderFields = () => {
    clear(fields);
    validators.length = 0;
    if (isSequence()) renderSequenceFields();
    else renderEffectFields();
    if (modeToggle) modeToggle.sync();
    // The drawer used to hide for a sequence, because every preset was a
    // plain effect and none of them could be dropped into one. Some are stop
    // lists now (TODO 36a), so it stays open and filters instead.
    if (presetDrawerEl) presetDrawerEl.hidden = false;
  };

  // --- the library ----------------------------------------------------

  const applyPreset = (preset) => {
    const target = effect();
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
    if (presetIsSequence(preset)) {
      for (const key of ['style', 'color', 'color2', 'period_s', 'drive']) delete target[key];
    } else {
      for (const key of ['stops', 'repeat', 'drive']) delete target[key];
    }
    Object.assign(target, presetLook(preset));
    renderFields();
    refresh();
    o.onChange?.();
    if (canPreview) show(effect());
  };

  const presetDrawer = () => {
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

    const drawer = el('details', { className: 'preset-drawer' }, [
      el('summary', { textContent: 'Start from a preset' }),
      body,
    ]);
    if (o.openPresets) drawer.open = true;
    return drawer;
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
    tryIt.addEventListener('click', () => show(effect()));
    const stop = el('button', { type: 'button', textContent: 'Stop' });
    stop.addEventListener('click', () => show({ clear: true }));
    actions.append(tryIt, stop, status);
  }

  // --- switching shape --------------------------------------------------
  // Only offered where a sequence is a legal look at all (see the
  // `allowSequence` doc above). The object is mutated in place, key by key,
  // like `applyPreset` above - callers hold a reference to it.
  const switchShape = (wantSequence) => {
    const cur = effect();
    if (Array.isArray(cur.stops) === wantSequence) return;
    // Read the colour to carry across *before* clearing the object below -
    // both branches want it, and it lives under a different key in each
    // shape (`color` on a plain effect, `stops[0].color` on a sequence).
    const carryColor = wantSequence
      ? (typeof cur.color === 'string' && cur.color) || '#ffffff'
      : cur.stops?.[0]?.color || '#ffffff';
    for (const key of Object.keys(cur)) delete cur[key];
    if (wantSequence) {
      // Starts from the one colour already chosen rather than blank: a
      // single-stop sequence *is* the plain effect it replaces, minus the
      // animation, so nothing about the current pick needs re-deciding.
      cur.stops = [{
        color: carryColor, hold_s: 0.5, fade_s: 0,
        curve: 'linear', style: 'solid', period_s: 1,
      }];
      cur.repeat = true;
    } else {
      Object.assign(cur, { style: 'solid', color: carryColor, color2: '#000000', period_s: 1 });
    }
    renderFields();
    refresh();
    o.onChange?.();
    if (canPreview) show(cur);
  };

  let modeToggle = null;
  if (o.allowSequence) {
    const oneBtn = el('button', { type: 'button', className: 'mini', textContent: 'Single colour',
      title: 'One colour or animation the device renders on its own.' });
    const seqBtn = el('button', { type: 'button', className: 'mini', textContent: 'Sequence',
      title: 'A list of colours the host walks through in order.' });
    oneBtn.addEventListener('click', () => switchShape(false));
    seqBtn.addEventListener('click', () => switchShape(true));
    modeToggle = {
      el: el('div', { className: 'look-mode-toggle' }, [oneBtn, seqBtn]),
      sync: () => {
        oneBtn.classList.toggle('active', !isSequence());
        seqBtn.classList.toggle('active', isSequence());
      },
    };
  }

  const presetDrawerEl = presetDrawer();

  renderFields();
  refresh();
  // Filtered, because this is a raw `append` rather than `el()` - and only
  // `el()` skips nullish children. `modeToggle?.el` is undefined on every row
  // that did not opt into sequences (the system palette's five), and
  // `Element.append(undefined)` inserts the *string* "undefined", which is
  // exactly what it was doing on the Lights tab.
  row.append(...[
    el('div', { className: 'palette-head' }, head),
    presetDrawerEl,
    modeToggle?.el,
    fields,
    actions,
  ].filter((node) => node != null));

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
