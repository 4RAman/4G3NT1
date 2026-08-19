// Renders and edits a single mode, always fully open: name → template
// <select> (swaps the template body) → activation <select> (swaps the
// activation body). menu.js's master/detail Modes tab shows one of these at
// a time in its detail pane, plus - only for the mode being saved-checked -
// a throwaway instance built purely to call validate(). Either way there is
// only ever one on screen, so this component has no collapse state of its
// own. It composes its fields from the widget factory and its
// template/activation choices from the schema registries, so it knows
// nothing about specific template, activation, action, or field kinds
// (Dependency Inversion). It mutates the mode object in place and reports
// edits, moves, and removal through injected handlers - it does not own the
// modes list.

import { el, clear } from './dom.js';
import {
  GESTURES, DAYS, ACTIONS, ACTION_BY_TYPE,
  TEMPLATES, TEMPLATE_BY_TYPE,
  ACTIVATIONS, ACTIVATION_BY_TYPE, describeActivation,
  describeExit, findEntryPoints,
  LED_STATE_BY_KEY, describeEffect, LOOK_PRESETS, LOOK_PRESET_GROUPS,
} from './schema.js';
import { paint as applySwatch } from './ledPreview.js';
import { createField } from './widgets.js';
import { createLookEditor } from './colorEngine.js';

export class ModeEditor {
  /**
   * @param {object} mode - the mode object (mutated in place)
   * @param {{onChange?: Function, onRemove?: Function,
   *          onMoveUp?: Function, onMoveDown?: Function, canReorder?: boolean,
   *          getModes?: Function}} handlers
   */
  constructor(mode, handlers = {}) {
    this.mode = mode;
    this.handlers = handlers;
    this._validators = []; // each returns an error string or null
    this.el = el('div', { className: 'mode-card' });
    this._build();
  }

  _changed() {
    this.refreshExplainers();
    this.handlers.onChange?.();
  }

  // Context handed to dynamic widgets (e.g. the enter_mode target select).
  // `getModes` returns the sibling modes so an options function can list
  // them; menu.js injects the provider, so this editor never reaches into
  // the modes list itself (Dependency Inversion).
  _fieldCtx() {
    return { getModes: this.handlers.getModes || (() => []) };
  }

  _build() {
    clear(this.el);
    this._validators = [];
    this.el.append(this._body());
  }

  /**
   * Mark this card as the one answering `gestures` right now.
   * @param {string[]} gestures - gesture labels, empty for "not in charge".
   */
  setActive(gestures) {
    if (!this.activeEl) return;
    this.activeEl.hidden = !gestures.length;
    if (!gestures.length) return;
    this.activeEl.textContent = '● Active now';
    this.activeEl.title = `Right now, a ${gestures.join(' or a ')} would be handled by this mode.`;
  }

  // --- body -----------------------------------------------------------

  _body() {
    this.bodyEl = el('div', { className: 'mode-body' });
    // A stable container so refreshExplainers() can rewrite the how-to-get-in
    // / how-to-get-out lines without rebuilding the fields you are editing.
    this.howtoEl = el('div', { className: 'howto' });
    // Colour above the mechanics, deliberately: what a mode looks like is how
    // you recognise it going off from across the room, not an afterthought
    // setting. Only takeover modes have one - an everyday mode never owns the
    // light long enough to have an appearance of its own.
    this.bodyEl.append(
      this._header(), this.howtoEl, this._looksPicker(),
      this._templatePicker(), this._activationPicker(),
    );
    this.refreshExplainers();
    return this.bodyEl;
  }

  /**
   * One picker per LED state this template owns, choosing a named look from
   * the pool (or the standard colour). A *reference*, not an inline effect:
   * that is what lets two Pomodoros differ while `WORKING` stays one shared
   * state, and it is the same shape the wire already pushes (ROADMAP D4).
   */
  _looksPicker() {
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    const states = descriptor?.ledStates || [];
    const wrap = el('div', { className: 'looks-row' });
    if (!states.length) {
      wrap.hidden = true;
      return wrap;
    }
    const pool = this.handlers.getLooks?.() || {};
    const names = Object.keys(pool).sort();

    wrap.append(el('span', { className: 'fld-label', textContent: 'How it looks' }));
    for (const key of states) {
      const state = LED_STATE_BY_KEY[key] || { key, label: key, meaning: '' };
      const select = el('select', { className: 'inp' }, [
        el('option', { value: '', textContent: '- standard colour -' }),
        ...names.map((n) => el('option', { value: n, textContent: n })),
      ]);
      const chosen = this.mode.looks?.[key] || '';
      // A look deleted from the pool leaves a dangling name. Show it rather
      // than silently snapping to the standard colour - the Python parser
      // warns about exactly this, and the two should agree.
      if (chosen && !names.includes(chosen)) {
        select.append(el('option', { value: chosen, textContent: `${chosen} (missing)` }));
      }
      select.value = chosen;

      const swatch = el('span', { className: 'palette-swatch' });
      const summary = el('span', { className: 'palette-summary' });
      // Where the editor for the *named* look appears, when one is named.
      // This is what makes the mode page the only place mode colour is
      // edited: picking is not enough if changing it sends you elsewhere.
      const editorSlot = el('div', { className: 'looks-editor' });

      const setLook = (name) => {
        if (!this.mode.looks) this.mode.looks = {};
        if (name) this.mode.looks[key] = name;
        else delete this.mode.looks[key];
        // An empty map is how "uses the palette" round-trips, and the Python
        // serialiser omits the key entirely - so drop it here too.
        if (!Object.keys(this.mode.looks).length) delete this.mode.looks;
      };

      const sharedBy = (name) => (this.handlers.getModes?.() || []).filter(
        (m) => m !== this.mode && Object.values(m.looks || {}).includes(name),
      ).length;

      const paint = () => {
        const current = this.handlers.getLooks?.() || {};
        const effect = current[select.value];
        clear(editorSlot);
        if (effect) {
          applySwatch(swatch, effect);
          summary.textContent = describeEffect(effect);
        } else {
          swatch.style.background = '';
          summary.textContent = select.value
            ? 'no such look'
            : 'the built-in colour for this state';
        }
        if (!effect) return;

        const editor = createLookEditor({
          get: () => effect,
          onChange: () => {
            applySwatch(swatch, effect);
            summary.textContent = describeEffect(effect);
            this.handlers.onLooksChanged?.();
          },
          floor: this.handlers.getFloor?.(),
          api: this.handlers.api,
          label: select.value,
        });
        editorSlot.append(editor.el);

        // Editing a shared look from here changes it everywhere, which is
        // the correct behaviour for a *named* look and a genuinely surprising
        // one if nobody says so. The copy button is the escape hatch, and it
        // is offered only when there is something to escape.
        const others = sharedBy(select.value);
        if (others) {
          const copy = el('button', {
            type: 'button',
            textContent: `Make a copy just for this mode`,
          });
          copy.addEventListener('click', () => {
            const name = this.handlers.addLook?.(select.value, effect);
            if (!name) return;
            rebuildOptions(name);
            setLook(name);
            paint();
            this._changed();
          });
          editorSlot.append(el('div', { className: 'looks-shared' }, [
            el('span', {
              className: 'menu-hint',
              textContent: `Shared with ${others} other mode${others > 1 ? 's' : ''} - editing changes it for all of them.`,
            }),
            copy,
          ]));
        }
      };

      const rebuildOptions = (selected) => {
        const current = Object.keys(this.handlers.getLooks?.() || {}).sort();
        clear(select);
        select.append(el('option', { value: '', textContent: '- standard colour -' }));
        for (const n of current) select.append(el('option', { value: n, textContent: n }));
        if (selected && !current.includes(selected)) {
          select.append(el('option', { value: selected, textContent: `${selected} (missing)` }));
        }
        select.value = selected || '';
      };

      select.addEventListener('change', () => {
        setLook(select.value);
        paint();
        this._changed();
      });

      // Making a look from a preset, without going anywhere. This is the path
      // that replaces "add one in the Lights tab first" - the pool still owns
      // it afterwards, so nothing about the shared-look model changes.
      const fromPreset = el('select', { className: 'inp' }, [
        el('option', { value: '', textContent: 'New look from a preset…' }),
        ...LOOK_PRESET_GROUPS.map((group) => el('optgroup', { label: group },
          LOOK_PRESETS.filter((p) => p.group === group).map(
            (p) => el('option', { value: p.id, textContent: p.label }),
          ))),
      ]);
      fromPreset.addEventListener('change', () => {
        const preset = LOOK_PRESETS.find((p) => p.id === fromPreset.value);
        fromPreset.value = '';
        if (!preset) return;
        const name = this.handlers.addLook?.(preset.label, preset.effect);
        if (!name) return;
        rebuildOptions(name);
        setLook(name);
        paint();
        this._changed();
      });

      paint();
      wrap.append(el('div', { className: 'looks-pick' }, [
        el('span', { className: 'palette-name', textContent: state.label }),
        swatch, select, fromPreset, summary,
      ]), editorSlot);
    }
    return wrap;
  }

  /**
   * Rewrite the takeover mode's "how do I get in / how do I get out" lines.
   * Called on every edit - including edits to *other* modes, since what starts
   * this one lives in their gestures, not in this card.
   */
  refreshExplainers() {
    if (!this.howtoEl) return;
    clear(this.howtoEl);
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    // Everyday modes are never entered or left, so there is nothing to explain.
    if (!descriptor || descriptor.nature !== 'takeover') {
      this.howtoEl.hidden = true;
      return;
    }
    this.howtoEl.hidden = false;

    if (descriptor.startedBy === 'schedule') {
      this.howtoEl.append(el('p', {
        className: 'howto-line',
        textContent: `Starts ${describeActivation(this.mode.activation)}`,
      }));
    } else {
      const entries = findEntryPoints(this.mode, this.handlers.getModes?.() || []);
      this.howtoEl.append(entries.length
        ? el('p', { className: 'howto-line', textContent: `Start: ${entries.join(', or ')}` })
        : el('p', { className: 'howto-line howto-warn' }, [
          '⚠ Not reachable',
          el('span', {
            'data-help': true,
            textContent: ' - give a gesture the "Enter a mode" action, pointing here.',
          }),
        ]));
    }

    const exit = describeExit(this.mode);
    if (exit) this.howtoEl.append(el('p', { className: 'howto-line', textContent: `Exit: ${exit}` }));
  }

  _header() {
    const name = el('input', {
      type: 'text', className: 'inp mode-name',
      value: this.mode.name || '', placeholder: 'Mode name',
    });
    name.addEventListener('input', () => {
      this.mode.name = name.value;
      this._changed();
    });

    // Filled in by setActive() from the host's own resolution - this is the
    // one place "which mode is actually in charge right now?" gets answered.
    this.activeEl = el('span', { className: 'mode-active', hidden: true });

    const btn = (text, title, cls, fn) => {
      const b = el('button', { type: 'button', className: `mini ${cls}`, textContent: text, title });
      b.addEventListener('click', fn);
      return b;
    };
    // Reorder arrows only where order decides anything: everyday modes are
    // read top to bottom, takeover modes are found by name.
    const reorder = this.handlers.canReorder === false ? [] : [
      btn('↑', 'Move up - higher modes win', '', () => this.handlers.onMoveUp?.()),
      btn('↓', 'Move down - lower modes win', '', () => this.handlers.onMoveDown?.()),
    ];
    return el('div', { className: 'mode-edit-head' }, [
      el('span', { className: 'fld-label', textContent: 'Name' }),
      name,
      this.activeEl,
      ...reorder,
      btn('✕', 'Delete mode', 'danger', () => this.handlers.onRemove?.()),
    ]);
  }

  // --- template picker (swaps the template body) ---------------------------

  _templatePicker() {
    const select = el('select', { className: 'inp' },
      TEMPLATES.map((t) => el('option', { value: t.type, textContent: t.label })));
    select.value = this.mode.template || TEMPLATES[0].type;

    this.templateBody = el('div', { className: 'tpl-body' });
    this._buildTemplateBody();

    select.addEventListener('change', () => {
      this._switchTemplate(select.value);
    });

    return el('div', { className: 'pick-row' }, [
      el('div', { className: 'pick-head' }, [
        el('span', { className: 'fld-label', textContent: 'What it does' }),
        select,
      ]),
      this.templateBody,
    ]);
  }

  // Replace template fields, then re-pin the activation to one this template
  // allows (clears + rebuilds the activation picker if it became invalid).
  // Switching to stopwatch/counter therefore re-pins activation to `manual`,
  // since `manual` is their only allowed activation.
  _switchTemplate(type) {
    const descriptor = TEMPLATE_BY_TYPE[type];
    if (!descriptor) return;
    // Strip old template-specific flat fields off the mode, keep core keys.
    for (const key of [...GESTURES.map((g) => g.key), 'unless_logged_today',
      'message', 'label', 'snooze_minutes', 'dismiss_event', 'log_as', 'event',
      // A Pomodoro's WORKING look means nothing on a stopwatch, and the Python
      // parser would warn that the mode does not own that state.
      'looks']) {
      delete this.mode[key];
    }
    this.mode.template = type;
    Object.assign(this.mode, descriptor.defaults());

    // Ensure the activation is compatible with the new template's nature.
    const allowed = descriptor.allowedActivations;
    const current = this.mode.activation?.type;
    if (!allowed.includes(current)) {
      this.mode.activation = ACTIVATION_BY_TYPE[allowed[0]].defaults();
    }
    this._build(); // full rebuild keeps validators + bodies in sync
    this._changed();
  }

  _buildTemplateBody() {
    clear(this.templateBody);
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template] || TEMPLATES[0];
    if (descriptor.body === 'actions') {
      this.templateBody.append(this._gestures(), this._unlessLogged());
    } else {
      const grid = el('div', { className: 'tpl-fields' });
      for (const spec of descriptor.fields) {
        const field = createField(spec, this.mode, () => this._changed(), this._fieldCtx());
        grid.append(field.el);
        this._validators.push(field.validate);
      }
      this.templateBody.append(grid);
    }
  }

  // --- activation picker (swaps the activation body) -----------------------

  _activationPicker() {
    const tplDescriptor = TEMPLATE_BY_TYPE[this.mode.template] || TEMPLATES[0];
    const allowed = new Set(tplDescriptor.allowedActivations);
    const select = el('select', { className: 'inp' },
      ACTIVATIONS.filter((a) => allowed.has(a.type))
        .map((a) => el('option', { value: a.type, textContent: a.label })));
    select.value = this.mode.activation?.type || tplDescriptor.allowedActivations[0];

    this.activationBody = el('div', { className: 'act-body' });
    this._buildActivationBody();

    select.addEventListener('change', () => {
      this.mode.activation = ACTIVATION_BY_TYPE[select.value].defaults();
      this._build();
      this._changed();
    });

    return el('div', { className: 'pick-row' }, [
      el('div', { className: 'pick-head' }, [
        el('span', { className: 'fld-label', textContent: "When it's on" }),
        select,
      ]),
      this.activationBody,
    ]);
  }

  _buildActivationBody() {
    clear(this.activationBody);
    const activation = this.mode.activation || {};
    if (activation.type === 'window') {
      this.activationBody.append(this._window(activation), this._days(activation));
    } else if (activation.type === 'schedule') {
      this.activationBody.append(this._scheduleTime(activation), this._days(activation));
    }
    // 'always' and 'manual' have no scope fields, so no body.
  }

  // window: optional [HH:MM, HH:MM] between range (may cross midnight).
  _window(activation) {
    const has = Array.isArray(activation.between);
    const toggle = el('input', { type: 'checkbox', checked: has });
    const start = el('input', { type: 'time', className: 'inp', value: has ? activation.between[0] : '' });
    const end = el('input', { type: 'time', className: 'inp', value: has ? activation.between[1] : '' });
    const err = el('span', { className: 'fld-err' });
    start.disabled = end.disabled = !has;

    const sync = () => {
      if (toggle.checked) activation.between = [start.value, end.value];
      else delete activation.between;
      start.disabled = end.disabled = !toggle.checked;
      this._changed();
    };
    toggle.addEventListener('change', sync);
    start.addEventListener('input', sync);
    end.addEventListener('input', sync);

    this._validators.push(() => {
      const bad = toggle.checked && (!start.value || !end.value);
      err.textContent = bad ? 'Set both times' : '';
      return bad ? 'time window needs a start and an end' : null;
    });

    return el('div', { className: 'scope-row' }, [
      el('label', { className: 'fld-check' }, [toggle, el('span', { textContent: 'Only between' })]),
      start, el('span', { className: 'sep', textContent: '-' }), end, err,
    ]);
  }

  // schedule: a single fire time (required).
  _scheduleTime(activation) {
    const input = el('input', { type: 'time', className: 'inp', value: activation.at || '' });
    const err = el('span', { className: 'fld-err' });
    input.addEventListener('input', () => {
      activation.at = input.value;
      this._changed();
    });
    this._validators.push(() => {
      const bad = !input.value;
      err.textContent = bad ? 'Set a time' : '';
      return bad ? 'a scheduled alarm needs a time' : null;
    });
    return el('div', { className: 'scope-row' }, [
      el('span', { className: 'scope-lbl', textContent: 'Fire at' }),
      input, err,
    ]);
  }

  // days: optional 3-letter weekday set, shared by window + schedule.
  _days(activation) {
    const chosen = new Set(Array.isArray(activation.days) ? activation.days : []);
    const row = el('div', { className: 'scope-row days-row' }, [
      el('span', { className: 'scope-lbl', textContent: 'On days' }),
    ]);
    for (const day of DAYS) {
      const cb = el('input', { type: 'checkbox', checked: chosen.has(day.key) });
      cb.addEventListener('change', () => {
        if (cb.checked) chosen.add(day.key);
        else chosen.delete(day.key);
        if (chosen.size) activation.days = DAYS.filter((d) => chosen.has(d.key)).map((d) => d.key);
        else delete activation.days;
        this._changed();
      });
      row.append(el('label', { className: 'day-pill' }, [cb, el('span', { textContent: day.label })]));
    }
    return row;
  }

  // --- actions template body: unless_logged_today + gesture sub-editor -----

  _unlessLogged() {
    const input = el('input', {
      type: 'text', className: 'inp',
      value: this.mode.unless_logged_today || '', placeholder: 'event name (optional)',
    });
    input.addEventListener('input', () => {
      const value = input.value.trim();
      if (value) this.mode.unless_logged_today = value;
      else delete this.mode.unless_logged_today;
      this._changed();
    });
    return el('div', { className: 'scope-row' }, [
      el('span', { className: 'scope-lbl', textContent: 'Skip if already logged today' }),
      input,
    ]);
  }

  _gestures() {
    const wrap = el('div', { className: 'gestures' });
    for (const gesture of GESTURES) wrap.append(this._gesture(gesture));
    return wrap;
  }

  _gesture(gesture) {
    const select = el('select', { className: 'inp' }, [
      el('option', { value: '', textContent: '- do nothing -' }),
      ...ACTIONS.map((a) => el('option', { value: a.type, textContent: a.label })),
    ]);
    select.value = this.mode[gesture.key]?.action || '';

    const fields = el('div', { className: 'gesture-fields' });
    // Held in a stable array so the registered validator below always reads
    // the fields currently shown, even after the action type is swapped.
    const fieldValidators = [];

    const buildFields = () => {
      clear(fields);
      fieldValidators.length = 0;
      const action = this.mode[gesture.key];
      const descriptor = action && ACTION_BY_TYPE[action.action];
      if (!descriptor) return;
      for (const spec of descriptor.fields) {
        // `rebuild` lets a widget that writes *sibling* keys (the integration
        // picker fills in url + payload) redraw the fields it overwrote.
        // Scoped to this gesture's own field set, so redrawing one action
        // never disturbs another gesture's half-typed input.
        const ctx = { ...this._fieldCtx(), rebuild: buildFields };
        const field = createField(spec, action, () => this._changed(), ctx);
        fields.append(field.el);
        fieldValidators.push(field.validate);
      }
    };

    select.addEventListener('change', () => {
      if (!select.value) delete this.mode[gesture.key];
      else this.mode[gesture.key] = ACTION_BY_TYPE[select.value].defaults();
      buildFields();
      this._changed();
    });

    this._validators.push(() => {
      for (const validate of fieldValidators) {
        const error = validate();
        if (error) return `${gesture.label}: ${error}`;
      }
      return null;
    });

    buildFields();
    return el('div', { className: 'gesture-row' }, [
      el('div', { className: 'gesture-head' }, [
        el('span', { className: 'gesture-name', textContent: gesture.label }),
        select,
      ]),
      fields,
    ]);
  }

  /** Run every field validator; returns an array of error strings (empty = ok). */
  validate() {
    return this._validators.map((v) => v()).filter(Boolean);
  }
}
