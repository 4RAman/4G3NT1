// How this page writes a duration and a logged number.
//
// One definition each, because both are shown in two places now: the Events
// table on the dashboard and an app's own readout on its page (TODO 51). Two
// copies of "how long is 3661 seconds" is a mirrored table with nothing
// testing it - the shape CLAUDE.md warns about - and the drift would show up
// as the same run reading as 1:01:01 in one panel and 61:01 in the other.

/** Seconds as `m:ss`, or `h:mm:ss` once there is an hour to show. Rounded to
 *  the second: the log stores float seconds and nothing here is a stopwatch
 *  display, so tenths would be precision the reader cannot use. */
export function fmtDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`;
}

/** A logged `value` as text. A whole number stays whole (a tally of 7, not
 *  "7.00"); anything else keeps enough to be worth having without pretending
 *  to precision the source had. */
export function fmtValue(v) {
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

/** A signed difference, for "this run against the one before it". The sign is
 *  always shown - an unsigned delta beside a time reads as another time. */
export function fmtDelta(seconds) {
  const sign = seconds < 0 ? '-' : '+';
  return `${sign}${fmtDuration(Math.abs(seconds))}`;
}

/** When a row happened, in the reader's own locale and timezone. `ts` is
 *  stored UTC (store.py says so); rendering it local is that module's stated
 *  half of the bargain. */
export function fmtWhen(ts) {
  return new Date(ts).toLocaleString([], {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/** Just the day, for a readout that groups by one. */
export function fmtDay(ts) {
  return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/**
 * `n` of a thing, pluralised.
 *
 * English's -es rule, which is the one that actually bites here: three of the
 * nouns an app readout declares end in a sibilant, and `noun + 's'` rendered
 * them "presss", "guesss" and "launchs" on screen. Adding a `plural` key to
 * every descriptor to fix three of them would be worse - a field twelve
 * templates fill in identically is a field nobody reads.
 *
 * Irregulars are not handled and none exists today. A template wanting one
 * should declare it rather than this growing a dictionary.
 */
export function plural(noun, n) {
  if (n === 1) return noun;
  return /(s|x|z|ch|sh)$/.test(noun) ? `${noun}es` : `${noun}s`;
}

/** "12 runs", "1 guess" - the count and its noun, which are always written
 *  together and were always being written apart. */
export function countOf(n, noun) {
  return `${n} ${plural(noun, n)}`;
}
