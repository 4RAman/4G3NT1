// Pure registry tests for schema.js - no DOM needed, but the shared setup is
// harmless. Mirrors the Python parser contract in config.py.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  TEMPLATES, TEMPLATE_BY_TYPE, describeTemplate,
  ACTIONS, ACTION_BY_TYPE, describeAction,
  ACTIVATION_BY_TYPE, describeActivation,
} from '../aibutton/web/static/schema.js';

test('all five templates are registered', () => {
  const types = TEMPLATES.map((t) => t.type).sort();
  assert.deepEqual(types, ['actions', 'alarm', 'counter', 'pomodoro', 'stopwatch']);
});

test('takeover templates use manual activation only', () => {
  for (const type of ['stopwatch', 'counter', 'pomodoro']) {
    assert.deepEqual(TEMPLATE_BY_TYPE[type].allowedActivations, ['manual']);
  }
  assert.deepEqual(TEMPLATE_BY_TYPE.actions.allowedActivations, ['always', 'window']);
  assert.deepEqual(TEMPLATE_BY_TYPE.alarm.allowedActivations, ['schedule']);
});

test('counter defaults carry the three increments', () => {
  const d = TEMPLATE_BY_TYPE.counter.defaults();
  assert.equal(d.tap_increment, 1);
  assert.equal(d.long_increment, 10);
  assert.equal(d.double_increment, 20);
});

test('counter summary shows the increments', () => {
  const summary = describeTemplate({
    template: 'counter', event: 'water',
    tap_increment: 1, long_increment: 10, double_increment: 20,
  });
  assert.match(summary, /water/);
  assert.match(summary, /\+1\/\+10\/\+20/);
});

test('pomodoro defaults match the Python parser shape', () => {
  const d = TEMPLATE_BY_TYPE.pomodoro.defaults();
  assert.equal(d.work_minutes, 25);
  assert.equal(d.break_minutes, 5);
  assert.equal(d.extend_minutes, 10);
  assert.equal(d.log_as, 'pomodoro');
  assert.equal(d.short_press, 'start_pause');
  assert.equal(d.long_press, 'restart');
  assert.equal(d.double_tap, 'extend');
});

test('pomodoro summary reads as work/break minutes', () => {
  assert.equal(
    describeTemplate({ template: 'pomodoro', work_minutes: 25, break_minutes: 5 }),
    'Pomodoro 25/5 min',
  );
});

test('enter_mode lists takeover modes (incl. pomodoro), excludes alarm/actions', () => {
  const targetField = ACTION_BY_TYPE.enter_mode.fields.find((f) => f.key === 'target');
  const modes = [
    { name: 'Default', template: 'actions' },
    { name: 'Wake', template: 'alarm' },
    { name: 'Focus', template: 'stopwatch' },
    { name: 'Water', template: 'counter' },
    { name: 'Pom', template: 'pomodoro' },
  ];
  const options = targetField.options({ getModes: () => modes });
  assert.deepEqual(options.map((o) => o.value).sort(), ['Focus', 'Pom', 'Water']);
});

test('enter_mode options tolerate a missing getModes', () => {
  const targetField = ACTION_BY_TYPE.enter_mode.fields.find((f) => f.key === 'target');
  assert.deepEqual(targetField.options({}), []);
  assert.deepEqual(targetField.options(undefined), []);
});

test('activation registry + summaries', () => {
  assert.deepEqual(
    Object.keys(ACTIVATION_BY_TYPE).sort(),
    ['always', 'manual', 'schedule', 'window'],
  );
  assert.equal(describeActivation({ type: 'always' }), 'always');
  assert.equal(describeActivation({ type: 'schedule', at: '05:00' }), 'at 05:00');
  assert.match(
    describeActivation({ type: 'window', between: ['22:00', '06:00'] }),
    /22:00-06:00/,
  );
});

test('every action type round-trips through describeAction', () => {
  for (const a of ACTIONS) {
    const obj = a.defaults();
    assert.equal(typeof describeAction(obj), 'string');
  }
});
