// Field factory: turns one field spec (from schema.js) into a labeled form
// control bound to a target object. Each widget owns its own parsing and
// validation, and every widget returns the same shape -
//   { el: HTMLElement, validate: () => string | null }
// - so the mode editor and settings form can treat them uniformly
// (Liskov). New field kinds plug into WIDGETS without touching callers
// (Open/Closed).

import { el } from './dom.js';

function errLine() {
  return el('span', { className: 'fld-err' });
}

// Standard layout: label text above the control, optional hint + error below.
function wrap(spec, control, errEl) {
  return el('label', { className: 'fld' }, [
    el('span', { className: 'fld-label', textContent: spec.label }),
    control,
    spec.hint ? el('span', { className: 'fld-hint', textContent: spec.hint }) : null,
    errEl,
  ]);
}

function requiredError(spec, value) {
  return spec.required && !String(value ?? '').trim() ? `${spec.label} is required` : null;
}

function textInput(type, spec, obj, onInput) {
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
    el: wrap(spec, input, err),
    validate() {
      const msg = requiredError(spec, obj[spec.key]);
      err.textContent = msg ? 'Required' : '';
      return msg;
    },
  };
}

const WIDGETS = {
  text: (spec, obj, onInput) => textInput('text', spec, obj, onInput),

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

  number(spec, obj, onInput) {
    const input = el('input', { type: 'number', className: 'inp', value: obj[spec.key] ?? '' });
    if (spec.min != null) input.min = spec.min;
    if (spec.max != null) input.max = spec.max;
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
        else if (spec.min != null && value < spec.min) msg = `${spec.label} must be ≥ ${spec.min}`;
        else if (spec.max != null && value > spec.max) msg = `${spec.label} must be ≤ ${spec.max}`;
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

  checkbox(spec, obj, onInput) {
    const input = el('input', { type: 'checkbox', checked: !!obj[spec.key] });
    input.addEventListener('change', () => {
      obj[spec.key] = input.checked;
      onInput();
    });
    const node = el('label', { className: 'fld fld-check' }, [
      input,
      el('span', { className: 'fld-label', textContent: spec.label }),
      spec.hint ? el('span', { className: 'fld-hint', textContent: spec.hint }) : null,
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
