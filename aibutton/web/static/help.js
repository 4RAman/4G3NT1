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

// Storage can throw rather than return null - private browsing, and a page
// opened straight off the filesystem (the standalone editor). Losing the
// preference is fine; taking the rest of the page down with it is not.
function remembered() {
  try {
    return localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

function remember(value) {
  try {
    localStorage.setItem(KEY, value ? '1' : '0');
  } catch { /* not remembered this session */ }
}

let on = remembered();

function apply() {
  document.querySelectorAll('[data-help]').forEach((node) => { node.hidden = !on; });
}

export function isHelpOn() {
  return on;
}

export function setHelpOn(next) {
  on = next;
  remember(on);
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
