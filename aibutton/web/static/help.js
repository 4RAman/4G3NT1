// A single global "Tips" toggle for every bit of explanatory copy on the
// page. Content marked [data-help] is tutorial, not a control - hidden by
// default so the interface reads as short labels, shown on request. One
// switch rather than a per-element expand/collapse: flip it once and every
// hint, blurb and primer follows, including inside panels menu.js hasn't
// rendered yet.
//
// menu.js and modeEditor.js rebuild subtrees constantly (template switches,
// style switches, mode selection), so a MutationObserver reapplying on every
// DOM change is simpler and more robust than threading an "apply help state"
// call through each render path.
//
// Tinker mode (TODO 14) lives in this same file rather than one of its own:
// it is built from the identical three parts - a localStorage flag, the same
// MutationObserver, a header button - and a second file would only be that
// machinery copied once more. They are still two independent axes, not one
// "beginner mode": Tips is explain/don't explain (`[data-help]`), Tinker is
// show/hide surface (`[data-tier="tinker"]`, set by widgets.js from a
// field's `tier` in schema.js). Each gets its own key, so turning one on
// says nothing about the other - a basic user with Tips on gets a short,
// fully explained form, not a beginner/expert split.

import { readFlag, writeFlag } from './prefs.js';
import { el } from './dom.js';

const KEY = 'aibutton-help';
const TINKER_KEY = 'aibutton-tinker';

let on = readFlag(KEY);
let tinkerOn = readFlag(TINKER_KEY);

function apply() {
  document.querySelectorAll('[data-help]').forEach((node) => { node.hidden = !on; });
  document.querySelectorAll('[data-tier="tinker"]').forEach((node) => { node.hidden = !tinkerOn; });
}


export function setHelpOn(next) {
  on = next;
  writeFlag(KEY, on);
  apply();
  sync();
}

export function setTinkerOn(next) {
  tinkerOn = next;
  writeFlag(TINKER_KEY, tinkerOn);
  apply();
  syncTinker();
}

const btn = document.getElementById('help-toggle');

function sync() {
  if (!btn) return;
  btn.setAttribute('aria-pressed', String(on));
  btn.textContent = on ? 'ⓘ Tips on' : 'ⓘ Tips';
}

btn?.addEventListener('click', () => setHelpOn(!on));

// Tinker has no static markup of its own (unlike help-toggle/pane-toggle):
// this module is shared by the served page's `.header-tools` cluster and the
// offline editor's bare header row (tools/editor_shell.html has just Tips),
// and building the button here - right after Tips, in Tips's own parent -
// lands it correctly in both without this file needing to know which shell
// it is in. No Tips button on the page at all (should never happen) simply
// means no Tinker button either, the same graceful absence every other
// lookup in this file already tolerates.
let tinkerBtn = null;
if (btn?.parentElement) {
  tinkerBtn = el('button', {
    type: 'button', id: 'tinker-toggle', className: 'help-toggle', 'aria-pressed': 'false',
  });
  // `.header-tools > button { margin-left: 0 }` already keeps the served
  // page's cluster tight, but the offline editor's Tips button sits bare in
  // `.header-row` with its own margin-left: auto - two adjacent auto margins
  // would split the free space and shove Tinker away from Tips instead of
  // beside it. Zeroing it inline here is one rule that is correct in both
  // shells, without touching either one's stylesheet.
  tinkerBtn.style.marginLeft = '0';
  btn.after(tinkerBtn);
}

function syncTinker() {
  if (!tinkerBtn) return;
  tinkerBtn.setAttribute('aria-pressed', String(tinkerOn));
  tinkerBtn.textContent = tinkerOn ? '⚙ Tinker on' : '⚙ Tinker';
}

tinkerBtn?.addEventListener('click', () => setTinkerOn(!tinkerOn));

new MutationObserver(apply).observe(document.documentElement, { childList: true, subtree: true });

apply();
sync();
syncTinker();
