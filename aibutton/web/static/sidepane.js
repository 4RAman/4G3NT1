// The test panel: the virtual device, a way to press the button, its tones and
// its test clock, shown from a toggle in the header beside Tips.
//
// Everything in it is an inspection surface - someone driving a real button
// opens it to check something and closes it again - and as a permanent column
// it cost a third of the screen on a phone and a quarter on a laptop. So it is
// a popover, and the column it used to occupy is now the app's navigation
// (TODO 45).
//
// Deliberately *not* remembered between loads, unlike Tips and the volume:
// "only appears when you ask for it" is the whole point, and a popover that
// restored itself over the nav on every reload would be the column again with
// extra steps.
//
// Served-page only. The offline editor has no test panel at all (see
// tools/editor_shell.html), so this module is not in the editor bundle's entry
// list, and every lookup below tolerates its element being absent anyway.

const pop = document.getElementById('dash-pop');
const popBtn = document.getElementById('pane-toggle');

function setOpen(open) {
  if (!pop) return;
  pop.hidden = !open;
  popBtn?.setAttribute('aria-expanded', String(open));
}

popBtn?.addEventListener('click', (e) => {
  e.stopPropagation();  // or the document listener below closes it again
  setOpen(pop?.hidden ?? false);
});

// Clicking away closes it. The panel's own clicks are excluded rather than the
// document listener being skipped while it is open: pressing the simulated
// button four times in a row has to keep it up, and that is the main thing
// anyone does in here.
document.addEventListener('click', (e) => {
  if (!pop || pop.hidden) return;
  if (pop.contains(e.target) || popBtn?.contains(e.target)) return;
  setOpen(false);
});

// Escape closes it and hands focus back to the control that opened it, so a
// keyboard is never left pointing at something that is no longer on screen.
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !pop || pop.hidden) return;
  setOpen(false);
  popBtn?.focus();
});

setOpen(false);
