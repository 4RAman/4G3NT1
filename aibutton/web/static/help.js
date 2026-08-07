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

const KEY = 'aibutton-help';
let on = localStorage.getItem(KEY) === '1';

function apply() {
  document.querySelectorAll('[data-help]').forEach((node) => { node.hidden = !on; });
}

export function isHelpOn() {
  return on;
}

export function setHelpOn(next) {
  on = next;
  localStorage.setItem(KEY, on ? '1' : '0');
  apply();
  sync();
}

const btn = document.getElementById('help-toggle');

function sync() {
  if (!btn) return;
  btn.setAttribute('aria-pressed', String(on));
  btn.textContent = on ? 'ⓘ Tips on' : 'ⓘ Tips';
}

btn?.addEventListener('click', () => setHelpOn(!on));

new MutationObserver(apply).observe(document.documentElement, { childList: true, subtree: true });

apply();
sync();
