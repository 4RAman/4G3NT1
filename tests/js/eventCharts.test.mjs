// The Events page's aggregations, checked against tables (TODO 53).
//
// Run by tests/test_js_modules.py through `node --test`, which is built in -
// no runner, no config, no dependency, and the Python suite skips the whole
// thing when node is absent. CLAUDE.md's no-new-dependencies rule is about
// what the *service* runs on; this is a dev tool that nothing ships with.
//
// Only the pure half of eventCharts.js is exercised. The drawing half needs a
// DOM and is checked in a browser, which is the honest split: every question
// worth getting wrong here - which rows count, which would double-count, what
// "today" means - is answered by a function over data.
//
// Importing the module is safe with no DOM: dom.js touches `document` inside
// its functions and never at module scope, so nothing runs on import.

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BUCKETS, DAYS, MAX_SERIES, TOP_N,
  durationTotals, eventCounts, heatGrid, hourCounts, kindCounts,
  lengthBuckets, localDay, modeCounts, perDayCounts, seriesByName, tally,
} from '../../aibutton/web/static/eventCharts.js';

import {
  countOf, fmtDay, fmtDelta, fmtDuration, fmtValue, plural,
} from '../../aibutton/web/static/format.js';

// Every noun an app readout declares (schema.js's `readout.noun`). Kept here
// as a list rather than parsed out of schema.js: the point is to pin the
// *words*, and three of them were rendering as "presss", "guesss" and
// "launchs" on screen before `plural` existed.
const READOUT_NOUNS = [
  'run', 'press', 'ring', 'clear', 'launch', 'session', 'block',
  'guess', 'attempt', 'change', 'cue',
];

/** A row, with only the fields a test cares about spelled out. */
function row(overrides = {}) {
  return {
    ts: '2026-08-25T12:00:00+00:00', kind: 'log', name: 'press',
    duration_s: null, mode: null, value: null, ...overrides,
  };
}

// --- localDay: the timezone trap -------------------------------------------

test('localDay reports the day on the wall clock, not the day in UTC', () => {
  // Built from the runtime's own offset rather than a hardcoded zone, so this
  // is a real difference wherever it runs. Two local instants on a known local
  // day, one just after midnight and one just before it: whichever way the
  // offset points, at least one of them falls on a different *UTC* day.
  const anchor = new Date(2026, 7, 25); // 25 Aug 2026, local
  const justAfterMidnight = new Date(2026, 7, 25, 0, 30);
  const justBeforeMidnight = new Date(2026, 7, 25, 23, 30);

  assert.equal(localDay(justAfterMidnight.toISOString()), '2026-08-25');
  assert.equal(localDay(justBeforeMidnight.toISOString()), '2026-08-25');

  if (anchor.getTimezoneOffset() !== 0) {
    // The bug this guards: `toISOString().slice(0, 10)` is the obvious
    // implementation and silently files evening events under tomorrow (or
    // morning ones under yesterday) for everyone not on UTC.
    const naive = [justAfterMidnight, justBeforeMidnight]
      .map((d) => d.toISOString().slice(0, 10));
    assert.ok(
      naive.some((day) => day !== '2026-08-25'),
      'expected at least one instant to sit on a different UTC day',
    );
  }
});

test('localDay zero-pads, so days sort lexically', () => {
  assert.equal(localDay(new Date(2026, 0, 5, 12).toISOString()), '2026-01-05');
});

// --- tally -----------------------------------------------------------------

test('tally counts by key, biggest first', () => {
  const rows = [row({ name: 'a' }), row({ name: 'b' }), row({ name: 'a' })];
  assert.deepEqual(tally(rows, (r) => r.name), [['a', 2], ['b', 1]]);
});

test('tally skips rows with no key rather than inventing one', () => {
  // A null `mode` is the normal case for an ambient press, and a bucket called
  // "null" at the top of a chart is worse than one row fewer.
  const rows = [row({ mode: null }), row({ mode: '' }), row({ mode: 'Focus' })];
  assert.deepEqual(tally(rows, (r) => r.mode), [['Focus', 1]]);
});

// --- perDayCounts ----------------------------------------------------------

test('perDayCounts runs oldest first, because it is read as time passing', () => {
  const rows = [
    row({ ts: new Date(2026, 7, 25, 9).toISOString() }),
    row({ ts: new Date(2026, 7, 23, 9).toISOString() }),
    row({ ts: new Date(2026, 7, 25, 10).toISOString() }),
  ];
  assert.deepEqual(perDayCounts(rows), [['2026-08-23', 1], ['2026-08-25', 2]]);
});

// --- kindCounts / hourCounts / heatGrid ------------------------------------

test('kindCounts is biggest first', () => {
  const rows = [
    row({ kind: 'log' }), row({ kind: 'mode_enter' }), row({ kind: 'log' }),
  ];
  assert.deepEqual(kindCounts(rows), [['log', 2], ['mode_enter', 1]]);
});

test('hourCounts always has 24 slots, including the empty ones', () => {
  const counts = hourCounts([row({ ts: new Date(2026, 7, 25, 14).toISOString() })]);
  assert.equal(counts.length, 24);
  assert.equal(counts[14], 1);
  // The gaps are the finding: "you never touch this before 9" is only visible
  // if the empty hours are present.
  assert.equal(counts.filter((n) => n === 0).length, 23);
});

test('heatGrid is 7 weekdays of 24 hours, Sunday first', () => {
  const when = new Date(2026, 7, 25, 14); // a Tuesday
  const grid = heatGrid([row({ ts: when.toISOString() })]);
  assert.equal(grid.length, 7);
  assert.equal(grid[0].length, 24);
  assert.equal(grid[when.getDay()][14], 1);
  assert.equal(DAYS[when.getDay()], 'Tue');
});

// --- durationTotals: the double-count guard --------------------------------

test('durationTotals ignores timer_stop rows, so a stopwatch is counted once', () => {
  // The bug this exists to prevent: a stopwatch session writes *both* a
  // timer_stop (the timer) and a mode_exit (the app session that contained
  // it). Summing both doubles exactly the app most likely to top this chart,
  // and the wrong answer looks entirely plausible.
  const rows = [
    row({ kind: 'mode_exit', name: 'Stopwatch', mode: 'Stopwatch', duration_s: 60 }),
    row({ kind: 'timer_stop', name: 'stopwatch', mode: 'Stopwatch', duration_s: 60 }),
  ];
  assert.deepEqual(durationTotals(rows), [['Stopwatch', 60]]);
});

test('durationTotals sums per mode, biggest first', () => {
  const rows = [
    row({ kind: 'mode_exit', mode: 'Focus', duration_s: 100 }),
    row({ kind: 'mode_exit', mode: 'Focus', duration_s: 50 }),
    row({ kind: 'mode_exit', mode: 'Timer', duration_s: 200 }),
  ];
  assert.deepEqual(durationTotals(rows), [['Timer', 200], ['Focus', 150]]);
});

test('durationTotals falls back to the row name when mode is missing', () => {
  const rows = [row({ kind: 'mode_exit', name: 'Focus', mode: null, duration_s: 30 })];
  assert.deepEqual(durationTotals(rows), [['Focus', 30]]);
});

test('durationTotals skips a mode_exit carrying no duration', () => {
  const rows = [row({ kind: 'mode_exit', mode: 'Focus', duration_s: null })];
  assert.deepEqual(durationTotals(rows), []);
});

// --- lengthBuckets ---------------------------------------------------------

test('lengthBuckets puts each session in exactly one bucket', () => {
  const rows = [1, 29.9, 30, 119, 120, 3599, 3600, 99999].map(
    (duration_s) => row({ kind: 'mode_exit', mode: 'x', duration_s }),
  );
  const counts = lengthBuckets(rows);
  assert.equal(counts.reduce((a, b) => a + b, 0), rows.length);
  // Boundaries are exclusive at the top: 30s is "30s-2m", not "< 30s".
  assert.equal(counts[0], 2);   // 1, 29.9
  assert.equal(counts[1], 2);   // 30, 119
  assert.equal(counts[BUCKETS.length - 1], 2); // 3600, 99999
});

test('lengthBuckets ignores anything that is not an app session', () => {
  const rows = [row({ kind: 'timer_stop', duration_s: 10 }), row({ kind: 'log' })];
  assert.deepEqual(lengthBuckets(rows), BUCKETS.map(() => 0));
});

// --- eventCounts / modeCounts ----------------------------------------------

test('eventCounts counts only log rows', () => {
  const rows = [
    row({ kind: 'log', name: 'coffee' }),
    row({ kind: 'log', name: 'coffee' }),
    row({ kind: 'mode_enter', name: 'coffee' }),
  ];
  assert.deepEqual(eventCounts(rows), [['coffee', 2]]);
});

test('modeCounts counts openings, which is not the same question as duration', () => {
  const rows = [
    row({ kind: 'mode_enter', name: 'Focus' }),
    row({ kind: 'mode_exit', name: 'Focus', duration_s: 3600 }),
  ];
  assert.deepEqual(modeCounts(rows), [['Focus', 1]]);
});

// --- seriesByName: the "value means different things" rule ------------------

test('seriesByName keeps each name apart, so unlike numbers never share an axis', () => {
  const rows = [
    row({ name: 'metronome', value: 120 }),
    row({ name: 'reaction', value: 214 }),
    row({ name: 'metronome', value: 96 }),
  ];
  const series = seriesByName(rows);
  assert.deepEqual(series.map(([name]) => name), ['metronome', 'reaction']);
  assert.equal(series[0][1].length, 2);
});

test('seriesByName drops rows with no value at all', () => {
  const rows = [row({ name: 'a', value: null }), row({ name: 'a', value: 5 })];
  assert.equal(seriesByName(rows)[0][1].length, 1);
});

test('seriesByName keeps zero, which is a value and not a missing one', () => {
  // An alarm logs 0 for "nobody answered" (item 44). A falsy check here would
  // silently delete every unanswered alarm from the chart.
  const rows = [row({ name: 'checkin', value: 0 }), row({ name: 'checkin', value: 1 })];
  assert.equal(seriesByName(rows)[0][1].length, 2);
});

test('seriesByName puts points in time order, though the rows arrive newest first', () => {
  const rows = [
    row({ name: 'a', value: 3, ts: '2026-08-25T12:00:00+00:00' }),
    row({ name: 'a', value: 1, ts: '2026-08-23T12:00:00+00:00' }),
  ];
  assert.deepEqual(seriesByName(rows)[0][1].map((p) => p.value), [1, 3]);
});

test('seriesByName does not reorder the caller rows', () => {
  const rows = [
    row({ name: 'a', value: 3, ts: '2026-08-25T12:00:00+00:00' }),
    row({ name: 'a', value: 1, ts: '2026-08-23T12:00:00+00:00' }),
  ];
  const before = rows.map((r) => r.value);
  seriesByName(rows);
  // The same array backs the table one tab away; sorting it in place would
  // silently reorder the log the moment you looked at a chart.
  assert.deepEqual(rows.map((r) => r.value), before);
});

test('seriesByName is busiest first, so a truncated page keeps the useful ones', () => {
  const rows = [
    row({ name: 'quiet', value: 1 }),
    row({ name: 'busy', value: 1 }),
    row({ name: 'busy', value: 2 }),
  ];
  assert.deepEqual(seriesByName(rows).map(([n]) => n), ['busy', 'quiet']);
});

// --- the limits are sane ---------------------------------------------------

test('the page limits are positive integers', () => {
  for (const limit of [TOP_N, MAX_SERIES]) {
    assert.ok(Number.isInteger(limit) && limit > 0);
  }
});

// --- format.js, shared by the log table and every app readout --------------

test('fmtDuration grows an hours field only when there is one', () => {
  assert.equal(fmtDuration(0), '0:00');
  assert.equal(fmtDuration(9), '0:09');
  assert.equal(fmtDuration(61), '1:01');
  assert.equal(fmtDuration(3600), '1:00:00');
  assert.equal(fmtDuration(3661), '1:01:01');
});

test('fmtDuration rounds to the second and never goes negative', () => {
  assert.equal(fmtDuration(59.6), '1:00');
  assert.equal(fmtDuration(-5), '0:00');
});

test('fmtValue keeps a whole number whole', () => {
  assert.equal(fmtValue(7), '7');
  assert.equal(fmtValue(0), '0');
  assert.equal(fmtValue(214.567), '214.57');
});

test('fmtDelta always carries its sign, so it cannot read as another time', () => {
  assert.equal(fmtDelta(62), '+1:02');
  assert.equal(fmtDelta(-62), '-1:02');
  assert.equal(fmtDelta(0), '+0:00');
});

test('plural gets the -es rule right, which is the one that bites here', () => {
  assert.equal(plural('press', 2), 'presses');
  assert.equal(plural('guess', 2), 'guesses');
  assert.equal(plural('launch', 2), 'launches');
  assert.equal(plural('run', 2), 'runs');
  assert.equal(plural('cue', 2), 'cues');
});

test('plural leaves a single one alone', () => {
  assert.equal(plural('press', 1), 'press');
  assert.equal(plural('run', 1), 'run');
});

test('plural treats zero as plural, because English does', () => {
  // "No presses logged yet", not "No press logged yet".
  assert.equal(plural('press', 0), 'presses');
});

test('every noun an app readout declares survives pluralisation', () => {
  for (const noun of READOUT_NOUNS) {
    const many = plural(noun, 2);
    assert.ok(!/[^aeiou]ss$|chs$|shs$|xs$/.test(many), `${noun} -> ${many}`);
    assert.notEqual(many, noun);
  }
});

test('countOf writes the number and the noun together', () => {
  assert.equal(countOf(1, 'run'), '1 run');
  assert.equal(countOf(12, 'run'), '12 runs');
  assert.equal(countOf(0, 'press'), '0 presses');
});

test('fmtDay renders the local day of a stored UTC instant', () => {
  const when = new Date(2026, 7, 25, 9);
  assert.equal(fmtDay(when.toISOString()), when.toLocaleDateString([], {
    month: 'short', day: 'numeric',
  }));
});
