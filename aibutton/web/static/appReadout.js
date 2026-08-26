// What an app has actually done, on the app's own page (TODO 51).
//
// **A page, not a second brain.** Everything here is a *read*: rows out of the
// event store through /api/events, plus the mode's own config. Nothing it
// computes is written back, no new event kind or config key exists for its
// sake, and the button's behaviour does not depend on a byte of it. That is
// the line item 51 draws, and it is what keeps this a view rather than a
// second model of what the app is. If something here ever needs storing, that
// is item 34 (app documents), not this file.
//
// Which rows belong to an app is declared as data on the template descriptor
// (`readout` in schema.js) rather than branched on here, so an app grows a
// history by adding four keys - the Open/Closed rule the editor already
// follows for fields, actions and looks.
//
// Optional by construction, exactly like colorEngine's live preview: the
// offline editor's FileApi has no `events` and no service behind it, so there
// is simply no readout section there. A capability that required one would be
// the wrong seam.

import { el, clear } from './dom.js';
import {
  countOf, fmtDay, fmtDelta, fmtDuration, fmtValue, fmtWhen, plural,
} from './format.js';

// How many rows to ask the service for. Generous, because the window below is
// counted *after* the exact-name filter and a busy log can hold a lot of other
// apps' rows in between. Well under the endpoint's own 10,000 ceiling.
const FETCH_ROWS = 500;
// How much of it to show. One window for the list *and* the summary, so the
// two can never disagree - a "best" computed over 500 rows beside a list of 20
// is the kind of quiet mismatch nobody catches by looking.
const WINDOW_ROWS = 20;
const WINDOW_DAYS = 14;

/**
 * The rows this app owns, newest first.
 *
 * **The exact-name filter is here rather than in the query, deliberately.**
 * `/api/events?name=` is a substring match, because you search a log for
 * "coff" and expect "coffee" (store.py says so). That is right for a search
 * box and wrong for "this counter's rows": a counter called `water` would
 * quietly absorb `water_reminder`, and the total would be wrong in a way that
 * looks entirely plausible. So the query narrows and this makes it exact.
 */
async function fetchRows(api, { kind, name }) {
  const rows = await api.events({ kind, name, limit: FETCH_ROWS });
  return (rows || []).filter((r) => r.name === name);
}

/** The numbers a measure reads off a row, and how one of them is written. */
function reader(measure) {
  if (measure === 'duration') {
    return { of: (r) => r.duration_s, write: fmtDuration, delta: fmtDelta };
  }
  return {
    of: (r) => r.value,
    write: fmtValue,
    delta: (n) => `${n < 0 ? '-' : '+'}${fmtValue(Math.abs(n))}`,
  };
}

/** `12 runs · longest 8:41 · shortest 4:12 · average 6:03`, in the words the
 *  measure earns.
 *
 *  With no `better`, both ends are reported and neither is called best - a
 *  stopwatch does not know whether you wanted the long run or the short one,
 *  and picking for you would be the readout inventing an opinion. */
function summarise(numbers, { noun, unit, better, write }) {
  const unitOf = (n) => (unit ? `${write(n)} ${unit}` : write(n));
  const count = countOf(numbers.length, noun);
  if (numbers.length < 2) return count;
  const high = Math.max(...numbers);
  const low = Math.min(...numbers);
  const mean = numbers.reduce((a, b) => a + b, 0) / numbers.length;
  const ends = better === 'low' ? [`best ${unitOf(low)}`]
    : better === 'high' ? [`best ${unitOf(high)}`]
      : [`longest ${unitOf(high)}`, `shortest ${unitOf(low)}`];
  return [count, ...ends, `average ${unitOf(mean)}`].join(' · ');
}

/** One row: when it happened, a bar against the biggest in the window, the
 *  number, and how it compares with the one before it. The bar is what makes
 *  this a comparison rather than a list, which is what item 51 asked for. */
function measuredRow({ when, value, peak, best, delta, write, unit, better }) {
  const bar = el('span', { className: 'ro-bar' }, [
    el('span', {
      className: `ro-bar-fill${best ? ' best' : ''}`,
      // Never zero-width: a run of 0.4s against a peak of 40 minutes would
      // render as no bar at all, which reads as a missing row.
      style: `width: ${Math.max(2, peak > 0 ? (value / peak) * 100 : 0)}%`,
    }),
  ]);
  // Good or bad only where the app knows which is which. Without a `better`
  // the delta is still worth showing - it says the runs differ and by how
  // much - it just is not coloured as an achievement.
  const mood = delta == null || !better ? ''
    : (better === 'low') === (delta < 0) ? ' good' : ' bad';
  return el('div', { className: 'ro-row' }, [
    el('span', { className: 'ro-when', textContent: when }),
    bar,
    el('span', {
      className: 'ro-value',
      textContent: unit ? `${write(value)} ${unit}` : write(value),
    }),
    el('span', {
      className: `ro-delta${mood}`,
      textContent: delta == null ? '' : delta,
    }),
  ]);
}

/** duration / value: every session, newest first, compared against each other. */
function renderMeasured(rows, spec) {
  const { of, write, delta: writeDelta } = reader(spec.measure);
  const usable = rows.filter((r) => typeof of(r) === 'number');
  if (!usable.length) return [emptyNote(spec)];

  const window = usable.slice(0, WINDOW_ROWS);
  const numbers = window.map(of);
  const peak = Math.max(...numbers);
  const target = spec.better === 'low' ? Math.min(...numbers) : peak;

  const list = el('div', { className: 'ro-rows' });
  window.forEach((row, index) => {
    const value = of(row);
    // The next entry is the *previous* session: the list is newest first, so
    // "how did this compare with the one before it" reads forwards in time
    // while the page reads backwards. Nothing to compare the oldest with.
    const previous = index + 1 < window.length ? of(window[index + 1]) : null;
    list.append(measuredRow({
      when: fmtWhen(row.ts),
      value,
      peak,
      best: spec.better != null && value === target,
      delta: previous == null ? null : writeDelta(value - previous),
      write,
      unit: spec.unit,
      better: spec.better,
    }));
  });

  return [
    el('p', {
      className: 'ro-summary',
      textContent: summarise(numbers, { ...spec, write }),
    }),
    list,
    moreNote(usable.length, window.length, spec.noun),
  ];
}

/** tally: the rows are occurrences, so the number is how many a day held. */
function renderTally(rows, spec) {
  if (!rows.length) return [emptyNote(spec)];
  // Insertion order is preserved by Map, and the rows arrive newest first, so
  // the days come out newest first without a sort.
  const byDay = new Map();
  for (const row of rows) {
    const day = fmtDay(row.ts);
    byDay.set(day, (byDay.get(day) || 0) + 1);
  }
  const days = [...byDay.entries()].slice(0, WINDOW_DAYS);
  const counts = days.map(([, n]) => n);
  const peak = Math.max(...counts);
  const total = counts.reduce((a, b) => a + b, 0);
  const today = fmtDay(new Date().toISOString());

  const list = el('div', { className: 'ro-rows' });
  for (const [day, count] of days) {
    list.append(el('div', { className: `ro-row${day === today ? ' today' : ''}` }, [
      el('span', { className: 'ro-when', textContent: day === today ? 'today' : day }),
      el('span', { className: 'ro-bar' }, [
        el('span', {
          className: `ro-bar-fill${count === peak ? ' best' : ''}`,
          style: `width: ${Math.max(2, (count / peak) * 100)}%`,
        }),
      ]),
      el('span', { className: 'ro-value', textContent: String(count) }),
      el('span', { className: 'ro-delta' }),
    ]));
  }

  const many = (n) => countOf(n, spec.noun);
  const summary = [
    `${many(total)} over ${countOf(days.length, 'day')}`,
    `busiest ${many(peak)}`,
  ];
  return [
    el('p', { className: 'ro-summary', textContent: summary.join(' · ') }),
    list,
  ];
}

/** outcome: the value is one of two states, so it is counted, never averaged. */
function renderOutcome(rows, spec) {
  const usable = rows.filter((r) => typeof r.value === 'number');
  if (!usable.length) return [emptyNote(spec)];
  const window = usable.slice(0, WINDOW_ROWS);
  const states = spec.states || {};
  // The first state listed is the good one - `{1: 'answered', 0: 'no answer'}`
  // reads in that order for exactly this reason.
  const goodKey = Object.keys(states)[0];
  const good = window.filter((r) => String(r.value) === String(goodKey)).length;

  const list = el('div', { className: 'ro-rows' });
  for (const row of window) {
    const isGood = String(row.value) === String(goodKey);
    list.append(el('div', { className: 'ro-row' }, [
      el('span', { className: 'ro-when', textContent: fmtWhen(row.ts) }),
      el('span', {
        className: `ro-state${isGood ? ' good' : ' bad'}`,
        textContent: states[row.value] ?? fmtValue(row.value),
      }),
    ]));
  }

  return [
    el('p', {
      className: 'ro-summary',
      textContent: `${states[goodKey] || 'ok'} ${good} of the last ${window.length}`,
    }),
    list,
    moreNote(usable.length, window.length, spec.noun),
  ];
}

function emptyNote(spec) {
  return el('p', {
    className: 'empty',
    textContent: `No ${plural(spec.noun, 0)} logged yet under “${spec.name}”.`,
  });
}

/** Said only when it is true, and it is the sentence that stops the summary
 *  above being read as "all of it". */
function moreNote(total, shown, noun) {
  if (total <= shown) return null;
  return el('p', {
    className: 'ro-note',
    textContent: `Showing the last ${shown} of ${countOf(total, noun)} in the log.`,
  });
}

/**
 * The app's history, as a section for its own page.
 *
 * @param {object} mode - the mode being edited (read only - never mutated)
 * @param {object} descriptor - its template descriptor, for `readout`
 * @param {object} api - needs `events`; absent means no readout at all
 * @returns {{el: Element}|null} null when this app has no history to show
 */
export function createReadout(mode, descriptor, api) {
  const readout = descriptor?.readout;
  // Three separate "nothing to show" cases, and only the last is worth a word
  // on screen: no descriptor (this template does not log), no api (the offline
  // editor), and an empty name field (this copy is configured not to log).
  if (!readout || typeof api?.events !== 'function') return null;

  const name = String(mode[readout.nameField] || '').trim();
  const spec = { ...readout, name };
  const wrap = el('div', { className: 'readout' });
  const body = el('div', { className: 'ro-body' });

  if (!name) {
    // A real answer rather than a blank space: the field that would give this
    // app a history is optional and sitting further down the same page.
    wrap.append(el('p', {
      className: 'ro-note',
      textContent: 'This one logs nothing, so there is no history to show. '
        + 'Fill in its event name below and it will start keeping one.',
    }));
    return { el: wrap };
  }

  const refresh = el('button', {
    type: 'button', className: 'mini', textContent: 'Refresh',
    onclick: () => load(),
  });

  const load = async () => {
    clear(body);
    body.append(el('p', { className: 'empty', textContent: 'Reading the log…' }));
    try {
      const rows = await fetchRows(api, { kind: readout.kind, name });
      clear(body);
      const parts = readout.measure === 'tally' ? renderTally(rows, spec)
        : readout.measure === 'outcome' ? renderOutcome(rows, spec)
          : renderMeasured(rows, spec);
      for (const part of parts) if (part) body.append(part);
    } catch (err) {
      clear(body);
      body.append(el('p', {
        className: 'ro-note err',
        textContent: `Could not read the log: ${err.message}`,
      }));
    }
  };

  wrap.append(
    el('div', { className: 'ro-head' }, [
      el('span', { className: 'ro-title', textContent: headTitle(readout, name) }),
      refresh,
    ]),
    body,
  );
  // Fetched once, when the page opens, and again on demand.
  //
  // **Deliberately not polled.** The Events panel one click away already polls
  // for anyone watching the log live, and a timer here would outlive its own
  // section: the mode editor is rebuilt on every selection and every template
  // switch, so each visit to an app page would leave another interval running
  // against a detached node. Arriving at the page is what makes this current,
  // and arriving is what people do.
  load();
  return { el: wrap };
}

/** The head names the event as well as the noun, and that is not decoration:
 *  the field it comes from is editable further down this same page, so a
 *  rename leaves the rows below describing the *old* name until the next
 *  fetch. Saying which name they are keeps that honest instead of silent. */
function headTitle(readout, name) {
  const noun = readout.noun;
  const many = plural(noun, 0);
  const what = readout.measure === 'tally' ? `Recent ${many}, by day` : `Recent ${many}`;
  return `${what} · ${name}`;
}
