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
import { levelHex, levelPercent } from './schema.js';

function errLine() {
  return el('span', { className: 'fld-err' });
}

// Standard layout: label text above the control, optional hint + error below.
// The hint carries `data-help`: it's tutorial copy, hidden unless the page's
// Tips toggle (see help.js) is on, so a form full of fields reads as short
// labels by default rather than a paragraph per field.
//
// `data-tier`: the other, independent axis (TODO 14). A field defaults to
// 'basic' by simply not carrying the attribute - only 'tinker' fields are
// marked, and help.js hides `[data-tier="tinker"]` the same way it hides
// `[data-help]`. Two separate attributes on the same node is the whole
// mechanism: Tips decides whether the hint below is readable, Tinker decides
// whether the field exists on screen at all, and neither toggle can imply
// the other.
function wrap(spec, control, errEl) {
  const tier = spec.tier === 'tinker' ? { 'data-tier': 'tinker' } : {};
  return el('label', { className: 'fld', ...tier }, [
    el('span', { className: 'fld-label', textContent: spec.label }),
    control,
    spec.hint ? el('span', { className: 'fld-hint', 'data-help': true, textContent: spec.hint }) : null,
    errEl,
  ]);
}

function requiredError(spec, value) {
  return spec.required && !String(value ?? '').trim() ? `${spec.label} is required` : null;
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
// from - a table entry rather than a branch, so the midi action's `port`
// (output) and the metronome's `clock_port` (input) can share one mechanism
// while asking for different lists (Open/Closed). See webui.py's
// /api/midi/ports and api.js's midiPorts().
const SUGGEST_SOURCES = {
  midi_out: { method: 'midiPorts', field: 'out' },
  midi_in: { method: 'midiPorts', field: 'in' },
};

let _suggestSeq = 0;

// Layers a <datalist> onto a text `input`, fed by the service - free text
// stays first-class (a port plugged in after the page loaded still types in
// fine; a <datalist> only ever offers, never restricts). Optional by
// construction, the same rule as colorEngine.js's showLook: no `ctx.api`, no
// matching method on it (the offline editor's FileApi has none), or a
// failed call all leave the plain input exactly as it already was, rather
// than surfacing an error - a missing suggestion is not a broken field.
//
// Returns a DocumentFragment holding [input, datalist] so the caller's DOM
// shape does not change: appending a fragment moves its children in place
// of itself, so the datalist rides along as an invisible sibling of the
// input rather than adding a wrapping element around it. Returns null when
// `spec.suggest` does not apply, so the caller falls back to the bare input.
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
  });
  const err = errLine();
  input.addEventListener('input', () => {
    obj[spec.key] = input.value;
    onInput();
  });
  return {
    el: wrap(spec, attachSuggestions(spec, input, ctx) ?? input, err),
    validate() {
      const msg = requiredError(spec, obj[spec.key]);
      err.textContent = msg ? 'Required' : '';
      return msg;
    },
  };
}

const WIDGETS = {
  text: (spec, obj, onInput, ctx) => textInput('text', spec, obj, onInput, ctx),

  // A length of time, stored in seconds and shown in whichever unit reads
  // better. Seconds are canonical because the same field has to express a
  // 25-minute focus block and a 20-second Tabata interval, and `0.333` is not
  // a way to write twenty seconds. Making the *unit* a display choice is what
  // lets one field serve both without either looking absurd.
  //
  // The unit is inferred, not stored: a whole number of minutes shows as
  // minutes, anything else as seconds. So 1500 opens as "25 min" and 40 opens
  // as "40 sec" with nothing recorded anywhere about which it "is".
  duration(spec, obj, onInput, ctx) {
    const stored = () => Number(obj[spec.key] ?? 0);
    let unit = stored() >= 60 && stored() % 60 === 0 ? 60 : 1;

    const input = el('input', {
      type: 'number', className: 'inp', step: 'any', value: String(stored() / unit),
    });
    const units = el('select', { className: 'inp inp-unit' }, [
      el('option', { value: '1', textContent: 'sec' }),
      el('option', { value: '60', textContent: 'min' }),
    ]);
    units.value = String(unit);

    const min = bound(spec, 'min', ctx);
    const applyMin = () => {
      if (min != null) input.min = String(min / unit);
    };
    applyMin();

    const err = errLine();
    input.addEventListener('input', () => {
      obj[spec.key] = Number(input.value) * unit;
      onInput();
    });
    units.addEventListener('change', () => {
      // Convert the display, never the value: switching sec/min is a change
      // of how long you are looking at, not a change of how long it is.
      const seconds = stored();
      unit = Number(units.value);
      input.value = String(seconds / unit);
      applyMin();
    });

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
  // object being edited and stores nothing under its own key, so nothing has
  // to round-trip through the parser to remember which one you picked. That
  // is deliberate - "I started from Slack" is not a property of the webhook,
  // it is how the webhook got filled in, and persisting it would be a config
  // surface that only ever restates what the URL already says.
  //
  // Which keys it writes is the preset's own business (`set`), not this
  // widget's. It used to assign `url` and `payload` by name, which made a
  // generic-looking widget silently webhook-only; the DAW command picker on
  // the midi action is the second user and writes three entirely different
  // keys. Adding a third should need a table entry and no code here.
  //
  // It needs `ctx.rebuild` because the fields it overwrites already exist in
  // the DOM with their old values. Callers that do not supply one get a
  // picker that still writes the object and simply does not redraw, which is
  // the honest degradation - no caller silently loses data.
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
    const remembered = presets.find((p) => p.id === obj[spec.key]);
    if (remembered) {
      select.value = remembered.id;
      note.textContent = remembered.hint || '';
    }

    select.addEventListener('change', () => {
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
    });

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
    });
    const err = errLine();
    input.addEventListener('input', () => {
      obj[spec.key] = input.value;
      onInput();
    });
    return {
      el: wrap(spec, input, err),
      validate() {
        const msg = requiredError(spec, obj[spec.key]);
        err.textContent = msg ? 'Required' : '';
        return msg;
      },
    };
  },

  number(spec, obj, onInput, ctx) {
    const min = bound(spec, 'min', ctx);
    const max = bound(spec, 'max', ctx);
    const input = el('input', { type: 'number', className: 'inp', value: obj[spec.key] ?? '' });
    if (min != null) input.min = min;
    if (max != null) input.max = max;
    if (spec.step != null) input.step = spec.step;
    const err = errLine();
    input.addEventListener('input', () => {
      obj[spec.key] = input.value === '' ? '' : Number(input.value);
      onInput();
    });
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

  // A slider with a typed number beside it, both bound to the same key
  // (TODO 27) - not a second field, because a template descriptor could
  // forget to keep two copies in step. For a flash period the *shape* of the
  // value still matters more than the digits - you are choosing a rate you
  // can picture - so the slider stays the primary control and the box is
  // clamped on commit exactly where dragging already stops: typing 0.02
  // cannot leave the field holding a value dragging could never reach.
  //
  // The floor is a live bound (`bound` above), not a constant: it comes from
  // the config's min_flash_period_s, so raising the setting immediately widens
  // both controls instead of leaving one of them lying about what will be
  // accepted. That is also why the readout names the rate in Hz - the safety
  // limit is written in flashes per second, and a period in seconds is the
  // reciprocal of the number anyone reasons in.
  range(spec, obj, onInput, ctx) {
    const min = bound(spec, 'min', ctx) ?? 0;
    const step = spec.step ?? 1;
    const start = Number(obj[spec.key] ?? min);
    // The ceiling stretches to fit a value that is already above it. `max` is
    // chosen so the range people actually use is draggable, and a config
    // holding a 600-second breathe is rare but real - pinning it to the slider's
    // top would silently rewrite it the moment the form rendered.
    const max = Math.max(bound(spec, 'max', ctx) ?? 100,
      Number.isFinite(start) ? start : 0);
    const clamp = (value) => Math.min(max, Math.max(min, value));
    const slider = el('input', {
      type: 'range', className: 'inp inp-range',
      min, max, step,
      value: Number.isFinite(start) ? clamp(start) : min,
    });
    const number = el('input', {
      type: 'number', className: 'inp inp-range-num',
      min, max, step,
      value: slider.value,
    });
    const readout = el('span', { className: 'fld-readout' });
    const err = errLine();

    const show = () => {
      const value = Number(obj[spec.key]);
      if (!Number.isFinite(value)) {
        readout.textContent = '-';
        return;
      }
      readout.textContent = spec.describe ? spec.describe(value) : String(value);
    };

    const set = (value) => {
      obj[spec.key] = value;
      slider.value = value;
      show();
      onInput();
    };

    slider.addEventListener('input', () => {
      set(Number(slider.value));
      number.value = slider.value;
    });
    number.addEventListener('input', () => {
      // A mid-typing box ("", "-", "0.") is not a value yet - leave it alone
      // rather than fighting the keystroke that is about to make it one.
      if (number.value === '') return;
      const parsed = Number(number.value);
      if (Number.isFinite(parsed)) set(clamp(parsed));
    });
    // Once typing stops, show what actually got stored - so a floored value
    // does not sit in the box looking like it was accepted verbatim.
    number.addEventListener('change', () => { number.value = slider.value; });
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
  select(spec, obj, onInput, ctx) {
    const options = typeof spec.options === 'function' ? (spec.options(ctx) || []) : (spec.options || []);
    const input = el('select', { className: 'inp' },
      options.map((o) => el('option', { value: o.value, textContent: o.label })));
    // Reflect the current value even if it is not (yet) in the list.
    input.value = obj[spec.key] ?? '';
    const err = errLine();
    input.addEventListener('change', () => {
      obj[spec.key] = input.value;
      onInput();
    });
    return {
      el: wrap(spec, input, err),
      validate() {
        const msg = requiredError(spec, obj[spec.key]);
        err.textContent = msg ? 'Required' : '';
        return msg;
      },
    };
  },

  // A colour swatch you can click to open the OS picker, with the hex value
  // beside it - the hex is what lands in config.json, so it should be
  // visible and copyable rather than hidden behind a colour well.
  color(spec, obj, onInput) {
    const current = obj[spec.key] || '#000000';
    const input = el('input', { type: 'color', className: 'inp inp-color', value: current });
    const hex = el('span', { className: 'fld-hex', textContent: current });
    const err = errLine();
    input.addEventListener('input', () => {
      obj[spec.key] = input.value;
      hex.textContent = input.value;
      onInput();
    });
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
    const clamp = (value) => Math.min(100, Math.max(1, value));
    const slider = el('input', {
      type: 'range', className: 'inp inp-range', min: 1, max: 100, step: 1,
      value: start,
    });
    const number = el('input', {
      type: 'number', className: 'inp inp-range-num', min: 1, max: 100, step: 1,
      value: start,
    });
    const readout = el('span', { className: 'fld-readout', textContent: `${start}%` });
    const err = errLine();

    const set = (percent) => {
      obj[spec.key] = levelHex(percent);
      slider.value = percent;
      readout.textContent = `${percent}%`;
      onInput();
    };

    slider.addEventListener('input', () => {
      set(Number(slider.value));
      number.value = slider.value;
    });
    number.addEventListener('input', () => {
      if (number.value === '') return;
      const parsed = Number(number.value);
      // A whole percent, same as the slider's step - not the general `range`
      // clamp, because a level has no descriptor bounds to read.
      if (Number.isFinite(parsed)) set(clamp(Math.round(parsed)));
    });
    number.addEventListener('change', () => { number.value = slider.value; });

    return {
      el: wrap(spec, el('span', { className: 'range-row' }, [slider, number, readout]), err),
      validate: () => null,
    };
  },

  // A colour ramp: an ordered list of stops, each a colour pinned somewhere
  // between the start (0%) and the end (100%). Mirrors ramp.py's Stop, and
  // what config.py's parser accepts.
  //
  // The position is editable rather than implied, because "hold this colour
  // for longer" is most of the point of a ramp - an evenly spread list is the
  // easy case, not the only one. A gradient strip sits above the rows so the
  // thing being edited is the thing you see.
  //
  // Adding or removing re-spaces the ramp *only when it was already evenly
  // spaced*. That way the common case (a list of colours) stays tidy on its
  // own, and a hand-tuned ramp is never silently flattened by a click.
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
        });
        swatch.addEventListener('input', () => {
          stop.color = swatch.value;
          commit();
          paint();
        });

        const at = el('input', {
          type: 'number', className: 'inp ramp-at', min: 0, max: 100, step: 1,
          value: Math.round(stop.at * 100),
        });
        at.addEventListener('input', () => {
          const percent = Number(at.value);
          if (Number.isFinite(percent)) {
            stop.at = Math.min(100, Math.max(0, percent)) / 100;
            commit();
            paint();
          }
        });

        const remove = el('button', {
          type: 'button', className: 'mini danger', textContent: '×',
          title: 'Remove this colour',
        });
        remove.addEventListener('click', () => {
          const wasEven = evenlySpaced();
          stops.splice(index, 1);
          if (wasEven) respace();
          commit();
          render();
        });

        rows.append(el('div', { className: 'ramp-row' }, [
          swatch,
          at,
          el('span', { className: 'ramp-pct', textContent: '%' }),
          // Never offer to remove the last one - an empty ramp is not a thing
          // you can mean, and the parser would just hand back the default.
          stops.length > 1 ? remove : null,
        ]));
      });

      const add = el('button', {
        type: 'button', className: 'mini', textContent: '+ Colour',
      });
      add.addEventListener('click', () => {
        const wasEven = evenlySpaced();
        const last = stops[stops.length - 1];
        stops.push({ color: last ? last.color : '#ffffff', at: 1 });
        if (wasEven) respace();
        commit();
        render();
      });
      rows.append(add);
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
  // the largest interval dividing the current time wins. Mirrors ladder.py and
  // what config.py's _parse_ladder accepts.
  //
  // Rows are kept sorted longest-first because that is the order the thing
  // *reads* in - the ten-second colour is the headline and the one-second
  // colour is the background - and because "largest matching wins" is
  // impossible to reason about in an arbitrary order.
  //
  // The preview is a strip of the first cycle rather than a gradient: a ladder
  // is a sequence of discrete flashes, and drawing it as a blend would
  // misrepresent the one thing it does.
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
        });
        every.addEventListener('input', () => {
          const seconds = Number(every.value);
          if (seconds > 0) { rung.every_s = seconds; commit(); paint(); }
        });

        const swatch = el('input', {
          type: 'color', className: 'inp inp-color', value: rung.color,
        });
        swatch.addEventListener('input', () => {
          rung.color = swatch.value; commit(); paint();
        });

        const remove = el('button', {
          type: 'button', className: 'mini danger', textContent: '×',
          title: 'Remove this interval',
        });
        remove.addEventListener('click', () => {
          value.rungs.splice(index, 1); commit(); render();
        });

        rows.append(el('div', { className: 'ladder-row' }, [
          el('span', { className: 'ladder-lbl', textContent: 'every' }),
          every,
          // Seconds for a timer, beats for the metronome - the ladder counts,
          // and what it counts is declared on the descriptor.
          el('span', { className: 'ladder-lbl', textContent: spec.unit ?? 's' }),
          swatch,
          remove,
        ]));
      });

      const add = el('button', { type: 'button', className: 'mini', textContent: '+ Interval' });
      add.addEventListener('click', () => {
        const shortest = value.rungs.length
          ? Math.min(...value.rungs.map((r) => r.every_s)) : 2;
        value.rungs.push({ every_s: Math.max(0.1, shortest / 2), color: '#ffffff' });
        commit();
        render();
      });
      rows.append(add);
      paint();
    };

    const enabled = el('input', { type: 'checkbox', checked: value.enabled });
    enabled.addEventListener('change', () => {
      value.enabled = enabled.checked;
      body.hidden = !value.enabled;  // off is the default; hide the detail
      commit();
    });

    const tick = el('input', {
      type: 'number', className: 'inp ladder-every',
      min: 0.05, step: 0.05, value: value.tick_s,
    });
    tick.addEventListener('input', () => {
      const seconds = Number(tick.value);
      if (seconds > 0) { value.tick_s = seconds; commit(); paint(); }
    });

    const base = el('input', { type: 'color', className: 'inp inp-color', value: value.base });
    base.addEventListener('input', () => { value.base = base.value; commit(); paint(); });

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
    body.append(
      spec.showTick === false
        ? el('div', { className: 'ladder-row', 'data-tier': 'tinker' }, [
            el('span', { className: 'ladder-lbl', textContent: 'off-beat' }),
            base,
          ])
        : el('div', { className: 'ladder-row', 'data-tier': 'tinker' }, [
            el('span', { className: 'ladder-lbl', textContent: 'tick' }),
            tick,
            el('span', { className: 'ladder-lbl', textContent: 's, off-beat' }),
            base,
          ]),
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
        spec.hint
          ? el('span', { className: 'fld-hint', 'data-help': true, textContent: spec.hint })
          : null,
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

  checkbox(spec, obj, onInput) {
    const input = el('input', { type: 'checkbox', checked: !!obj[spec.key] });
    input.addEventListener('change', () => {
      obj[spec.key] = input.checked;
      onInput();
    });
    // Own label rather than wrap() (a checkbox reads left of its text, not
    // above it), so the same data-tier marking wrap() does has to be repeated
    // here rather than shared.
    const tier = spec.tier === 'tinker' ? { 'data-tier': 'tinker' } : {};
    const node = el('label', { className: 'fld fld-check', ...tier }, [
      input,
      el('span', { className: 'fld-label', textContent: spec.label }),
      spec.hint ? el('span', { className: 'fld-hint', 'data-help': true, textContent: spec.hint }) : null,
    ]);
    return { el: node, validate: () => null };
  },

  json(spec, obj, onInput) {
    const current = obj[spec.key];
    const input = el('textarea', {
      className: 'inp mono',
      rows: 4,
      value: current && Object.keys(current).length ? JSON.stringify(current, null, 2) : '',
      placeholder: '{ }',
    });
    const err = errLine();
    const parse = () => {
      const text = input.value.trim();
      if (!text) {
        obj[spec.key] = {};
        err.textContent = '';
        return null;
      }
      try {
        const value = JSON.parse(text);
        if (typeof value !== 'object' || value === null || Array.isArray(value)) {
          throw new Error('not an object');
        }
        obj[spec.key] = value;
        err.textContent = '';
        return null;
      } catch {
        err.textContent = 'Must be a JSON object, e.g. {"key": "value"}';
        return `${spec.label}: invalid JSON`;
      }
    };
    input.addEventListener('input', () => {
      parse();
      onInput();
    });
    return { el: wrap(spec, input, err), validate: parse };
  },
};

/**
 * Build a field for `spec` bound to `obj[spec.key]`. `onInput` is called on
 * every edit (the menu uses it to flag unsaved changes). `ctx` is an optional
 * context object passed through to dynamic widgets (e.g. a select whose
 * `options` is a function reading `ctx.getModes()`). Returns { el, validate }.
 */
export function createField(spec, obj, onInput, ctx) {
  return (WIDGETS[spec.kind] || WIDGETS.text)(spec, obj, onInput, ctx);
}
