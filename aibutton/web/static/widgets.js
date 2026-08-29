// Field factory: turns one field spec (from schema.js) into a labeled form
// control bound to a target object. Each widget owns its own parsing and
// validation, and every widget returns the same shape -
//   { el: HTMLElement, validate: () => string | null }
// - so the mode editor and settings form can treat them uniformly
// (Liskov). New field kinds plug into WIDGETS without touching callers
// (Open/Closed).

import { clear, el } from './dom.js';
// The one place that knows how a brightness rides inside a colour. schema.js
// needs it too (a rainbow's summary quotes the percentage), and two copies of
// that conversion is exactly the drift this file's descriptors exist to avoid.
// The import is one-way - schema.js is DOM-free data and never reaches back.
import {
  ACTIONS, ACTION_BY_TYPE, MAX_SEQUENCE_S, MAX_SEQUENCE_STEPS, SEQUENCE_ACTIONS,
  TEMPLATE_BY_TYPE, describeEffect, describeTemplate, levelHex, levelPercent,
  modeLook,
} from './schema.js';
// The same painter the nav and the App page use, so a look previews once and
// identically wherever it is shown.
import { paint as applySwatch, unpaint } from './ledPreview.js';

function errLine() {
  return el('span', { className: 'fld-err' });
}

const hintLine = (spec) => (spec.hint
  ? el('span', { className: 'fld-hint', 'data-help': true, textContent: spec.hint })
  : null);

// Two independent attributes on the same node, and neither toggle may imply
// the other (TODO 14): `data-help` marks tutorial copy that the page's Tips
// toggle reveals (help.js), `data-tier="tinker"` marks a field that Tinker
// reveals at all. A field is 'basic' by simply not carrying the second.
const tierAttr = (spec) => (spec.tier === 'tinker' ? { 'data-tier': 'tinker' } : {});

// Standard layout: label text above the control, optional hint + error below.
function wrap(spec, control, errEl) {
  return el('label', { className: 'fld', ...tierAttr(spec) }, [
    el('span', { className: 'fld-label', textContent: spec.label }),
    control,
    hintLine(spec),
    errEl,
  ]);
}

// The one rule the three text-shaped widgets share: full label in the message
// the form collects, one short word in the field itself.
const requiredValidator = (spec, obj, err) => () => {
  const msg = spec.required && !String(obj[spec.key] ?? '').trim()
    ? `${spec.label} is required` : null;
  err.textContent = msg ? 'Required' : '';
  return msg;
};

// A slider and a typed box bound to the same value (TODO 27) - one key, not
// two fields, because a descriptor could forget to keep two copies in step.
// Dragging cannot leave the range, so typing may not either: `clamp` is
// applied on the way in, and the box is re-shown from the slider once typing
// stops so a clamped entry does not sit there looking accepted verbatim.
function sliderPair({ min, max, step, start, clamp, set }) {
  const slider = el('input', {
    type: 'range', className: 'inp inp-range', min, max, step, value: start,
    oninput: () => { set(Number(slider.value)); number.value = slider.value; },
  });
  const number = el('input', {
    type: 'number', className: 'inp inp-range-num', min, max, step, value: start,
    oninput: () => {
      // A mid-typing box ("", "-", "0.") is not a value yet - leave it alone
      // rather than fighting the keystroke that is about to make it one.
      if (number.value === '') return;
      const parsed = Number(number.value);
      if (Number.isFinite(parsed)) set(clamp(parsed));
    },
    onchange: () => { number.value = slider.value; },
  });
  return { slider, number };
}

// A numeric bound may be a plain number or a function of `ctx`, resolved at
// render time. The live one is the flash floor: it is a *setting* rather than
// a constant, so a slider that hard-coded its own minimum would keep offering
// periods the parser has been told to reject. Same trick `select` already
// uses for dynamic `options`.
function bound(spec, name, ctx) {
  const raw = spec[name];
  const value = typeof raw === 'function' ? raw(ctx) : raw;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

// Which api method (and which field of its JSON) a `suggest` name pulls
// from - a table rather than a branch, so the midi action's `port` (output)
// and the metronome's `clock_port` (input) share one mechanism while asking
// for different lists (Open/Closed). See webui.py's /api/midi/ports.
const SUGGEST_SOURCES = {
  midi_out: { method: 'midiPorts', field: 'out' },
  midi_in: { method: 'midiPorts', field: 'in' },
};

let _suggestSeq = 0;

// Layers a <datalist> onto a text `input`, fed by the service - free text
// stays first-class, since a <datalist> only ever offers and never restricts.
// Optional by construction, the same rule as colorEngine.js's showLook: no
// `ctx.api`, no matching method on it (the offline editor's FileApi has none),
// or a failed call all leave the plain input as it was - a missing suggestion
// is not a broken field.
//
// Returns a DocumentFragment holding [input, datalist] so the caller's DOM
// shape does not change: appending a fragment moves its children in place of
// itself, so the datalist rides along as an invisible sibling rather than
// wrapping the input. Null when `spec.suggest` does not apply.
function attachSuggestions(spec, input, ctx) {
  const source = spec.suggest && SUGGEST_SOURCES[spec.suggest];
  if (!source || typeof ctx?.api?.[source.method] !== 'function') return null;

  const listId = `suggest-${spec.key}-${(_suggestSeq += 1)}`;
  const datalist = el('datalist', { id: listId });
  input.setAttribute('list', listId);
  ctx.api[source.method]()
    .then((data) => {
      const names = (data && data[source.field]) || [];
      datalist.append(...names.map((name) => el('option', { value: name })));
    })
    .catch(() => {}); // no suggestions beats a broken field

  const fragment = document.createDocumentFragment();
  fragment.append(input, datalist);
  return fragment;
}

function textInput(type, spec, obj, onInput, ctx) {
  const input = el('input', {
    type,
    className: 'inp',
    value: obj[spec.key] ?? '',
    placeholder: spec.placeholder || '',
    oninput: () => { obj[spec.key] = input.value; onInput(); },
  });
  const err = errLine();
  return {
    el: wrap(spec, attachSuggestions(spec, input, ctx) ?? input, err),
    validate: requiredValidator(spec, obj, err),
  };
}

const WIDGETS = {
  text: (spec, obj, onInput, ctx) => textInput('text', spec, obj, onInput, ctx),

  // A length of time, stored in seconds and shown in whichever unit reads
  // better. Seconds are canonical because one field has to express a 25-minute
  // focus block and a 20-second Tabata interval, and `0.333` is not a way to
  // write twenty seconds. The unit is inferred rather than stored - a whole
  // number of minutes shows as minutes - so 1500 opens as "25 min" and 40 as
  // "40 sec" with nothing recorded about which it "is".
  duration(spec, obj, onInput, ctx) {
    const stored = () => Number(obj[spec.key] ?? 0);
    let unit = stored() >= 60 && stored() % 60 === 0 ? 60 : 1;

    const input = el('input', {
      type: 'number', className: 'inp', step: 'any', value: String(stored() / unit),
      oninput: () => { obj[spec.key] = Number(input.value) * unit; onInput(); },
    });
    const units = el('select', { className: 'inp inp-unit' }, [
      el('option', { value: '1', textContent: 'sec' }),
      el('option', { value: '60', textContent: 'min' }),
    ]);
    units.value = String(unit);
    units.onchange = () => {
      // Convert the display, never the value: switching sec/min is a change
      // of how long you are looking at, not a change of how long it is.
      const seconds = stored();
      unit = Number(units.value);
      input.value = String(seconds / unit);
      applyMin();
    };

    const min = bound(spec, 'min', ctx);
    const applyMin = () => {
      if (min != null) input.min = String(min / unit);
    };
    applyMin();

    const err = errLine();
    return {
      el: wrap(spec, el('div', { className: 'row-tight' }, [input, units]), err),
      // The floor is the descriptor's to declare, not this widget's to assume.
      // A hard-coded "> 0" here made a *documented* default unsaveable: the
      // Pomodoro's lead_in_s says `min: 0` and means it ("0 = starts
      // immediately"), so a freshly seeded scene failed the editor's own
      // Check. An undeclared floor is zero - a length of time cannot run
      // backwards, and anything stricter than that is a fact about the field
      // rather than about durations.
      validate() {
        const seconds = stored();
        const floor = min ?? 0;
        let msg = null;
        let short = '';
        if (!Number.isFinite(seconds)) {
          msg = `${spec.label} must be a number`;
          short = 'Must be a number';
        } else if (seconds < floor) {
          msg = floor > 0
            ? `${spec.label} must be at least ${floor} seconds`
            : `${spec.label} cannot be negative`;
          short = floor > 0 ? `At least ${floor}s` : 'Cannot be negative';
        }
        err.textContent = short;
        return msg;
      },
    };
  },

  // A template inserter rather than a field: it writes *sibling* keys on the
  // object being edited and stores nothing under its own key. "I started from
  // Slack" is not a property of the webhook, it is how the webhook got filled
  // in, so nothing has to round-trip through the parser to remember it.
  //
  // Which keys it writes is the preset's own business (`set`), never named
  // here - the webhook picker and the DAW command picker write entirely
  // different ones, and a third should cost a table entry and no code.
  //
  // It needs `ctx.rebuild` because the fields it overwrites already exist in
  // the DOM with their old values. A caller with none still gets correct data
  // and a stale view, which is the honest degradation.
  preset(spec, obj, onInput, ctx) {
    const presets = typeof spec.presets === 'function' ? spec.presets() : (spec.presets || []);
    // Grouped into <optgroup> when the entries say so, flat when they do not.
    // The eight webhook services are a list you read; the Mackie map is fifty
    // entries you *navigate*, and an ungrouped select of that length is a
    // scroll bar with no landmarks in it.
    const option = (p) => el('option', { value: p.id, textContent: p.label });
    const groups = [];
    for (const preset of presets) {
      const name = preset.group || '';
      const last = groups[groups.length - 1];
      if (last && last.name === name) last.items.push(preset);
      else groups.push({ name, items: [preset] });
    }
    // Flattened rather than mapped: an <option> may only be a child of the
    // <select> or of an <optgroup>, so an ungrouped run has to be spread in
    // rather than wrapped in anything.
    const nodes = [el('option', { value: '', textContent: '- start from… -' })];
    for (const group of groups) {
      if (group.name) nodes.push(el('optgroup', { label: group.name }, group.items.map(option)));
      else nodes.push(...group.items.map(option));
    }
    const select = el('select', { className: 'inp' }, nodes);
    const note = el('span', { className: 'fld-hint', 'data-help': true });

    // Restored from the object rather than from a closure variable, because
    // choosing one rebuilds the whole field set and destroys this widget. The
    // key is *deliberately* transient: the parser does not know it, so it is
    // dropped the first time the config is saved and reloaded - which is the
    // right lifetime for "this is how the URL got filled in".
    //
    // **Unless the preset can be recognised again from what it wrote**, which
    // is what `derive` is for. A DAW command is reverse-lookupable - note 94
    // *is* Play - and without this the transient key's correct lifetime had a
    // visible cost: every raw MIDI field is Tinker-tier and hidden, so after a
    // save this dropdown was the only control on screen for that gesture, and
    // it reverted to "- start from… -" while the button went on sending the
    // right note. It read as the settings having been wiped. Reported
    // 2026-08-26; `describe()` had been deriving the same label all along.
    const remembered = presets.find((p) => p.id === obj[spec.key])
      || (typeof spec.derive === 'function' ? spec.derive(obj) : null);
    if (remembered) {
      select.value = remembered.id;
      note.textContent = remembered.hint || '';
    }

    select.onchange = () => {
      const chosen = presets.find((p) => p.id === select.value);
      if (!chosen) {
        delete obj[spec.key];
        note.textContent = '';
        onInput();
        return;
      }
      // Deep-copied so two modes started from the same preset do not end up
      // sharing one payload object between them.
      Object.assign(obj, {
        [spec.key]: chosen.id,
        ...JSON.parse(JSON.stringify(chosen.set || {})),
      });
      note.textContent = chosen.hint || '';
      onInput();
      // Without this the URL and payload fields keep showing their old values:
      // they were rendered before this widget overwrote the object underneath
      // them. A caller with no rebuild still gets correct data, just a stale
      // view - which is why this degrades rather than throwing.
      if (ctx && typeof ctx.rebuild === 'function') ctx.rebuild();
    };

    return {
      el: el('div', {}, [wrap(spec, select, errLine()), note]),
      validate: () => null,
    };
  },

  textarea(spec, obj, onInput) {
    const input = el('textarea', {
      className: 'inp',
      rows: 3,
      value: obj[spec.key] ?? '',
      placeholder: spec.placeholder || '',
      oninput: () => { obj[spec.key] = input.value; onInput(); },
    });
    const err = errLine();
    return { el: wrap(spec, input, err), validate: requiredValidator(spec, obj, err) };
  },

  number(spec, obj, onInput, ctx) {
    const min = bound(spec, 'min', ctx);
    const max = bound(spec, 'max', ctx);
    const input = el('input', {
      type: 'number', className: 'inp', value: obj[spec.key] ?? '',
      oninput: () => {
        obj[spec.key] = input.value === '' ? '' : Number(input.value);
        onInput();
      },
    });
    if (min != null) input.min = min;
    if (max != null) input.max = max;
    if (spec.step != null) input.step = spec.step;
    const err = errLine();
    return {
      el: wrap(spec, input, err),
      validate() {
        const value = obj[spec.key];
        let msg = null;
        if (value === '' || value == null || Number.isNaN(value)) msg = `${spec.label} must be a number`;
        else if (min != null && value < min) msg = `${spec.label} must be ≥ ${min}`;
        else if (max != null && value > max) msg = `${spec.label} must be ≤ ${max}`;
        err.textContent = msg ? 'Invalid' : '';
        return msg;
      },
    };
  },

  // The floor is a live bound (`bound` above), not a constant: it comes from
  // the config's min_flash_period_s, so raising the setting immediately widens
  // both controls instead of leaving one of them lying about what will be
  // accepted. That is also why the readout names the rate in Hz - the safety
  // limit is written in flashes per second, and a period in seconds is the
  // reciprocal of the number anyone reasons in.
  range(spec, obj, onInput, ctx) {
    const min = bound(spec, 'min', ctx) ?? 0;
    const start = Number(obj[spec.key] ?? min);
    // The ceiling stretches to fit a value that is already above it. `max` is
    // chosen so the range people actually use is draggable, and a config
    // holding a 600-second breathe is rare but real - pinning it to the slider's
    // top would silently rewrite it the moment the form rendered.
    const max = Math.max(bound(spec, 'max', ctx) ?? 100,
      Number.isFinite(start) ? start : 0);
    const clamp = (value) => Math.min(max, Math.max(min, value));
    const readout = el('span', { className: 'fld-readout' });
    const err = errLine();

    const show = () => {
      const value = Number(obj[spec.key]);
      readout.textContent = Number.isFinite(value)
        ? (spec.describe ? spec.describe(value) : String(value))
        : '-';
    };

    const { slider, number } = sliderPair({
      min, max, step: spec.step ?? 1, clamp,
      start: Number.isFinite(start) ? clamp(start) : min,
      set: (value) => {
        obj[spec.key] = value;
        slider.value = value;
        show();
        onInput();
      },
    });
    show();

    return {
      el: wrap(spec, el('span', { className: 'range-row' }, [slider, number, readout]), err),
      validate() {
        const value = Number(obj[spec.key]);
        let msg = null;
        if (!Number.isFinite(value)) msg = `${spec.label} must be a number`;
        // A stored value below the floor is not the slider's doing - a scene
        // file or a lowered setting can produce one. Say so rather than
        // silently snapping it, because the number is a safety limit.
        else if (value < min) msg = `${spec.label} must be ≥ ${min}`;
        else if (value > max) msg = `${spec.label} must be ≤ ${max}`;
        err.textContent = msg ? 'Invalid' : '';
        return msg;
      },
    };
  },

  // Static or dynamic <select>. `spec.options` is either an array of
  // { value, label } or a function returning that array at render time. A
  // dynamic options function receives `ctx` (the context createField was
  // called with, e.g. { getModes }) so it can read sibling state - this is
  // how the enter_mode picker lists the current takeover modes. Same
  // { el, validate } contract.
  // `options` may be a function of `(ctx, obj)`. The second argument is what
  // lets one select depend on another in the same action - `set_value`'s slot
  // list is decided by which app it names - and `spec.rebuilds` is the other
  // half of that: the field it depends on redraws the set. Optional by
  // construction, like every `ctx` capability here: an editor that provides no
  // `rebuild` shows a list that is right when it opened, never a broken one.
  select(spec, obj, onInput, ctx) {
    const options = typeof spec.options === 'function'
      ? (spec.options(ctx, obj) || [])
      : (spec.options || []);
    const input = el('select', {
      className: 'inp',
      onchange: () => {
        obj[spec.key] = input.value;
        onInput();
        if (spec.rebuilds) ctx?.rebuild?.();
      },
    }, options.map((o) => el('option', { value: o.value, textContent: o.label })));
    // Reflect the current value even if it is not (yet) in the list.
    input.value = obj[spec.key] ?? '';
    const err = errLine();
    return { el: wrap(spec, input, err), validate: requiredValidator(spec, obj, err) };
  },

  /**
   * Pick a mode by name, showing the light it runs in.
   *
   * A native `<select>` cannot do this: an `<option>` holds text, and the half
   * of a look that identifies it is the *movement* - "the slow blue one" is
   * how anyone actually refers to a mode (TODO 50). So this is a button and a
   * list of buttons, each carrying the same live swatch the nav and the App
   * page paint, from the same `modeLook`.
   *
   * A widget kind rather than a special case inside the `enter_mode` picker,
   * because capability is declared as data here - anything else that comes to
   * pick a mode asks for this kind and gets the swatch for free.
   *
   * Keyboard: the options are real buttons, so Tab and Enter work without a
   * listbox implementation; Escape closes and hands focus back.
   */
  // A `SequenceAction`'s step list (TODO 33). The one widget that edits a list
  // of *actions*, which is why it is here rather than in menu.js beside the
  // action pool: a sequence can be bound anywhere an action can, so its editor
  // has to travel with the field system rather than with one page.
  //
  // **Order is the whole point**, hence the arrows. **Nesting is not offered**
  // at all - `SEQUENCE_ACTIONS` has no `sequence` in it - so the control
  // cannot express the thing the parser would refuse.
  //
  // A step that names a pooled action stays a bare string here and is edited
  // with a picker, because a config written by hand may hold one and an editor
  // that quietly rewrote it into an inline copy would be the same data loss
  // the named-action pool exists to prevent.
  steps(spec, obj, onInput, ctx) {
    const NAMED = '__named__';
    const offered = ACTIONS.filter((a) => SEQUENCE_ACTIONS.includes(a.type));
    const list = () => (Array.isArray(obj[spec.key]) ? obj[spec.key] : (obj[spec.key] = []));
    const rows = el('div', { className: 'steps' });
    const err = errLine();
    const validators = [];

    const changed = () => { render(); onInput(); };

    const move = (from, to) => {
      const steps = list();
      if (to < 0 || to >= steps.length) return;
      [steps[from], steps[to]] = [steps[to], steps[from]];
      changed();
    };

    const render = () => {
      clear(rows);
      validators.length = 0;
      const steps = list();
      if (!steps.length) {
        rows.append(el('p', { className: 'menu-hint', textContent: 'No steps yet.' }));
      }
      steps.forEach((step, index) => rows.append(row(step, index, steps)));
      const add = el('button', {
        type: 'button', className: 'mini', textContent: '+ Add a step',
        disabled: steps.length >= MAX_SEQUENCE_STEPS,
        onclick: () => {
          steps.push(ACTION_BY_TYPE.midi.defaults());
          changed();
        },
      });
      rows.append(el('div', { className: 'add-row' }, [
        add,
        steps.length >= MAX_SEQUENCE_STEPS
          ? el('span', { className: 'fld-hint', textContent:
              `${MAX_SEQUENCE_STEPS} steps is the limit - a sequence holds the button while it runs.` })
          : null,
      ]));
    };

    const row = (step, index, steps) => {
      const named = typeof step === 'string';
      const fields = el('div', { className: 'gesture-fields' });

      const kind = el('select', {
        className: 'inp',
        onchange: () => {
          steps[index] = kind.value === NAMED ? '' : ACTION_BY_TYPE[kind.value].defaults();
          changed();
        },
      }, [
        ...offered.map((a) => el('option', { value: a.type, textContent: a.label })),
        el('option', { value: NAMED, textContent: 'Use a named action' }),
      ]);
      kind.value = named ? NAMED : (step.action || 'midi');

      // Written on the step it delays, because "wait, then do this" is the
      // order a person reads it in - and it is where the parser looks too.
      const wait = el('input', {
        type: 'number', className: 'inp step-wait', min: 0, max: MAX_SEQUENCE_S,
        step: 0.05, value: named ? '' : (step.wait_s ?? 0),
        disabled: named,
        title: named
          ? 'A named step runs straight away - a name has nowhere to put a delay.'
          : 'Seconds to wait before this step',
        oninput: () => {
          const value = Number(wait.value);
          if (!wait.value || value <= 0) delete step.wait_s;
          else step.wait_s = value;
          onInput();
        },
      });

      if (named) {
        const names = Object.keys((ctx && ctx.getActions && ctx.getActions()) || {}).sort();
        const options = [el('option', { value: '', textContent: '- pick one -' })];
        if (step && !names.includes(step)) {
          options.push(el('option', { value: step, textContent: `${step} (missing)` }));
        }
        options.push(...names.map((n) => el('option', { value: n, textContent: n })));
        const pick = el('select', {
          className: 'inp',
          onchange: () => { steps[index] = pick.value; onInput(); },
        }, options);
        pick.value = step || '';
        fields.append(el('label', { className: 'fld' }, [
          el('span', { className: 'fld-label', textContent: 'Named action' }),
          pick,
        ]));
        validators.push(() => (pick.value ? null : `step ${index + 1}: pick a named action`));
      } else {
        const descriptor = offered.find((a) => a.type === step.action);
        for (const field of (descriptor ? descriptor.fields : [])) {
          const built = createField(field, step, onInput, ctx);
          fields.append(built.el);
          validators.push(() => {
            const message = built.validate();
            return message ? `step ${index + 1}: ${message}` : null;
          });
        }
      }

      const button = (text, title, onclick, disabled = false) => el('button', {
        type: 'button', className: 'mini', textContent: text, title, onclick, disabled,
      });
      return el('div', { className: 'gesture-row' }, [
        el('div', { className: 'gesture-head' }, [
          el('span', { className: 'step-no', textContent: `${index + 1}.` }),
          kind,
          el('label', { className: 'step-wait-lbl' }, [
            el('span', { textContent: 'wait' }), wait, el('span', { textContent: 's' }),
          ]),
          button('↑', 'Move earlier', () => move(index, index - 1), index === 0),
          button('↓', 'Move later', () => move(index, index + 1), index === steps.length - 1),
          button('✕', 'Remove this step', () => { steps.splice(index, 1); changed(); }),
        ]),
        fields,
      ]);
    };

    render();
    return {
      el: wrap(spec, rows, err),
      validate() {
        const steps = list();
        if (spec.required && !steps.length) {
          err.textContent = 'Add at least one step';
          return `${spec.label} needs at least one step`;
        }
        for (const validate of validators) {
          const message = validate();
          if (message) {
            err.textContent = message;
            return message;
          }
        }
        err.textContent = '';
        return null;
      },
    };
  },

  modeSelect(spec, obj, onInput, ctx) {
    const options = typeof spec.options === 'function' ? (spec.options(ctx) || []) : (spec.options || []);
    const modes = (ctx && typeof ctx.getModes === 'function') ? (ctx.getModes() || []) : [];
    const looks = (ctx && typeof ctx.getLooks === 'function') ? (ctx.getLooks() || {}) : {};
    const palette = (ctx && typeof ctx.getPalette === 'function') ? (ctx.getPalette() || {}) : {};
    const byName = new Map(modes.filter((m) => m && m.name).map((m) => [m.name, m]));

    const paint = (node, name) => {
      const look = modeLook(byName.get(name), looks, palette);
      node.classList.toggle('empty', !look);
      if (look) applySwatch(node, look);
      else unpaint(node);
      node.title = look
        ? `While it runs: ${describeEffect(look)}`
        : "No colour of its own - it runs the button's own lights.";
    };

    const headSwatch = el('span', { className: 'pick-swatch' });
    const headName = el('span', { className: 'pick-name' });
    const head = el('button', {
      type: 'button', className: 'inp mode-pick',
      onclick: (e) => { e.stopPropagation(); setOpen(list.hidden); },
    }, [headSwatch, headName, el('span', { className: 'pick-caret', textContent: '▾' })]);

    const list = el('div', { className: 'mode-pick-list', hidden: true });
    const show = () => {
      const current = obj[spec.key] ?? '';
      const chosen = options.find((o) => o.value === current);
      headName.textContent = chosen ? chosen.label : (current || 'Choose an app…');
      headName.classList.toggle('unset', !current);
      // A target that no longer exists keeps its name and says so, rather than
      // silently reading as unset - the parser warns about exactly this and the
      // editor must not disagree with it.
      headName.classList.toggle('missing', Boolean(current) && !chosen);
      if (current && !chosen) headName.textContent = `${current} (missing)`;
      paint(headSwatch, current);
    };

    function setOpen(open) {
      list.hidden = !open;
      head.setAttribute('aria-expanded', String(open));
    }
    const away = (e) => {
      if (list.hidden) return;
      if (!wrapEl.contains(e.target)) setOpen(false);
    };
    document.addEventListener('click', away);
    head.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') { setOpen(true); }
    });

    for (const option of options) {
      const swatch = el('span', { className: 'pick-swatch' });
      paint(swatch, option.value);
      const mode = byName.get(option.value);
      list.append(el('button', {
        type: 'button', className: 'mode-pick-option',
        onclick: (e) => {
          e.stopPropagation();
          obj[spec.key] = option.value;
          show();
          setOpen(false);
          head.focus();
          onInput();
        },
      }, [
        swatch,
        el('span', { className: 'pick-name', textContent: option.label }),
        // `describe` stopped naming the template (TODO 101) - the nav has a
        // heading for that and this picker does not, so it prefixes the label
        // itself rather than a second description existing to carry it.
        el('span', { className: 'pick-note', textContent: mode ? describePick(mode) : '' }),
      ]));
    }
    if (!options.length) {
      list.append(el('p', { className: 'empty pick-empty', textContent:
        'No apps installed yet - install one from Apps.' }));
    }
    list.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      setOpen(false);
      head.focus();
    });

    show();
    const err = errLine();
    const wrapEl = el('div', { className: 'mode-pick-wrap' }, [head, list]);
    return { el: wrap(spec, wrapEl, err), validate: requiredValidator(spec, obj, err) };
  },

  // A colour swatch you can click to open the OS picker, with the hex value
  // beside it - the hex is what lands in config.json, so it should be
  // visible and copyable rather than hidden behind a colour well.
  color(spec, obj, onInput) {
    const current = obj[spec.key] || '#000000';
    const input = el('input', {
      type: 'color', className: 'inp inp-color', value: current,
      oninput: () => {
        obj[spec.key] = input.value;
        hex.textContent = input.value;
        onInput();
      },
    });
    const hex = el('span', { className: 'fld-hex', textContent: current });
    const err = errLine();
    return {
      el: wrap(spec, el('span', { className: 'color-row' }, [input, hex]), err),
      validate() {
        const msg = /^#[0-9a-fA-F]{6}$/.test(obj[spec.key] || '')
          ? null : `${spec.label} must be a colour`;
        err.textContent = msg ? 'Invalid' : '';
        return msg;
      },
    };
  },

  // Brightness for a style that makes its own hues (rainbow). It edits the
  // *same* `color` field as the picker above, because that is where the value
  // rides on the wire - the effect's brightest channel is its level - so a
  // grey is written rather than a new field being invented.
  //
  // The floor is 1%, not 0: zero is what an unset colour looks like in a config
  // written before this meant anything, and the firmware reads that as full.
  // Offering 0 would let someone pick a value that silently means its opposite
  // - the typed box (TODO 27) is clamped to the same [1, 100] the slider
  // already refuses to leave, so typing 0 cannot get there either.
  level(spec, obj, onInput) {
    const start = levelPercent(obj[spec.key]);
    const readout = el('span', { className: 'fld-readout', textContent: `${start}%` });
    const err = errLine();

    const { slider, number } = sliderPair({
      min: 1, max: 100, step: 1, start,
      // A whole percent, same as the slider's step: the bounds are the
      // widget's own, so unlike `range` there is no descriptor to read them
      // from and nothing to round against.
      clamp: (value) => Math.min(100, Math.max(1, Math.round(value))),
      set: (percent) => {
        obj[spec.key] = levelHex(percent);
        slider.value = percent;
        readout.textContent = `${percent}%`;
        onInput();
      },
    });

    return {
      el: wrap(spec, el('span', { className: 'range-row' }, [slider, number, readout]), err),
      validate: () => null,
    };
  },

  // A colour ramp: an ordered list of stops, each a colour pinned somewhere
  // between the start (0%) and the end (100%). Mirrors ramp.py's Stop.
  //
  // The position is editable rather than implied, because "hold this colour
  // for longer" is most of the point of a ramp. Adding or removing re-spaces
  // the ramp *only when it was already evenly spaced*, so the common case (a
  // list of colours) stays tidy and a hand-tuned ramp is never flattened by a
  // click.
  ramp(spec, obj, onInput) {
    const preview = el('div', { className: 'ramp-preview' });
    const rows = el('div', { className: 'ramp-rows' });
    const err = errLine();

    const evenAt = (index, count) => (count > 1 ? index / (count - 1) : 0);

    // Config may hold bare colour strings (a hand-written scene) or objects;
    // the API only ever returns objects, but reading both costs one branch.
    const normalise = (raw) => {
      const list = Array.isArray(raw) ? raw : [];
      return list.map((stop, index) => {
        const fallback = evenAt(index, list.length);
        if (typeof stop === 'string') return { color: stop, at: fallback };
        return {
          color: typeof stop?.color === 'string' ? stop.color : '#000000',
          at: typeof stop?.at === 'number' ? stop.at : fallback,
        };
      });
    };

    let stops = normalise(obj[spec.key]);

    const evenlySpaced = () => stops.every(
      (stop, index) => Math.abs(stop.at - evenAt(index, stops.length)) < 0.001,
    );
    const respace = () => stops.forEach((stop, index) => {
      stop.at = evenAt(index, stops.length);
    });

    const commit = () => {
      obj[spec.key] = stops.map((stop) => ({ color: stop.color, at: stop.at }));
      onInput();
    };

    const paint = () => {
      const ordered = [...stops].sort((a, b) => a.at - b.at);
      if (!ordered.length) {
        preview.style.background = 'transparent';
      } else if (ordered.length === 1) {
        preview.style.background = ordered[0].color;
      } else {
        preview.style.background = `linear-gradient(to right, ${
          ordered.map((s) => `${s.color} ${Math.round(s.at * 100)}%`).join(', ')})`;
      }
    };

    const render = () => {
      clear(rows);
      stops.forEach((stop, index) => {
        const swatch = el('input', {
          type: 'color', className: 'inp inp-color', value: stop.color,
          oninput: () => { stop.color = swatch.value; commit(); paint(); },
        });

        const at = el('input', {
          type: 'number', className: 'inp ramp-at', min: 0, max: 100, step: 1,
          value: Math.round(stop.at * 100),
          oninput: () => {
            const percent = Number(at.value);
            if (Number.isFinite(percent)) {
              stop.at = Math.min(100, Math.max(0, percent)) / 100;
              commit();
              paint();
            }
          },
        });

        rows.append(el('div', { className: 'ramp-row' }, [
          swatch,
          at,
          el('span', { className: 'ramp-pct', textContent: '%' }),
          // Never offer to remove the last one - an empty ramp is not a thing
          // you can mean, and the parser would just hand back the default.
          stops.length > 1 ? el('button', {
            type: 'button', className: 'mini danger', textContent: '×',
            title: 'Remove this colour',
            onclick: () => {
              const wasEven = evenlySpaced();
              stops.splice(index, 1);
              if (wasEven) respace();
              commit();
              render();
            },
          }) : null,
        ]));
      });

      rows.append(el('button', {
        type: 'button', className: 'mini', textContent: '+ Colour',
        onclick: () => {
          const wasEven = evenlySpaced();
          const last = stops[stops.length - 1];
          stops.push({ color: last ? last.color : '#ffffff', at: 1 });
          if (wasEven) respace();
          commit();
          render();
        },
      }));
      paint();
    };

    render();

    return {
      el: wrap(spec, el('div', { className: 'ramp-edit' }, [preview, rows]), err),
      validate() {
        let msg = null;
        if (!stops.length) msg = `${spec.label} needs at least one colour`;
        else if (!stops.every((s) => /^#[0-9a-fA-F]{6}$/.test(s.color))) {
          msg = `${spec.label} has an invalid colour`;
        }
        err.textContent = msg ? 'Invalid' : '';
        return msg;
      },
    };
  },

  // A subdivision ladder: intervals paired with colours, read top down, where
  // the largest interval dividing the current time wins. Mirrors ladder.py.
  //
  // Rows are kept sorted longest-first because that is the order the thing
  // *reads* in, and because "largest matching wins" is impossible to reason
  // about in an arbitrary order. The preview is a strip of the first cycle
  // rather than a gradient: a ladder is a run of discrete flashes, and drawing
  // it as a blend would misrepresent the one thing it does.
  ladder(spec, obj, onInput) {
    const err = errLine();
    const rows = el('div', { className: 'ladder-rows' });
    const preview = el('div', { className: 'ladder-preview' });
    const body = el('div', { className: 'ladder-body' });

    const current = obj[spec.key] && typeof obj[spec.key] === 'object' ? obj[spec.key] : {};
    const value = {
      enabled: !!current.enabled,
      tick_s: Number(current.tick_s) > 0 ? Number(current.tick_s) : 0.5,
      base: /^#[0-9a-fA-F]{6}$/.test(current.base || '') ? current.base : '#000000',
      rungs: (Array.isArray(current.rungs) ? current.rungs : [])
        .filter((r) => r && Number(r.every_s) > 0)
        .map((r) => ({ every_s: Number(r.every_s), color: r.color || '#ffffff' })),
    };

    const commit = () => {
      value.rungs.sort((a, b) => b.every_s - a.every_s);
      obj[spec.key] = {
        enabled: value.enabled, tick_s: value.tick_s, base: value.base,
        rungs: value.rungs.map((r) => ({ every_s: r.every_s, color: r.color })),
      };
      onInput();
    };

    // Which colour a given moment shows - the same "largest matching rung
    // wins" rule as ladder.py, in milliseconds for the same reason.
    const colorAt = (seconds) => {
      const ms = Math.round(seconds * 1000);
      let best = null;
      for (const rung of value.rungs) {
        const step = Math.round(rung.every_s * 1000);
        if (step <= 0) continue;
        const offset = ms % step;
        if ((offset <= 1 || step - offset <= 1) && (!best || step > Math.round(best.every_s * 1000))) {
          best = rung;
        }
      }
      return best ? best.color : value.base;
    };

    const paint = () => {
      clear(preview);
      // One full cycle of the longest rung, capped so a 10-minute rung does
      // not try to draw 1200 cells.
      const longest = value.rungs.length ? Math.max(...value.rungs.map((r) => r.every_s)) : 1;
      const count = Math.min(40, Math.max(1, Math.round(longest / value.tick_s) + 1));
      for (let i = 0; i < count; i += 1) {
        const cell = el('span', {
          className: 'ladder-cell', title: `${(i * value.tick_s).toFixed(2)}s`,
        });
        cell.style.background = colorAt(i * value.tick_s);
        preview.append(cell);
      }
    };

    const render = () => {
      clear(rows);
      value.rungs.sort((a, b) => b.every_s - a.every_s);
      value.rungs.forEach((rung, index) => {
        const every = el('input', {
          type: 'number', className: 'inp ladder-every',
          min: 0.1, step: 0.1, value: rung.every_s,
          oninput: () => {
            const seconds = Number(every.value);
            if (seconds > 0) { rung.every_s = seconds; commit(); paint(); }
          },
        });
        const swatch = el('input', {
          type: 'color', className: 'inp inp-color', value: rung.color,
          oninput: () => { rung.color = swatch.value; commit(); paint(); },
        });

        rows.append(el('div', { className: 'ladder-row' }, [
          el('span', { className: 'ladder-lbl', textContent: 'every' }),
          every,
          // Seconds for a timer, beats for the metronome - the ladder counts,
          // and what it counts is declared on the descriptor.
          el('span', { className: 'ladder-lbl', textContent: spec.unit ?? 's' }),
          swatch,
          el('button', {
            type: 'button', className: 'mini danger', textContent: '×',
            title: 'Remove this interval',
            onclick: () => { value.rungs.splice(index, 1); commit(); render(); },
          }),
        ]));
      });

      rows.append(el('button', {
        type: 'button', className: 'mini', textContent: '+ Interval',
        onclick: () => {
          const shortest = value.rungs.length
            ? Math.min(...value.rungs.map((r) => r.every_s)) : 2;
          value.rungs.push({ every_s: Math.max(0.1, shortest / 2), color: '#ffffff' });
          commit();
          render();
        },
      }));
      paint();
    };

    const enabled = el('input', {
      type: 'checkbox', checked: value.enabled,
      onchange: () => {
        value.enabled = enabled.checked;
        body.hidden = !value.enabled;  // off is the default; hide the detail
        commit();
      },
    });

    const tick = el('input', {
      type: 'number', className: 'inp ladder-every',
      min: 0.05, step: 0.05, value: value.tick_s,
      oninput: () => {
        const seconds = Number(tick.value);
        if (seconds > 0) { value.tick_s = seconds; commit(); paint(); }
      },
    });

    const base = el('input', {
      type: 'color', className: 'inp inp-color', value: value.base,
      oninput: () => { value.base = base.value; commit(); paint(); },
    });

    // No tick row where the cadence is not the mode's to set - the metronome's
    // tempo is tapped in, so offering a tick there would be a control that
    // does nothing.
    //
    // Tinker-tier by construction, not by descriptor (TODO 14): the rungs are
    // the point of a ladder and stay basic, but the tick rate and the
    // off-beat colour are fine-tuning on top of a sane default (0.5s, black).
    // This split is inherent to the widget's own layout rather than a fact
    // about any one mode's ladder field, so it is marked here directly
    // instead of threading a second tier through `spec`.
    const lbl = (text) => el('span', { className: 'ladder-lbl', textContent: text });
    body.append(
      el('div', { className: 'ladder-row', 'data-tier': 'tinker' },
        spec.showTick === false
          ? [lbl('off-beat'), base]
          : [lbl('tick'), tick, lbl('s, off-beat'), base]),
      rows,
      preview,
    );
    body.hidden = !value.enabled;
    render();

    return {
      el: el('div', { className: 'fld ladder-edit' }, [
        el('label', { className: 'fld-check' }, [
          enabled,
          el('span', { className: 'fld-label', textContent: spec.label }),
        ]),
        hintLine(spec),
        body,
        err,
      ]),
      validate() {
        const msg = value.enabled && !value.rungs.length
          ? `${spec.label} needs at least one interval` : null;
        err.textContent = msg ? 'Invalid' : '';
        return msg;
      },
    };
  },

  // Its own label rather than wrap(): a checkbox reads left of its text, not
  // above it.
  checkbox(spec, obj, onInput) {
    const input = el('input', {
      type: 'checkbox', checked: !!obj[spec.key],
      onchange: () => { obj[spec.key] = input.checked; onInput(); },
    });
    return {
      el: el('label', { className: 'fld fld-check', ...tierAttr(spec) }, [
        input,
        el('span', { className: 'fld-label', textContent: spec.label }),
        hintLine(spec),
      ]),
      validate: () => null,
    };
  },

  // "Show on the button", for the one action that has no button to show on
  // (TODO 65). A webhook's body is assembled from three places with a
  // precedence rule between them, and the only way to see the result used to
  // be to stand up a receiver.
  //
  // It edits nothing. `spec.key` is unused and `validate` always passes: this
  // is a *field descriptor that is a control*, which is what keeps it out of
  // every sub-editor's code - a gesture, a hook, a reflex, a pool entry and a
  // sequence step all loop over `descriptor.fields`, so declaring it once on
  // the webhook action puts it in all five.
  //
  // Optional by construction, the rule colorEngine's showLook set: no
  // `ctx.api.previewWebhook` (the offline editor's FileApi has none) and the
  // row simply is not there.
  webhookPreview(spec, obj, _onInput, ctx) {
    const pass = () => null;
    if (typeof ctx?.api?.previewWebhook !== 'function') {
      return { el: el('span'), validate: pass };
    }
    const out = el('pre', { className: 'mono webhook-out', hidden: true });
    const note = el('span', { className: 'fld-err' });
    // Sample values, not real ones: the question this answers is "which keys
    // arrive", and inventing a plausible 4 for `blocks` is clearer than
    // showing a zero that looks like a measurement. Empty when the surrounding
    // editor does not know the template - a reflex's webhook has no app.
    const sampleSummary = () => {
      const keys = (typeof ctx.summaryKeys === 'function' ? ctx.summaryKeys() : null) || [];
      return Object.fromEntries(keys.map((k, i) => [k.key, i + 1]));
    };

    const run = async (send) => {
      note.textContent = send ? 'Sending…' : 'Building…';
      out.hidden = true;
      try {
        const res = await ctx.api.previewWebhook({
          action: obj,
          trigger: 'short_press',
          mode: typeof ctx.modeName === 'function' ? ctx.modeName() : null,
          summary: sampleSummary(),
          send,
        });
        const lines = [`POST ${res.url}`, JSON.stringify(res.payload, null, 2)];
        if (res.sent) lines.push(res.ok ? `✓ ${res.message}` : `✗ ${res.message}`);
        for (const complaint of res.dropped || []) lines.push(`! ${complaint}`);
        out.textContent = lines.join('\n');
        out.hidden = false;
        note.textContent = '';
      } catch (err) {
        note.textContent = String((err && err.message) || err);
      }
    };

    const row = el('div', { className: 'row' }, [
      el('button', {
        type: 'button', className: 'primary', textContent: 'Preview payload',
        onclick: () => run(false),
      }),
      el('button', { type: 'button', textContent: 'Send a test', onclick: () => run(true) }),
    ]);
    return {
      el: el('label', { className: 'fld', ...tierAttr(spec) }, [
        el('span', { className: 'fld-label', textContent: spec.label }),
        row,
        hintLine(spec),
        note,
        out,
      ]),
      validate: pass,
    };
  },

  // An object by default, a list where the descriptor says `shape: 'list'`.
  // The shape is **declared, not sniffed**: an empty box has to write `[]` or
  // `{}` and there is nothing left to sniff it from. This widget refused an
  // array outright, which made every list-shaped field using it uneditable in
  // the browser while its parser took a list happily - OSC `args`, a signal
  // light's positions and a control surface's, three of the four. Same family
  // as the textarea rule in CLAUDE.md: a widget whose shape disagrees with the
  // parser fails at the moment of saving, not at the moment of writing.
  json(spec, obj, onInput) {
    const isList = spec.shape === 'list';
    const current = obj[spec.key];
    const hasContent = current != null && (
      Array.isArray(current) ? current.length : Object.keys(current).length
    );
    const input = el('textarea', {
      className: 'inp mono',
      rows: 4,
      value: hasContent ? JSON.stringify(current, null, 2) : '',
      placeholder: isList ? '[ ]' : '{ }',
      oninput: () => { parse(); onInput(); },
    });
    const err = errLine();
    const parse = () => {
      const text = input.value.trim();
      if (!text) {
        obj[spec.key] = isList ? [] : {};
        err.textContent = '';
        return null;
      }
      try {
        const value = JSON.parse(text);
        const ok = isList
          ? Array.isArray(value)
          : typeof value === 'object' && value !== null && !Array.isArray(value);
        if (!ok) throw new Error('wrong shape');
        obj[spec.key] = value;
        err.textContent = '';
        return null;
      } catch {
        err.textContent = isList
          ? 'Must be a JSON list, e.g. [{"name": "Stopped"}]'
          : 'Must be a JSON object, e.g. {"key": "value"}';
        return `${spec.label}: invalid JSON`;
      }
    };
    return { el: wrap(spec, input, err), validate: parse };
  },
};

/**
 * Build a field for `spec` bound to `obj[spec.key]`. `onInput` is called on
 * every edit (the menu uses it to flag unsaved changes). `ctx` is an optional
 * context object passed through to dynamic widgets (e.g. a select whose
 * `options` is a function reading `ctx.getModes()`). Returns { el, validate }.
 */
/** "Stopwatch - logs “mile run”": the kind, then what makes this one itself.
 *  Only the picker needs both halves; the nav already says the kind. */
function describePick(mode) {
  const label = TEMPLATE_BY_TYPE[mode?.template]?.label;
  const detail = describeTemplate(mode);
  return label ? `${label} - ${detail}` : detail;
}

export function createField(spec, obj, onInput, ctx) {
  return (WIDGETS[spec.kind] || WIDGETS.text)(spec, obj, onInput, ctx);
}
