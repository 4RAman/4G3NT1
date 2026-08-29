// What sets a mode off (TODO 101), checked as a table.
//
// Run by tests/test_js_modules.py through `node --test`, which skips with a
// reason where node is absent. Only the pure half of schema.js is touched -
// `startedBy` takes data and returns a string, so the answer the nav paints is
// testable without a DOM, which is the whole reason it was written as a
// function over `reachableModes` rather than as branches inside `_navRow`.
//
// The case worth having tests at all for is `none`. An app nothing can reach
// is a bug in a config, it is invisible on the button, and until this glyph it
// was reported only in prose on a page you had to go and look at.

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  STARTERS, STARTER_BY_KEY, reachableModes, startedBy,
} from '../../aibutton/web/static/schema.js';

/** The scenario every case below draws from: one gesture map that launches a
 *  stopwatch, a second stopwatch only a reaction opens, a scheduled notice,
 *  and a metronome nothing points at. */
function world() {
  const modes = [
    {
      name: 'Main Menu', template: 'actions', activation: { type: 'always' },
      double_tap: { action: 'enter_mode', target: 'Mile Run' },
    },
    { name: 'Mile Run', template: 'stopwatch', activation: { type: 'manual' }, log_as: 'mile run' },
    { name: 'Commute', template: 'stopwatch', activation: { type: 'manual' }, log_as: 'commute' },
    {
      name: 'Good Morning', template: 'notice', urgent: true, message: 'up',
      activation: { type: 'schedule', at: '07:00' },
    },
    { name: 'Orphan', template: 'metronome', activation: { type: 'manual' }, start_bpm: 121 },
  ];
  const reflexes = [{ name: 'daw', then: { action: 'enter_mode', target: 'Commute' } }];
  return { modes, reflexes, reached: reachableModes(modes, {}, reflexes) };
}

const ask = (name) => {
  const { modes, reflexes, reached } = world();
  return startedBy(modes.find((m) => m.name === name), reached, {}, reflexes);
};

test('each mode reports the one thing that sets it off', () => {
  const table = [
    ['Main Menu', 'live'],      // a gesture map is never started; it listens
    ['Mile Run', 'press'],      // a double tap launches it
    ['Commute', 'reaction'],    // nothing presses to it; a reaction opens it
    ['Good Morning', 'clock'],  // a schedule, with nobody pressing anything
    ['Orphan', 'none'],         // configured, and unreachable
  ];
  for (const [name, expected] of table) assert.equal(ask(name), expected, name);
});

test('unreachable wins over every other answer', () => {
  // The order of the checks is the order of surprise, and this is the one that
  // has to come first: if nothing can reach a mode, nothing else about how it
  // would have started is true. A scheduled notice cannot hit this - a clock
  // makes it a root - so the case is built from a launcher nobody opens.
  const modes = [
    { name: 'Hidden menu', template: 'launcher', activation: { type: 'manual' }, targets: 'Deep' },
    { name: 'Deep', template: 'stopwatch', activation: { type: 'manual' }, log_as: 'deep' },
  ];
  const reached = reachableModes(modes, {}, []);
  assert.equal(startedBy(modes[0], reached, {}, []), 'none');
  // Transitive: a launcher you cannot open cannot open anything either.
  assert.equal(startedBy(modes[1], reached, {}, []), 'none');
});

test('a reaction that names a pooled action still counts as one', () => {
  // `then` may be a bare string naming the pool (config.resolve_action's
  // one-level rule). Resolving it here is what stops a pooled reaction from
  // reading as "nothing opens this".
  const modes = [{ name: 'Deep', template: 'stopwatch', activation: { type: 'manual' }, log_as: 'd' }];
  const actions = { 'open it': { action: 'enter_mode', target: 'Deep' } };
  const reflexes = [{ name: 'r', then: 'open it' }];
  const reached = reachableModes(modes, actions, reflexes);
  assert.equal(startedBy(modes[0], reached, actions, reflexes), 'reaction');
});

test('an unrecognised template is not classified at all', () => {
  // TODO 107: a fallback may degrade a capability, never invent a
  // classification. The nav gives these their own group; guessing a starter
  // would be the same invented answer one layer down.
  const mode = { name: 'From the future', template: 'holodeck', activation: { type: 'manual' } };
  assert.equal(startedBy(mode, new Set([mode]), {}, []), 'none');
});

test('every answer has a glyph entry, and only the live one draws nothing', () => {
  // The nav renders from this table rather than a switch, so a key with no row
  // would paint an empty column and read as "always listening" - the one
  // answer that is *meant* to be blank.
  const keys = ['live', 'clock', 'reaction', 'press', 'none'];
  assert.deepEqual(STARTERS.map((s) => s.key), keys);
  for (const key of keys) {
    assert.ok(STARTER_BY_KEY[key].title, `${key} needs a title`);
    assert.equal(STARTER_BY_KEY[key].glyph === '', key === 'live', key);
  }
});
