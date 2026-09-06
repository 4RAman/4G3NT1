// The live half of a nav row (TODO 101), checked as a table.
//
// Run by tests/test_js_modules.py through `node --test`, skipped where node is
// absent. `readoutStat` returns numbers rather than a sentence - schema.js is
// the data module and holds no format.js import - so this pins *which* numbers
// come out, and the wording is the caller's problem.
//
// The three cases that matter are all "say nothing": a template that logs
// nothing, a mode that never named its log, and a name the log has never seen.
// All three mean silence rather than a zero, because a nav row saying "0 runs"
// under an app you set up this morning reads as broken rather than as new.

import assert from 'node:assert/strict';
import test from 'node:test';

import { betterFor, readoutStat } from '../../aibutton/web/static/schema.js';

/** What `/api/events/summary` answers with, in its wire shape. */
const ROWS = [
  {
    kind: 'timer_stop', name: 'mile run', count: 12, last: '2026-08-20T10:00:00+00:00',
    duration_min: 477, duration_max: 1125, value_min: null, value_max: null,
  },
  {
    kind: 'log', name: 'quick', count: 30, last: '2026-08-28T10:00:00+00:00',
    duration_min: null, duration_max: null, value_min: 214, value_max: 900,
  },
  {
    kind: 'log', name: 'tempo', count: 5, last: '2026-08-29T10:00:00+00:00',
    duration_min: null, duration_max: null, value_min: 90, value_max: 160,
  },
];

test('a stopwatch reports how many and when, and no best', () => {
  // `better: null` on the descriptor, and that is a decision rather than a
  // gap: the same template times a mile run, where quicker is better, and a
  // cake, where it is not.
  const stat = readoutStat({ template: 'stopwatch', log_as: 'mile run' }, ROWS);
  assert.equal(stat.count, 12);
  assert.equal(stat.noun, 'run');
  assert.equal(stat.last, '2026-08-20T10:00:00+00:00');
  assert.equal(stat.best, null);
});

test('better: low takes the minimum, and says it is not a duration', () => {
  // A reaction timer measures milliseconds in `value`, not in `duration_s`,
  // so the caller must not format 214 as 3 minutes 34.
  const stat = readoutStat({ template: 'reaction', log_as: 'quick' }, ROWS);
  assert.equal(stat.best, 214);
  assert.equal(stat.unit, 'ms');
  assert.equal(stat.bestIsDuration, false);
});

test('better: high takes the maximum', () => {
  // Hot/Cold scores a percentage, where higher is the good end.
  const rows = [{
    kind: 'log', name: 'game', count: 4, last: '2026-08-29T10:00:00+00:00',
    duration_min: null, duration_max: null, value_min: 12, value_max: 97,
  }];
  assert.equal(readoutStat({ template: 'hotcold', log_as: 'game' }, rows).best, 97);
});

test('a unit with no better is carried but unused', () => {
  // A metronome declares BPM and declines a best - a tempo has no good end.
  const stat = readoutStat({ template: 'metronome', log_as: 'tempo' }, ROWS);
  assert.equal(stat.unit, 'BPM');
  assert.equal(stat.best, null);
});

test('the item can say which end is best, and the template is the fallback', () => {
  // TODO 109. "Mile Run" and "Cake" are the same template and the same
  // question with two different answers, which is the whole reason this is a
  // field on the item rather than a word on the descriptor.
  const run = readoutStat({ template: 'stopwatch', log_as: 'mile run', better: 'low' }, ROWS);
  assert.equal(run.best, 477);
  assert.equal(run.bestIsDuration, true);
  const high = readoutStat({ template: 'stopwatch', log_as: 'mile run', better: 'high' }, ROWS);
  assert.equal(high.best, 1125);
  // Anything that is not one of the two words leaves the template's answer
  // standing, which for a stopwatch is "nothing is best".
  for (const better of ['', 'quick', null, undefined]) {
    assert.equal(
      readoutStat({ template: 'stopwatch', log_as: 'mile run', better }, ROWS).best, null,
      String(better),
    );
  }
});

test('betterFor prefers the item, then the template, then nothing', () => {
  const descriptor = { better: 'low' };
  assert.equal(betterFor({ better: 'high' }, descriptor), 'high');
  // A template that *has* an opinion keeps it: absent means "you decide", not
  // "no best". This is the case that would need a third word to override.
  assert.equal(betterFor({}, descriptor), 'low');
  assert.equal(betterFor({ better: 'sideways' }, descriptor), 'low');
  assert.equal(betterFor(undefined, undefined), null);
});

test('three different kinds of nothing all report nothing', () => {
  const cases = [
    ['the log has never seen it', { template: 'stopwatch', log_as: 'never happened' }],
    ['the mode never named its log', { template: 'stopwatch', log_as: '' }],
    ['the template logs nothing', { template: 'launcher' }],
  ];
  for (const [why, mode] of cases) assert.equal(readoutStat(mode, ROWS), null, why);
});

test('no rows at all is silence, not a crash', () => {
  // What every row gets before the fetch lands, and what every row in the
  // offline editor gets forever - there is no service there to ask.
  const mode = { template: 'stopwatch', log_as: 'mile run' };
  assert.equal(readoutStat(mode, undefined), null);
  assert.equal(readoutStat(mode, []), null);
});

test('a row is matched on kind as well as name', () => {
  // `mode_exit` and `timer_stop` both exist for one stopwatch session and mean
  // different things (CLAUDE.md: taking both is how a duration chart
  // double-counts). The descriptor names which kind it reads.
  const rows = [{
    kind: 'mode_exit', name: 'mile run', count: 99, last: '2026-08-20T10:00:00+00:00',
    duration_min: 1, duration_max: 2, value_min: null, value_max: null,
  }];
  assert.equal(readoutStat({ template: 'stopwatch', log_as: 'mile run' }, rows), null);
});
