// Renders and edits a single mode with one uniform, collapsible card:
//   name → template <select> (swaps the template body) →
//   activation <select> (swaps the activation body).
// Collapsed, it shows a one-line summary (template.describe +
// activation.describe); expand to edit. It composes its fields from the
// widget factory and its template/activation choices from the schema
// registries, so it knows nothing about specific template, activation,
// action, or field kinds (Dependency Inversion). It mutates the mode object
// in place and reports edits, moves, and removal through injected handlers -
// it does not own the modes list.

import { el, clear } from './dom.js';
import {
  GESTURES, DAYS, ACTIONS, ACTION_BY_TYPE,
  TEMPLATES, TEMPLATE_BY_TYPE, describeTemplate,
  ACTIVATIONS, ACTIVATION_BY_TYPE, describeActivation,
} from './schema.js';
import { createField } from './widgets.js';

export class ModeEditor {
  /**
   * @param {object} mode - the mode object (mutated in place)
   * @param {{onChange?: Function, onRemove?: Function,
   *          onMoveUp?: Function, onMoveDown?: Function}} handlers
   */
  constructor(mode, handlers = {}) {
    this.mode = mode;
    this.handlers = handlers;
    this._validators = []; // each returns an error string or null
    this.expanded = false;
    this.el = el('div', { className: 'mode-card' });
    this._build();
  }

  _changed() {
    this._refreshSummary();
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
    this.el.append(this._summaryHead(), this._body());
    this._applyExpanded();
  }

  // --- collapsed one-line summary -----------------------------------------

  _summaryHead() {
    this.toggle = el('button', {
      type: 'button', className: 'mode-toggle', title: 'Expand / collapse',
    });
    this.toggle.addEventListener('click', () => {
      this.expanded = !this.expanded;
      this._applyExpanded();
    });
    this.summaryEl = el('span', { className: 'mode-summary' });
    this._refreshSummary();
    return el('div', { className: 'mode-head' }, [this.toggle, this.summaryEl]);
  }

  _refreshSummary() {
    if (!this.summaryEl) return;
    clear(this.summaryEl);
    const name = this.mode.name || '(unnamed)';
    this.summaryEl.append(
      el('span', { className: 'mode-sum-name', textContent: name }),
      el('span', { className: 'mode-sum-sep', textContent: ' · ' }),
      el('span', { className: 'mode-sum-act', textContent: describeActivation(this.mode.activation) }),
      el('span', { className: 'mode-sum-sep', textContent: ' · ' }),
      el('span', { className: 'mode-sum-tpl', textContent: describeTemplate(this.mode) }),
    );
  }

  _applyExpanded() {
    if (this.toggle) this.toggle.textContent = this.expanded ? '▾' : '▸';
    if (this.bodyEl) this.bodyEl.hidden = !this.expanded;
    this.el.classList.toggle('expanded', this.expanded);
  }

  // --- expandable body -----------------------------------------------------

  _body() {
    this.bodyEl = el('div', { className: 'mode-body' });
    this.bodyEl.append(this._header(), this._templatePicker(), this._activationPicker());
    return this.bodyEl;
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

    const btn = (text, title, cls, fn) => {
      const b = el('button', { type: 'button', className: `mini ${cls}`, textContent: text, title });
      b.addEventListener('click', fn);
      return b;
    };
    return el('div', { className: 'mode-edit-head' }, [
      el('span', { className: 'fld-label', textContent: 'Name' }),
      name,
      btn('↑', 'Move up', '', () => this.handlers.onMoveUp?.()),
      btn('↓', 'Move down', '', () => this.handlers.onMoveDown?.()),
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
        el('span', { className: 'fld-label', textContent: 'Template' }),
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
      'message', 'label', 'snooze_minutes', 'dismiss_event', 'log_as', 'event']) {
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
        el('span', { className: 'fld-label', textContent: 'Activation' }),
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
        const field = createField(spec, action, () => this._changed(), this._fieldCtx());
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
