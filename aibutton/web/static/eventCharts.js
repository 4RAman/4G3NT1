// The Events page's chart views (TODO 53).
//
// **No charting library, and no build step.** Recharts and react-chartjs-2 are
// React; this app is vanilla ES modules and that is a deliberate property. So
// every chart here is hand-rolled - and mostly *not* in SVG, which is where
// this departs from the item's own recommendation and is worth a sentence.
//
// A bar chart in SVG has to size its own text, and text inside a viewBox
// scales with the box: an 11px label in a 640-wide viewBox is 6px on a phone,
// which fails the "nothing overflows at 375" bar by being unreadable rather
// than by overflowing. Flex and grid do bars, columns and a heatmap with real
// text that stays real text at every width. So SVG is kept for the two shapes
// CSS genuinely cannot draw - a donut arc and a scatter over time - and both
// of those keep their labels in HTML around the plot rather than inside it.
//
// **Aggregated here, not in Python.** The log is a few hundred rows. Adding
// endpoints would put the same grouping logic in two languages with nothing
// testing that they agree - a mirrored table of exactly the kind CLAUDE.md
// says to avoid growing.
//
// **The aggregations are pure and exported; the drawing is not.** Same split
// as rules.py and scheduler.py, for the same reason: every question worth
// getting wrong here (which rows count, which would double-count, what "today"
// means) lives in a function over data with no DOM in it, so it can be checked
// against a table. tests/js/eventCharts.test.mjs does exactly that; the
// renderers below are the I/O edge and are checked in a browser.
//
// **Served page only.** The offline editor has no service and therefore no
// events at all, so this module is deliberately absent from build_editor.py's
// entry list - the same seam sidepane.js sits on. That was the item's one
// genuinely open question and this comment is the answer: no.

import { el } from './dom.js';
import { fmtDuration } from './format.js';

export const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// Enough hues to tell a handful of categories apart, and no more: a chart
// needing a twentieth colour is a chart that should have been a table.
const SERIES = ['#4f8ef7', '#43b97f', '#e0a93e', '#e05c5c', '#a678e0', '#3fb6c4'];

// How many bars before a chart stops being readable and starts being wallpaper.
export const TOP_N = 10;
// How many separate value series to draw. Each gets its own axis (see
// `seriesByName`), so this is a page-length limit, not a data one.
export const MAX_SERIES = 6;

// ===========================================================================
// The pure half: rows in, numbers out. No DOM below this line until the
// renderers start.
// ===========================================================================

/**
 * The local calendar day a timestamp falls in, as `YYYY-MM-DD`.
 *
 * **Not `toISOString().slice(0, 10)`**, which is the obvious version and is
 * wrong: that is UTC, and "which day did I press this" is a question about the
 * wall clock in the room. Anyone an hour or more off UTC would see evening
 * events land on the next day - the same rule store.py's `_local_day_bounds_utc`
 * follows from the other side, and the reason `ts` is stored UTC and rendered
 * local rather than the reverse.
 */
export function localDay(ts) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    + `-${String(d.getDate()).padStart(2, '0')}`;
}

/** Count rows by some key, biggest first, skipping rows with none. */
export function tally(rows, keyOf) {
  const counts = new Map();
  for (const row of rows) {
    const key = keyOf(row);
    if (key == null || key === '') continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
}

/** [dayKey, count], **oldest first** - this one is read left to right as time
 *  passing, unlike every "most of X" chart here, which is read biggest first. */
export function perDayCounts(rows) {
  const counts = new Map();
  for (const row of rows) {
    const key = localDay(row.ts);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

/** [kind, count], biggest first. */
export function kindCounts(rows) {
  return tally(rows, (r) => r.kind);
}

/** 24 counts, indexed by local hour. Every hour is present, including the
 *  empty ones: the gaps are the shape of a day, and dropping them would turn
 *  "you never touch this before 9" into a chart that starts at 9. */
export function hourCounts(rows) {
  const counts = new Array(24).fill(0);
  for (const row of rows) counts[new Date(row.ts).getHours()] += 1;
  return counts;
}

/** 7 rows (Sunday first, matching `Date.getDay`) of 24 hourly counts. */
export function heatGrid(rows) {
  const grid = Array.from({ length: 7 }, () => new Array(24).fill(0));
  for (const row of rows) {
    const when = new Date(row.ts);
    grid[when.getDay()][when.getHours()] += 1;
  }
  return grid;
}

/**
 * [mode, total seconds], biggest first - **from `mode_exit` rows only**, and
 * that is the whole correctness of this chart.
 *
 * `timer_stop` rows also carry a duration and a mode, so a stopwatch session
 * is in the log twice: once as the timer and once as the app session that
 * contained it. Summing both double-counts exactly the app most likely to be
 * at the top of this chart, and the result looks entirely plausible. A
 * mode_exit row *is* the session, which is what "where does the time go" asks.
 */
export function durationTotals(rows) {
  const totals = new Map();
  for (const row of rows) {
    if (row.kind !== 'mode_exit' || typeof row.duration_s !== 'number') continue;
    const key = row.mode || row.name;
    if (!key) continue;
    totals.set(key, (totals.get(key) || 0) + row.duration_s);
  }
  return [...totals.entries()].sort((a, b) => b[1] - a[1]);
}

/** Fixed buckets rather than computed ones. A histogram that rescales its own
 *  bins as data arrives cannot be compared with the one you looked at
 *  yesterday, and these boundaries are ones a person already thinks in. */
export const BUCKETS = [
  ['< 30s', 30], ['30s-2m', 120], ['2-5m', 300], ['5-15m', 900],
  ['15-30m', 1800], ['30-60m', 3600], ['1h+', Infinity],
];

/** One count per bucket, over app sessions (`mode_exit`, same rows as
 *  `durationTotals` and for the same reason). */
export function lengthBuckets(rows) {
  const counts = BUCKETS.map(() => 0);
  for (const row of rows) {
    if (row.kind !== 'mode_exit' || typeof row.duration_s !== 'number') continue;
    counts[BUCKETS.findIndex(([, cap]) => row.duration_s < cap)] += 1;
  }
  return counts;
}

/**
 * [event name, count] over `log` rows, biggest first.
 *
 * The spec called this "top triggers", and this is the honest version of it:
 * **the log does not record which gesture fired.** A row knows what was logged
 * and which mode was active, never whether you got there by a double tap. So
 * this counts event names - the question the data can actually answer - and
 * the chart's title says that rather than implying the other.
 */
export function eventCounts(rows) {
  return tally(rows.filter((r) => r.kind === 'log'), (r) => r.name);
}

/** [app name, times opened] over `mode_enter` rows. A different question from
 *  `durationTotals`: an app you open twenty times for ten seconds and one you
 *  open once for an hour are both worth knowing, and neither chart shows the
 *  other. */
export function modeCounts(rows) {
  return tally(rows.filter((r) => r.kind === 'mode_enter'), (r) => r.name);
}

/**
 * [name, points oldest-first][], busiest series first.
 *
 * **Grouped by name, always.** `value` is a single untyped numeric slot
 * (store.py says so): a metronome's BPM, a reaction timer's milliseconds, a
 * countdown's minutes, and since item 44 an alarm's 0/1. Those share a column
 * and nothing else, so each name is its own series with its own scale, and the
 * only thing they share is the time axis. Pooling them would produce a chart
 * that renders, looks fine, and means nothing.
 *
 * Points come back in time order: the rows arrive newest first, which is right
 * for a table and backwards for a plot.
 */
export function seriesByName(rows) {
  const byName = new Map();
  for (const row of rows) {
    if (typeof row.value !== 'number') continue;
    if (!byName.has(row.name)) byName.set(row.name, []);
    byName.get(row.name).push(row);
  }
  return [...byName.entries()]
    .map(([name, points]) => [name, [...points].sort((a, b) => a.ts.localeCompare(b.ts))])
    .sort((a, b) => b[1].length - a[1].length);
}

// ===========================================================================
// The drawing half.
// ===========================================================================

function svg(tag, props = {}) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(props)) node.setAttribute(key, value);
  return node;
}

function dayLabel(key) {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function chart(title, blurb, body) {
  if (!body) return null;
  return el('section', { className: 'chart' }, [
    el('h3', { className: 'chart-title', textContent: title }),
    el('p', { className: 'chart-blurb', 'data-help': true, textContent: blurb }),
    body,
  ]);
}

function nothing(what) {
  return el('p', { className: 'empty', textContent: `No ${what} in this range.` });
}

/** Horizontal bars: a label, a bar, a number. What every "most of X" chart
 *  wants, and it stays legible at 375 because the label truncates rather than
 *  the chart scrolling. */
function barsH(entries, { format = String, colour = SERIES[0] } = {}) {
  if (!entries.length) return null;
  const peak = Math.max(...entries.map(([, v]) => v));
  const wrap = el('div', { className: 'bars-h' });
  for (const [label, value] of entries) {
    wrap.append(el('div', { className: 'bar-h' }, [
      el('span', { className: 'bar-h-label', textContent: label, title: label }),
      el('span', { className: 'bar-h-track' }, [
        el('span', {
          className: 'bar-h-fill',
          style: `width: ${Math.max(1, (value / peak) * 100)}%; background: ${colour}`,
        }),
      ]),
      el('span', { className: 'bar-h-value', textContent: format(value) }),
    ]));
  }
  return wrap;
}

/** Vertical columns, for anything indexed by time. Scrolls in a box of its own
 *  rather than dragging the panel sideways - the fix item 42 applied to the
 *  events table, applied to the one other thing here that cannot shrink. */
function barsV(entries, { format = String, colour = SERIES[0], minWidth = 0 } = {}) {
  if (!entries.length) return null;
  const peak = Math.max(...entries.map(([, v]) => v));
  const plot = el('div', { className: 'bars-v' });
  if (minWidth) plot.style.minWidth = `${minWidth}px`;
  for (const [label, value] of entries) {
    plot.append(el('div', {
      className: 'bar-v',
      title: `${label}: ${format(value)}`,
    }, [
      el('span', { className: 'bar-v-track' }, [
        el('span', {
          className: 'bar-v-fill',
          // Zero has to look like zero, so no floor here - unlike the bars in
          // an app's readout, where every row is a thing that happened.
          style: `height: ${peak ? (value / peak) * 100 : 0}%; background: ${colour}`,
        }),
      ]),
      el('span', { className: 'bar-v-label', textContent: label }),
    ]));
  }
  return el('div', { className: 'scroll-x' }, [plot]);
}

function drawPerDay(rows) {
  const days = perDayCounts(rows);
  if (!days.length) return null;
  return barsV(days.map(([key, n]) => [dayLabel(key), n]), { minWidth: days.length * 26 });
}

function drawHours(rows) {
  const counts = hourCounts(rows);
  if (!counts.some(Boolean)) return null;
  return barsV(counts.map((n, hour) => [String(hour).padStart(2, '0'), n]), { minWidth: 430 });
}

/** A donut, which is the one place an arc says something a bar does not: the
 *  question is "what is this log made of", and a whole is what a donut draws.
 *  Labels live in the HTML legend beside it, never inside the SVG. */
function drawKinds(rows) {
  const entries = kindCounts(rows);
  if (!entries.length) return null;
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  const size = 120;
  const radius = 46;
  const ring = svg('svg', {
    viewBox: `0 0 ${size} ${size}`, class: 'donut', role: 'img',
    'aria-label': `Events by kind: ${entries.map(([k, n]) => `${k} ${n}`).join(', ')}`,
  });

  let offset = 0;
  const circumference = 2 * Math.PI * radius;
  entries.forEach(([, count], index) => {
    const length = (count / total) * circumference;
    // One dash of the right length and a gap of everything else, rotated into
    // place - a whole ring drawn as segments, with no path arithmetic and no
    // arc flags to get wrong.
    ring.append(svg('circle', {
      cx: size / 2, cy: size / 2, r: radius, fill: 'none',
      stroke: SERIES[index % SERIES.length], 'stroke-width': 16,
      'stroke-dasharray': `${length} ${circumference - length}`,
      'stroke-dashoffset': -offset,
      transform: `rotate(-90 ${size / 2} ${size / 2})`,
    }));
    offset += length;
  });

  const legend = el('div', { className: 'legend' });
  entries.forEach(([kind, count], index) => {
    legend.append(el('div', { className: 'legend-row' }, [
      el('span', {
        className: 'legend-dot',
        style: `background: ${SERIES[index % SERIES.length]}`,
      }),
      el('span', { className: 'legend-name', textContent: kind.replace('_', ' ') }),
      el('span', {
        className: 'legend-value',
        textContent: `${count} · ${Math.round((count / total) * 100)}%`,
      }),
    ]));
  });

  return el('div', { className: 'donut-row' }, [ring, legend]);
}

/** Weekday × hour - the chart that answers "when do I use this thing". A CSS
 *  grid rather than an SVG one: 168 cells with readable axis labels is exactly
 *  what grid is for, and the labels stay 11px at every width. */
function drawHeatmap(rows) {
  const grid = heatGrid(rows);
  const peak = Math.max(...grid.flat());
  if (!peak) return null;

  const table = el('div', { className: 'heat' });
  // Corner, then one label every three hours - 24 labels in a row this narrow
  // would collide, and 0/3/6/… is enough to read a position from.
  table.append(el('span', { className: 'heat-corner' }));
  for (let hour = 0; hour < 24; hour += 1) {
    table.append(el('span', {
      className: 'heat-hour', textContent: hour % 3 === 0 ? String(hour) : '',
    }));
  }
  grid.forEach((hours, day) => {
    table.append(el('span', { className: 'heat-day', textContent: DAYS[day] }));
    hours.forEach((count, hour) => {
      table.append(el('span', {
        className: 'heat-cell',
        title: `${DAYS[day]} ${String(hour).padStart(2, '0')}:00 - `
          + `${count} event${count === 1 ? '' : 's'}`,
        // Opacity rather than a hue ramp: one colour at varying strength reads
        // as "more or less", where a rainbow invites the reader to think the
        // hues mean different things.
        style: count
          ? `background: rgba(79, 142, 247, ${0.14 + 0.86 * (count / peak)})`
          : '',
      }));
    });
  });
  return el('div', { className: 'scroll-x' }, [table]);
}

function drawDurations(rows) {
  return barsH(durationTotals(rows).slice(0, TOP_N), {
    format: fmtDuration, colour: SERIES[0],
  });
}

function drawLengths(rows) {
  const counts = lengthBuckets(rows);
  if (!counts.some(Boolean)) return null;
  return barsV(BUCKETS.map(([label], index) => [label, counts[index]]), { minWidth: 330 });
}

function drawEvents(rows) {
  return barsH(eventCounts(rows).slice(0, TOP_N), { colour: SERIES[1] });
}

function drawModes(rows) {
  return barsH(modeCounts(rows).slice(0, TOP_N), { colour: SERIES[2] });
}

function drawSeries(rows) {
  const all = seriesByName(rows);
  if (!all.length) return null;
  const shown = all.slice(0, MAX_SERIES);
  const wrap = el('div', { className: 'series-grid' });
  shown.forEach(([name, points], index) => {
    wrap.append(seriesPanel(name, points, SERIES[index % SERIES.length]));
  });
  if (all.length > shown.length) {
    wrap.append(el('p', {
      className: 'chart-note',
      textContent: `${all.length - shown.length} more named series not shown.`,
    }));
  }
  return wrap;
}

function seriesPanel(name, points, colour) {
  const values = points.map((p) => p.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  // A flat series still has to draw: with no range, every point sits on the
  // middle line rather than dividing by zero.
  const span = high - low || 1;
  const W = 300;
  const H = 70;

  // Scaled uniformly (no `preserveAspectRatio="none"`): stretching the box
  // independently on each axis would turn every point marker into an ellipse
  // whose eccentricity depended on the panel's width, which is a chart whose
  // dots change shape when you resize the window.
  const plot = svg('svg', {
    viewBox: `0 0 ${W} ${H}`, class: 'series-plot', role: 'img',
    'aria-label': `${name}: ${points.length} values from ${low} to ${high}`,
  });
  const x = (index) => (points.length === 1 ? W / 2 : (index / (points.length - 1)) * W);
  const y = (value) => H - ((value - low) / span) * (H - 8) - 4;

  if (points.length > 1) {
    plot.append(svg('polyline', {
      points: points.map((p, i) => `${x(i)},${y(p.value)}`).join(' '),
      fill: 'none', stroke: colour, 'stroke-width': 1.5,
      // Keeps the line 1.5 device pixels whatever the panel scales to, so two
      // panels side by side are drawn in the same weight.
      'vector-effect': 'non-scaling-stroke',
    }));
  }
  for (const [index, point] of points.entries()) {
    const dot = svg('circle', { cx: x(index), cy: y(point.value), r: 2, fill: colour });
    // An SVG <title> is the hover text; `append` returns nothing, so the node
    // has to be built before it goes in.
    const label = svg('title');
    label.textContent = String(point.value);
    dot.append(label);
    plot.append(dot);
  }

  // Every label is HTML around the plot rather than text inside it: anything
  // drawn in a viewBox scales with it, and these have to stay readable.
  return el('div', { className: 'series-panel' }, [
    el('div', { className: 'series-head' }, [
      el('span', { className: 'series-name', textContent: name }),
      el('span', {
        className: 'series-range',
        textContent: `${low} - ${high} · ${points.length} pts`,
      }),
    ]),
    plot,
    el('div', { className: 'series-foot' }, [
      el('span', { textContent: dayLabel(localDay(points[0].ts)) }),
      el('span', { textContent: dayLabel(localDay(points[points.length - 1].ts)) }),
    ]),
  ]);
}

// --- the views -------------------------------------------------------------

/**
 * The Events page's views. The log itself has `charts: null` and is drawn by
 * the page - it is a table, it predates all of this, and moving it into a
 * chart module would be a rewrite for no gain.
 */
export const EVENT_VIEWS = [
  { id: 'log', label: 'Log', charts: null },
  {
    id: 'activity',
    label: 'Overview & Activity',
    charts: [
      ['When you use it', 'Every weekday against every hour. The one chart that '
        + 'answers "when do I actually reach for this?" - and the empty rows are '
        + 'as informative as the full ones.', drawHeatmap],
      ['Events per day', 'How busy each day was, oldest on the left.', drawPerDay],
      ['Hour of the day', 'Every hour is shown, including the quiet ones - the '
        + 'gaps are the shape of a day.', drawHours],
      ['What the log is made of', 'Presses logged, timers, and apps opening and '
        + 'closing.', drawKinds],
    ],
  },
  {
    id: 'time',
    label: 'Mode & Time',
    charts: [
      ['Where the time goes', 'Total time inside each app, from the rows written '
        + 'when one hands the button back. Timer rows are deliberately left out, '
        + 'so a stopwatch is not counted twice.', drawDurations],
      ['How long a session lasts', 'Every app session, bucketed. A tall left-hand '
        + 'side means you open things and leave again.', drawLengths],
      ['Most opened apps', 'How often each one was started - a different question '
        + 'from how long it ran.', drawModes],
    ],
  },
  {
    id: 'patterns',
    label: 'Patterns & Metrics',
    charts: [
      ['What gets logged most', 'Counting event names. The log does not record '
        + 'which gesture fired, so this is what was logged rather than how you got '
        + 'there.', drawEvents],
      ['The numbers, over time', 'One panel per event name, each with its own '
        + 'scale - a tempo and a reaction time share a column in the database and '
        + 'nothing else, so they must never share an axis.', drawSeries],
    ],
  },
];

/**
 * Draw one view into `mount`.
 *
 * Rows are whatever the filter bar currently selects, so the charts and the
 * table can never describe different things - the promise the export already
 * makes ("what you download is what you are looking at"), extended to these.
 */
export function renderEventView(mount, viewId, rows) {
  const view = EVENT_VIEWS.find((v) => v.id === viewId);
  if (!view || !view.charts) return;
  mount.replaceChildren();
  if (!rows.length) {
    mount.append(nothing('events'));
    return;
  }
  let drawn = 0;
  for (const [title, blurb, draw] of view.charts) {
    // A chart with nothing to draw is left out rather than rendered empty: six
    // "no data" boxes is a page that looks broken, and the note below says
    // what happened once instead of six times.
    const card = chart(title, blurb, draw(rows));
    if (card) {
      mount.append(card);
      drawn += 1;
    }
  }
  if (!drawn) mount.append(nothing('events with anything to chart'));
}
