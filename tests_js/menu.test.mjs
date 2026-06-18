// ConfigMenu (menu.js): the permanent-Default normalization/locking and the
// "insert new modes above the floor" behaviour. Rendered against jsdom.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ConfigMenu } from '../aibutton/web/static/menu.js';
import { fire } from './setup.mjs';

function menuWith(modes) {
  const menu = new ConfigMenu(document.createElement('div'), {});
  menu.model = { modes };
  return menu;
}

test('_defaultIndex finds the last always-actions mode', () => {
  const menu = menuWith([
    { name: 'Night', template: 'actions', activation: { type: 'window', between: ['22:00', '23:00'] } },
    { name: 'Wake', template: 'alarm', activation: { type: 'schedule', at: '05:00' } },
    { name: 'Default', template: 'actions', activation: { type: 'always' } },
  ]);
  assert.equal(menu._defaultIndex(), 2);
});

test('_normalizeDefault appends a Default when none exists', () => {
  const menu = menuWith([
    { name: 'Wake', template: 'alarm', activation: { type: 'schedule', at: '05:00' } },
  ]);
  menu._normalizeDefault();
  const last = menu.model.modes.at(-1);
  assert.equal(last.template, 'actions');
  assert.equal(last.activation.type, 'always');
  assert.equal(menu.model.modes.length, 2);
});

test('_normalizeDefault pins an existing floor last', () => {
  const menu = menuWith([
    { name: 'Default', template: 'actions', activation: { type: 'always' },
      short_press: { action: 'prompt', prompt: 'hi', label: '' } },
    { name: 'Night', template: 'actions', activation: { type: 'window', between: ['22:00', '23:00'] },
      short_press: { action: 'log', event: 'x' } },
  ]);
  menu._normalizeDefault();
  assert.equal(menu.model.modes.at(-1).name, 'Default');
});

test('load() normalizes, then Add inserts above the floor', async () => {
  const api = {
    get: async () => ({
      effective: {
        modes: [
          { name: 'Morning', template: 'actions',
            activation: { type: 'window', between: ['05:00', '07:00'] },
            double_tap: { action: 'log', event: 'meds' } },
          { name: 'Default', template: 'actions', activation: { type: 'always' },
            short_press: { action: 'prompt', prompt: 'hi', label: '' } },
        ],
      },
      warnings: [],
    }),
  };
  const menu = new ConfigMenu(document.createElement('div'), api);
  await menu.load();

  assert.equal(menu.model.modes.at(-1).name, 'Default');
  assert.equal(menu._defaultIndex(), menu.model.modes.length - 1);

  const before = menu.model.modes.length;
  fire(menu.root.querySelector('.add-mode'), 'click');
  assert.equal(menu.model.modes.length, before + 1);
  // the floor is still last; the newcomer landed just above it
  assert.equal(menu.model.modes.at(-1).name, 'Default');
  assert.equal(menu.model.modes.at(-2).name, 'New mode');
});
