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
  LED_FIELDS, LED_STYLE_BY_TYPE, LOOK_PRESETS, LOOK_PRESET_GROUPS,
  describeEffect,
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

  const refresh = () => {
    applySwatch(swatch, effect());
    summary.textContent = describeEffect(effect());
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

  const renderFields = () => {
    clear(fields);
    validators.length = 0;
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

  // --- the library ----------------------------------------------------

  const applyPreset = (preset) => {
    // Assigned key by key rather than replaced, because callers hold a
    // reference to this object - the whole point of editing in place.
    Object.assign(effect(), preset.effect);
    renderFields();
    refresh();
    o.onChange?.();
    if (canPreview) show(effect());
  };

  const presetDrawer = () => {
    const body = el('div', { className: 'preset-groups' });
    for (const group of LOOK_PRESET_GROUPS) {
      const dots = el('div', { className: 'preset-dots' });
      for (const preset of LOOK_PRESETS.filter((p) => p.group === group)) {
        // The colour goes on an inner swatch rather than the button, so the
        // label stays readable against the page instead of against whatever
        // the preset happens to be.
        const chip = el('span', { className: 'preset-dot-swatch' });
        applySwatch(chip, preset.effect);  // animates exactly as the LED does
        const dot = el('button', {
          type: 'button',
          className: 'preset-dot',
          title: `${preset.label} - ${describeEffect(preset.effect)}`,
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

  renderFields();
  refresh();
  row.append(
    el('div', { className: 'palette-head' }, head),
    presetDrawer(),
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
