// Field factory (widgets.js) - each widget binds to a target object, parses
// its own input, and reports validation. Exercised against jsdom.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createField } from '../aibutton/web/static/widgets.js';
import { fire } from './setup.mjs';

function inputOf(field, selector = 'input, textarea, select') {
  return field.el.querySelector(selector);
}

test('text widget writes back on input and validates required', () => {
  const obj = {};
  const field = createField({ key: 'event', label: 'Event', kind: 'text', required: true }, obj, () => {});
  assert.equal(field.validate(), 'Event is required');
  const input = inputOf(field);
  input.value = 'water';
  fire(input, 'input');
  assert.equal(obj.event, 'water');
  assert.equal(field.validate(), null);
});

test('number widget coerces to Number and enforces min', () => {
  const obj = { n: 0 };
  const field = createField({ key: 'n', label: 'N', kind: 'number', min: 1 }, obj, () => {});
  const input = inputOf(field);
  input.value = '0';
  fire(input, 'input');
  assert.equal(obj.n, 0);
  assert.equal(field.validate(), 'N must be ≥ 1');
  input.value = '5';
  fire(input, 'input');
  assert.equal(obj.n, 5);
  assert.equal(field.validate(), null);
});

test('select widget with static options sets the value', () => {
  const obj = { cmd: 'restart' };
  const field = createField({
    key: 'cmd', label: 'Cmd', kind: 'select',
    options: [{ value: 'start_pause', label: 'Start' }, { value: 'restart', label: 'Restart' }],
  }, obj, () => {});
  const select = inputOf(field);
  assert.equal(select.value, 'restart'); // reflects current value
  select.value = 'start_pause';
  fire(select, 'change');
  assert.equal(obj.cmd, 'start_pause');
});

test('select flags a value that is no longer an option (stale enter_mode target)', () => {
  const obj = { target: 'Focus' };
  let modes = [{ value: 'Focus', label: 'Focus' }];
  const field = createField({
    key: 'target', label: 'Mode to enter', kind: 'select', required: true,
    options: () => modes,
  }, obj, () => {});
  assert.equal(field.validate(), null);             // Focus is a current option
  modes = [{ value: 'Water', label: 'Water' }];     // Focus renamed/deleted
  assert.match(field.validate(), /no longer available/);
  obj.target = '';
  assert.match(field.validate(), /required/i);       // empty required still caught
});

test('select widget supports dynamic options via ctx', () => {
  const obj = {};
  const field = createField({
    key: 'target', label: 'Target', kind: 'select',
    options: (ctx) => ctx.getModes().map((m) => ({ value: m, label: m })),
  }, obj, () => {}, { getModes: () => ['Focus', 'Water'] });
  const labels = [...inputOf(field).options].map((o) => o.value);
  assert.deepEqual(labels, ['Focus', 'Water']);
});

test('checkbox widget toggles a boolean', () => {
  const obj = { on: false };
  const field = createField({ key: 'on', label: 'On', kind: 'checkbox' }, obj, () => {});
  const box = inputOf(field);
  box.checked = true;
  fire(box, 'change');
  assert.equal(obj.on, true);
});

test('json widget parses an object and rejects non-objects', () => {
  const obj = {};
  const field = createField({ key: 'payload', label: 'Payload', kind: 'json' }, obj, () => {});
  const ta = inputOf(field, 'textarea');
  ta.value = '{"a": 1}';
  fire(ta, 'input');
  assert.deepEqual(obj.payload, { a: 1 });
  assert.equal(field.validate(), null);
  ta.value = '[1, 2]';
  fire(ta, 'input');
  assert.match(field.validate(), /invalid JSON/);
});
