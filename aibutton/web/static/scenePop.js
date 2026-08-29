// The scene picker's popover toggle (TODO 81) - the same open-on-ask,
// close-on-Escape-or-outside-click shape as the Test panel's (sidepane.js),
// because a scene switch is touched about as often as the bench is and does
// not deserve a permanent row above the tabs either.
//
// Served-page only, exactly like sidepane.js: the offline editor has no
// scenes at all (see tools/editor_shell.html), so this module is not in the
// editor bundle's entry list and every lookup here tolerates its element
// being absent regardless.

const pop = document.getElementById('scene-pop');
const popBtn = document.getElementById('scene-toggle');

function setOpen(open) {
  if (!pop) return;
  pop.hidden = !open;
  popBtn?.setAttribute('aria-expanded', String(open));
}

popBtn?.addEventListener('click', (e) => {
  e.stopPropagation();  // or the document listener below closes it again
  setOpen(pop?.hidden ?? false);
});

document.addEventListener('click', (e) => {
  if (!pop || pop.hidden) return;
  if (pop.contains(e.target) || popBtn?.contains(e.target)) return;
  setOpen(false);
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !pop || pop.hidden) return;
  setOpen(false);
  popBtn?.focus();
});

setOpen(false);
