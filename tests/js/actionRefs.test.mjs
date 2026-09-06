// Where a pooled action is used (TODO 102), checked as a table.
//
// Run by tests/test_js_modules.py through `node --test`, skipped where node is
// absent. `actionRefs` is pure - config in, slots out - which is the only
// reason the *rename* it drives can be tested at all.
//
// The case worth the file: the editor's rename used to walk a hand-written
// list of places (gestures, and a signal light's positions) and quietly missed
// four more. Renaming a pooled action from the editor could dangle exactly the
// references the parser then warned about, which reads to a user as the rename
// having half worked. So the list of usages and the list of things to rewrite
// are one list, and this pins every slot kind in it.

import assert from 'node:assert/strict';
import test from 'node:test';

import { actionRefs, actionUsedBy } from '../../aibutton/web/static/schema.js';

/** One config touching every kind of slot a binding can live in. */
function world() {
  const modes = [
    {
      name: 'Home', template: 'actions',
      short_press: 'ping',                                  // a gesture
      triple_tap: { action: 'log', event: 'x' },            // inline, not a reference
    },
    {
      name: 'Wake', template: 'notice',
      on_enter: 'ping',                                     // a mode hook
      on_missed: 'ping',                                    // a template `bindings` entry
      short_press: { action: 'sequence', steps: ['ping', { action: 'log', event: 'y' }] },
    },
    {
      name: 'Status', template: 'signal',
      states: [{ name: 'Busy', action: 'ping' }],            // a signal position
    },
  ];
  const reflexes = [{ name: 'daw', then: 'ping' }];          // a reaction
  const pool = {
    ping: { action: 'log', event: 'p' },
    chain: { action: 'sequence', steps: ['ping'] },          // a pooled sequence's step
  };
  return { modes, reflexes, pool };
}

test('every kind of slot that can hold a name is found', () => {
  const { modes, reflexes, pool } = world();
  assert.deepEqual(actionUsedBy('ping', modes, reflexes, pool), [
    'Short press on Home',
    'Short press on Wake, step 1',
    'When it starts on Wake',
    'If nobody answers on Wake',
    'Busy in Status',
    'the reaction “daw”',
    '“chain”, step 1',
  ]);
});

test('renaming through the walk leaves nothing behind', () => {
  // This is exactly what the editor does on a rename, and the assertion is the
  // one that used to fail silently: not "the new name is somewhere" but "the
  // old name is nowhere".
  const { modes, reflexes, pool } = world();
  const before = actionUsedBy('ping', modes, reflexes, pool).length;
  for (const ref of actionRefs(modes, reflexes, pool)) {
    if (ref.owner[ref.key] === 'ping') ref.owner[ref.key] = 'pong';
  }
  assert.deepEqual(actionUsedBy('ping', modes, reflexes, pool), []);
  assert.equal(actionUsedBy('pong', modes, reflexes, pool).length, before);
});

test('an inline action is never a usage, however alike it looks', () => {
  // The pool exists to draw exactly this line: a bare string is a reference,
  // an object is this gesture's own copy. Counting the second would make
  // "editing this changes it everywhere" a lie in the safe direction.
  const modes = [{ name: 'Home', template: 'actions', short_press: { action: 'log', event: 'ping' } }];
  assert.deepEqual(actionUsedBy('ping', modes, [], {}), []);
});

test('an unused pool entry reports nothing rather than throwing', () => {
  const { modes, reflexes, pool } = world();
  assert.deepEqual(actionUsedBy('never-referenced', modes, reflexes, pool), []);
});

test('a config full of holes is walked without crashing', () => {
  // The editor calls this mid-edit, on half-built modes: an unnamed mode, a
  // template it has no descriptor for, a null in a list. None of those is an
  // error here - the walk is a reader.
  const modes = [null, {}, { name: 'x', template: 'holodeck', short_press: 'ping' },
    { name: 'y', template: 'signal', states: [null, { action: 'ping' }] }];
  assert.deepEqual(actionUsedBy('ping', modes, [null], {}), [
    'Short press on x', 'a position in y',
  ]);
});
