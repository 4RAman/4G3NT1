// ModeEditor (modeEditor.js): template/activation switching, the locked
// permanent Default, and validation. Rendered against jsdom.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ModeEditor } from '../aibutton/web/static/modeEditor.js';

function actionsMode() {
  return {
    name: 'X', template: 'actions', activation: { type: 'always' },
    short_press: { action: 'prompt', prompt: 'hi', label: '' },
    unless_logged_today: 'meds',
  };
}

test('switching actions -> counter strips old fields and applies defaults', () => {
  const mode = actionsMode();
  const editor = new ModeEditor(mode, {});
  editor._switchTemplate('counter');
  assert.equal(mode.template, 'counter');
  assert.equal(mode.short_press, undefined);          // gesture action stripped
  assert.equal(mode.unless_logged_today, undefined);  // actions-only field stripped
  assert.equal(mode.event, '');                       // counter defaults applied
  assert.equal(mode.tap_increment, 1);
  assert.equal(mode.long_increment, 10);
  assert.equal(mode.double_increment, 20);
  assert.deepEqual(mode.activation, { type: 'manual' }); // re-pinned to manual
});

test('switching to pomodoro applies its flat fields and gesture commands', () => {
  const mode = actionsMode();
  const editor = new ModeEditor(mode, {});
  editor._switchTemplate('pomodoro');
  assert.equal(mode.template, 'pomodoro');
  assert.equal(mode.work_minutes, 25);
  assert.equal(mode.break_minutes, 5);
  assert.equal(mode.extend_minutes, 10);
  assert.equal(mode.log_as, 'pomodoro');
  assert.equal(mode.short_press, 'start_pause'); // a command string, not an action object
});

test('the unlocked editor renders a delete button', () => {
  const editor = new ModeEditor(actionsMode(), {});
  assert.equal(editor.el.querySelectorAll('.mini.danger').length, 1);
  assert.equal(editor.el.querySelector('.mode-lock-tag'), null);
});

test('the locked Default hides delete and pins activation to Always', () => {
  const mode = { name: 'Default', template: 'actions', activation: { type: 'always' },
    short_press: { action: 'prompt', prompt: 'hi', label: '' } };
  const editor = new ModeEditor(mode, { locked: true });
  // no delete button, a "Permanent" tag instead
  assert.equal(editor.el.querySelectorAll('.mini.danger').length, 0);
  assert.ok(editor.el.querySelector('.mode-lock-tag'));
  // an activation select locked to a single Always option
  const selects = [...editor.el.querySelectorAll('select')];
  const activation = selects.find((s) => s.disabled && s.value === 'always');
  assert.ok(activation, 'activation select should be disabled and Always');
  assert.equal(activation.options.length, 1);
});

test('validate() reports a missing required field', () => {
  const mode = { name: 'C', template: 'counter', activation: { type: 'manual' },
    event: '', tap_increment: 1, long_increment: 10, double_increment: 20 };
  const editor = new ModeEditor(mode, {});
  const errors = editor.validate();
  assert.ok(errors.some((e) => /required/i.test(e)), errors.join(' | '));
});
