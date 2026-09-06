// What the App page says about the button running with nobody connected
// (TODO 111), checked as a table.
//
// Run by tests/test_js_modules.py through `node --test`, skipped where node is
// absent. `standaloneVerdict` answers with a state rather than a sentence -
// schema.js is the data module and holds no format.js import - so this pins
// which state each answer from `/api/app` lands in, and the wording is the
// page's problem.
//
// The order of the questions is the whole content of this function, and it is
// what the cases below are really about: a firmware that cannot run apps is
// told so *before* being told its package is out of date, because the second
// sentence would be nonsense on a button that can never hold one.

import assert from 'node:assert/strict';
import test from 'node:test';

import { standaloneVerdict } from '../../aibutton/web/static/schema.js';

/** A buildable, supported, up-to-date answer - the happy shape, to vary. */
const OK = {
  supported: true, buildable: true, bytes: 180,
  wanted_crc: 0x1234, installed_crc: 0x1234, current: true,
  menu: 'Home', apps: ['Home', 'Light show'], dropped: [], skipped: [],
};

test('installed and matching is the only "current"', () => {
  assert.equal(standaloneVerdict(OK).state, 'current');
  assert.equal(standaloneVerdict(OK).bytes, 180);
});

test('a package that is not what this config makes now is stale', () => {
  // The reason the endpoint exists: the button keeps doing the old thing
  // whenever the host is away, and nothing on screen used to say so.
  const stale = { ...OK, installed_crc: 0x9999, current: false };
  assert.equal(standaloneVerdict(stale).state, 'stale');
});

test('nothing installed is its own state, not a stale one', () => {
  // "Out of date" would be wrong and worse than wrong: it implies there is
  // something on the button to be out of date.
  //
  // **0 is what a bare board actually reports**, not null - the firmware
  // starts its package CRC at zero and stays there with no `app.pkg` on
  // flash. Reading that as a checksum is how a never-flashed button would
  // have shown up as merely "out of date".
  for (const installed_crc of [0, null, undefined]) {
    const empty = { ...OK, installed_crc, current: false };
    assert.equal(standaloneVerdict(empty).state, 'empty', String(installed_crc));
  }
});

test('a firmware that cannot run apps is told that first', () => {
  // Asked before staleness on purpose. A button with no CAP_APP reports no
  // package, which would otherwise read as "nothing installed" and invite an
  // Install button that cannot work.
  const old = { ...OK, supported: false, installed_crc: null, current: false };
  assert.equal(standaloneVerdict(old).state, 'unsupported');
  // And it still says whether there would have been anything to install.
  assert.equal(standaloneVerdict(old).buildable, true);
});

test('a config with nothing compilable says why, not how many bytes', () => {
  const nothing = { supported: true, buildable: false, why: 'nothing in this config compiles yet' };
  const verdict = standaloneVerdict(nothing);
  assert.equal(verdict.state, 'unbuildable');
  assert.equal(verdict.why, 'nothing in this config compiles yet');
  assert.equal(verdict.bytes, undefined);
});

test('not having asked yet is silence, not a state', () => {
  // What the section gets before the fetch lands, and forever in the offline
  // editor - there is no button there to ask.
  assert.equal(standaloneVerdict(null), null);
  assert.equal(standaloneVerdict(undefined), null);
});
