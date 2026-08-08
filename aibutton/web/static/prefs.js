// Remembered view preferences - which chrome is showing, not what the button
// does. Nothing here ever reaches config.json: these are per-browser choices
// about how much of the page you want to look at, and losing them costs a
// click.
//
// The guards are the whole reason this is a module. localStorage *throws*
// rather than returning null in two situations this app actually meets:
// private browsing, and a page opened straight off the filesystem (the
// standalone editor, which has no origin to key storage against). Forgetting a
// preference is fine; taking the page down with it is not.

export function readFlag(key, fallback = false) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : raw === '1';
  } catch {
    return fallback;
  }
}

export function writeFlag(key, value) {
  try {
    localStorage.setItem(key, value ? '1' : '0');
  } catch { /* not remembered this session */ }
}
