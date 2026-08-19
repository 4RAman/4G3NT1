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

// Same guards, for a preference that is a number rather than a flag. Anything
// unparseable falls back rather than propagating NaN into a volume, where it
// would silence the page in a way no control could undo.
export function readNumber(key, fallback, { min = -Infinity, max = Infinity } = {}) {
  try {
    const value = Number(localStorage.getItem(key));
    if (!Number.isFinite(value)) return fallback;
    return Math.min(max, Math.max(min, value));
  } catch {
    return fallback;
  }
}

export function writeNumber(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch { /* not remembered this session */ }
}
