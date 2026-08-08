// Folds the side pane (virtual device, simulated presses, test clock) away
// from a toggle in the header, beside Tips.
//
// Everything in that pane is an inspection surface: someone driving a real
// button never presses the simulated ones, and on a short viewport the pane is
// most of the height. So it is worth reclaiming - but it is also where you go
// when the button is *not* connected, which is why this is a fold rather than
// a removal, and why the choice is remembered.
//
// Served-page only. The offline editor has no side pane at all (see
// tools/editor_shell.html), so this module is deliberately not in the editor
// bundle's entry list, and every lookup below tolerates its element being
// absent anyway.

import { readFlag, writeFlag } from './prefs.js';

const PANE_KEY = 'aibutton-side-collapsed';

const pane = document.querySelector('.app-body');
const paneBtn = document.getElementById('pane-toggle');

let folded = readFlag(PANE_KEY);

function applyPane() {
  pane?.classList.toggle('side-collapsed', folded);
  if (!paneBtn) return;
  // aria-expanded, not aria-pressed: this is a disclosure for the region named
  // by aria-controls, and "expanded" says which way it is without anyone
  // having to decide whether a *collapse* button is "pressed" when the pane is
  // gone.
  paneBtn.setAttribute('aria-expanded', String(!folded));
  paneBtn.textContent = folded ? '◧ Panel hidden' : '◧ Panel';
}

paneBtn?.addEventListener('click', () => {
  folded = !folded;
  writeFlag(PANE_KEY, folded);
  applyPane();
});

applyPane();
