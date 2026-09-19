// The light library (TODO 113): a searchable bank of looks, *fetched* rather
// than shipped, and a small composer for building one out of several.
//
// **Two sources, one row shape.** The library is `aibutton/web/library/` -
// a manifest plus one shard per group, written by
// `tools/import_light_library.py` and served at `/library` (see webui.py).
// It may not be there at all: `tools/build_editor.py` inlines the editor into
// one offline HTML file, where there is no server to fetch from. So a missing
// `index.json` is a **normal state, not an error** - no dialog, no console
// noise - and the page falls back to the curated `LOOK_PRESETS` still inlined
// in schema.js, saying plainly which set is on screen. The two have different
// shapes (`label`/`effect`/`sequence` against `name`/`look`), and they are
// mapped to one shape *here*, at the boundary, so nothing downstream has to
// know where a row came from. docs/light-library-format.md section 7 is the
// contract this file reads.
//
// **The facets are read from the manifest, never named here.** `index.json`
// carries `facets: { group: [...], family: [...] }` with a count per value, so
// the chips can be drawn before a single row has loaded - and a facet a later
// importer run adds (a "quiet" one, say, for a strobe-sensitive room) appears
// on its own, with no edit to this file. That is the Open/Closed rule as CLAUDE.md
// applies it to schema.js, one level out: capability arrives as data.
//
// **Nothing here clamps anything.** Every row in the library already passed
// `flash_safe`/`sequence_safe` as an import-time *gate* - rejected with a
// reason, never rewritten - exactly as appc.py's `_look_bytes` applies the
// floor where the bytes are made. CLAUDE.md: three paths to the light, one
// call site each. A fourth clamp here would be a floor with four chances to
// drift, and would make the swatch that sold a look disagree with the button.
//
// **A preset is a starting point, never a stored thing.** Picking one *copies*
// its body into the look being edited; no id and no reference reaches
// config.json. That is the only reason the library is allowed to be this big.

import { clear, el } from './dom.js';
import { LOOK_PRESETS, describeEffect } from './schema.js';
import { paint as applySwatch } from './ledPreview.js';

// Where the shards live. Absolute, matching webui.py's mount: the served page
// is only ever at `/`. Over a `file://` URL (the offline editor) this resolves
// to nothing and the fetch rejects, which is the fallback path working as
// designed rather than a failure to handle.
//
// Fetched here rather than through api.js on purpose: api.js is "the only
// module that talks to the *server*" - the config API, one origin, one
// service. This is a static data directory with no request body, no error
// contract and no service behind it, and it must keep working when there is
// no service at all.
const LIBRARY_BASE = '/library/';

// How many rows are drawn at once. The ceiling is the animation, not the
// search: every swatch is a live rAF repaint (ledPreview.js), and a page of
// two thousand of them is a page that drops frames while you type. "Show more"
// raises it in the same steps.
const LIBRARY_PAGE = 60;

// How many *uncached* shards one search will fetch before it stops and says
// so. Nothing to do with today's 17 shards at 40 KB - it is what makes the
// page behave the same at 200 shards and 4 MB, which is the size the format
// was designed for. Shards already in memory are always searched first and
// cost nothing, so this only ever bounds the network.
const LIBRARY_SHARD_BUDGET = 8;

// A stop pushed by the composer holds this long, with a hard cut into it.
// A *default*, not a floor: `config.sequence_safe` wants every dwell at half
// the flash period (0.167 s at the stock setting) and this is comfortably
// past it, so composing by clicking cannot walk into the gate by accident -
// but the gate is still the only thing enforcing it, host-side, on save.
const COMPOSE_HOLD_S = 0.5;

// --- the boundary ---------------------------------------------------------

/** Is this look a schedule the *host* walks, rather than something the device
 *  renders unattended? Both stop lists and Morse messages are (config.py's
 *  `_parse_look` dispatches on the same key presence), and a caller editing a
 *  palette entry may offer neither - see colorEngine's `allowSequence`. */
function looksLikeSchedule(look) {
  return Boolean(look && (Array.isArray(look.stops) || typeof look.morse === 'string'));
}

/**
 * One row, whatever it came from. The single shape everything below this line
 * sees.
 *
 * `fields` is the source record itself, kept whole rather than picked apart:
 * it is what a facet filter reads, and a facet this file has never heard of
 * has to be able to find its value there.
 *
 * `haystack` is precomputed because it is read once per row per keystroke.
 */
function libraryRow(id, name, tags, look, fields, curated) {
  const words = Array.isArray(tags) ? tags.map((t) => String(t).toLowerCase()) : [];
  return {
    id: String(id || ''),
    name: String(name || id || 'unnamed'),
    tags: words,
    look,
    fields: fields || {},
    curated: Boolean(curated),
    schedule: looksLikeSchedule(look),
    haystack: `${String(name || '').toLowerCase()} ${words.join(' ')}`,
  };
}

/** A shard row (docs/light-library-format.md section 7). */
function rowFromShard(raw) {
  return libraryRow(raw.id, raw.name, raw.tags, raw.look, raw, raw.curated === true);
}

/**
 * A `LOOK_PRESETS` entry - the other shape, and the one that has no tags at
 * all. Its words are made from the label and the group so a search over "the
 * small set" still behaves like a search rather than a list you scroll; the
 * library's own rows carry hand-written tags and never come through here.
 */
function rowFromPreset(preset) {
  const body = preset.sequence || preset.effect;
  const words = `${preset.label || ''} ${preset.group || ''}`
    .toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  return libraryRow(
    preset.id, preset.label, words, body, { group: preset.group }, true,
  );
}

/**
 * The body a row drops in. **Copied, never shared** - a preset is a starting
 * point, and editing what you picked must not edit the library you picked it
 * from. (schema.js's `presetLook` says the same thing about the inline set;
 * this is that rule applied to a row held in a shard cache, where the sharing
 * would outlive the widget.)
 */
export function lookFromRow(row) {
  return structuredClone(row.look);
}

/**
 * Does `row` carry `value` for `facet` - one entry of the manifest's facet
 * table, `{ key, values }`?
 *
 * Generic on purpose: this file names no facet, so every reading below is
 * derived from what the manifest declared. Where the value lives, in order:
 *   - a top-level field on the row (`group`, `family`, `quiet`);
 *   - a `facets` object on the row, for a value that would collide with the
 *     six documented fields;
 *   - failing both, the tags, which is where a facet that is a *label* rather
 *     than a column would live.
 *
 * A field may be a string, a list of strings, or a **boolean with two named
 * buckets** - `quiet: true` against a facet called "quiet" offering "quiet"
 * and "busy". That last one is the case a naive `String(raw)` gets silently
 * wrong (it would look for "true"), so the two sides are worked out from the
 * facet's own declaration: the facet's name is the true side, anything else it
 * declares is the false side. A later `dim`/`bright` or `loop`/`one-shot`
 * lands the same way, with no edit here.
 */
function rowHasFacet(row, facet, value) {
  const key = facet.key;
  const raw = row.fields[key] === undefined ? row.fields.facets?.[key] : row.fields[key];
  if (raw === undefined || raw === null) return row.tags.includes(value);
  if (typeof raw === 'boolean') {
    const ids = facet.values.map((v) => v.id);
    const yes = ids.includes(key) ? key : (ids.includes('true') ? 'true' : ids[0]);
    return raw ? value === yes : value !== yes;
  }
  const values = Array.isArray(raw) ? raw.map(String) : [String(raw)];
  return values.includes(value);
}

// --- the catalogue --------------------------------------------------------

/** The inlined set, as a catalogue. No fetch, no shards, everything resident.
 *
 *  Its facets are derived from the presets themselves rather than declared,
 *  which is what keeps the fallback honest: `LOOK_PRESETS` has a group and no
 *  family, so the page shows a group chip row and no family chip row, instead
 *  of family chips that would filter to nothing. */
function builtinCatalog(note) {
  const rows = LOOK_PRESETS.map(rowFromPreset);
  const counts = new Map();
  for (const row of rows) {
    const group = row.fields.group;
    if (group) counts.set(group, (counts.get(group) || 0) + 1);
  }
  const shard = { file: '(built-in)', label: 'Built-in', rows: rows.length };
  return {
    source: 'builtin',
    total: rows.length,
    note,
    facets: counts.size
      ? [{
        key: 'group',
        label: 'Group',
        values: [...counts].map(([id, count]) => ({ id, label: id, count })),
      }]
      : [],
    shards: [shard],
    shardKey: 'group',
    cached: () => true,
    rowsFor: () => Promise.resolve(rows),
  };
}

/**
 * Which facet the shards are partitioned by, worked out rather than named.
 *
 * A shard entry carries the value of exactly one facet (`group`, today), and
 * that is the one filter answerable *without* fetching anything - picking it
 * turns a search into a bounded fetch, which is the whole reason the format
 * sharded by group in the first place. Derived so that a manifest that one day
 * shards by something else still gets the shortcut.
 */
function shardFacetKey(facets, shards) {
  return facets.map((f) => f.key)
    .find((key) => shards.length && shards.every((s) => s[key] !== undefined)) || null;
}

/** The fetched library, from a parsed `index.json`. */
function manifestCatalog(manifest) {
  const shards = Array.isArray(manifest.shards) ? manifest.shards : [];
  // Object.entries, not a list of names: the facet set is data (see the head
  // of this file), and a facet added by a later import has to appear here
  // without an edit.
  const facets = Object.entries(manifest.facets || {}).map(([key, values]) => ({
    key,
    label: key.charAt(0).toUpperCase() + key.slice(1),
    values: (Array.isArray(values) ? values : []).map((v) => ({
      id: String(v.id),
      label: v.label || String(v.id),
      count: Number(v.count) || 0,
    })),
  }));
  const cache = new Map();
  const total = Number(manifest.counts?.total)
    || shards.reduce((sum, s) => sum + (Number(s.rows) || 0), 0);

  return {
    source: 'library',
    total,
    note: `${total.toLocaleString()} look${total === 1 ? '' : 's'} in the light library`,
    facets,
    shards,
    shardKey: shardFacetKey(facets, shards),
    cached: (shard) => cache.has(shard.file),
    async rowsFor(shard) {
      if (cache.has(shard.file)) return cache.get(shard.file);
      // A shard that will not load costs its group and nothing else. The
      // caller counts these and says how many are missing rather than
      // pretending the search was complete.
      let rows = [];
      try {
        const res = await fetch(LIBRARY_BASE + shard.file);
        if (res.ok) {
          const body = await res.json();
          rows = (Array.isArray(body.rows) ? body.rows : []).map(rowFromShard);
        } else {
          rows.failed = true;
        }
      } catch {
        rows = [];
        rows.failed = true;
      }
      cache.set(shard.file, rows);
      return rows;
    },
  };
}

// One in-flight load for the whole page, however many browsers ask: two
// pickers open at once must not be two manifest fetches, and the answer never
// changes while the page is up.
let libraryCatalogPromise = null;

/**
 * The catalogue, whichever one this page can have.
 *
 * **Every failure is the same answer.** A 404, a `file://` URL, a half-written
 * JSON file, a directory that was never generated - all of them mean "there is
 * no library here", which is a state the offline editor is *always* in. So
 * nothing throws, nothing logs, and the caller gets the built-in set with a
 * sentence explaining what it is looking at.
 */
export function loadLightCatalog() {
  if (libraryCatalogPromise) return libraryCatalogPromise;
  libraryCatalogPromise = (async () => {
    try {
      // A `file:` page has nothing to fetch from, and browsers refuse the
      // attempt *loudly* - a red line in the console for a state that is
      // completely normal. The offline editor is always in it, so it is not
      // asked. Every other failure below is caught and means the same thing.
      if (typeof location !== 'undefined' && location.protocol === 'file:') {
        throw new Error('no server');
      }
      const res = await fetch(`${LIBRARY_BASE}index.json`);
      if (!res.ok) throw new Error(String(res.status));
      const manifest = await res.json();
      if (!manifest || !Array.isArray(manifest.shards) || !manifest.shards.length) {
        throw new Error('empty manifest');
      }
      return manifestCatalog(manifest);
    } catch {
      return builtinCatalog(
        `${LOOK_PRESETS.length} built-in presets - the light library is not `
        + 'being served here, so this is the small set that ships inside the page',
      );
    }
  })();
  return libraryCatalogPromise;
}

// --- composing (TODO 113's "+") -------------------------------------------

/** One flat colour, held. A stop *is* one flat colour
 *  (docs/light-library-format.md section 2) - it cannot flash or breathe on
 *  its own, which is why converting an animated look into a stop keeps the
 *  colour and loses the movement. */
function stopOf(color) {
  return { color: color || '#ffffff', hold_s: COMPOSE_HOLD_S, fade_s: 0, curve: 'linear' };
}

/**
 * Push `row`'s colour onto `look`, in place - TODO 113's "+", the other half
 * of the library page.
 *
 * **A second editor surface over the same look object, not a new config
 * shape.** What comes out is an ordinary stop list, exactly what the Sequence
 * tab edits and what `sequencer.py` walks; the only thing new is the gesture
 * that builds it. A look that is not a list yet becomes one, carrying its
 * colour in as the first stop.
 *
 * Returns a sentence about what happened, or one about why nothing did - the
 * caller shows it, because both answers are things a person needs told.
 */
export function pushRowOntoLook(look, row) {
  if (typeof look.morse === 'string') {
    return { ok: false, message: 'A Morse look spells a message - there is no stop list to push a colour onto.' };
  }
  if (typeof row.look.morse === 'string') {
    return { ok: false, message: `"${row.name}" is a Morse message, not a colour.` };
  }
  let note = '';
  if (!Array.isArray(look.stops)) {
    // The animation cannot survive - see stopOf. Said out loud rather than
    // done quietly, because the swatch is about to change and the reason has
    // to be on screen next to it.
    const had = look.style && look.style !== 'solid' ? ` The ${look.style} it had is gone - a stop is one flat colour.` : '';
    const first = stopOf(look.color);
    for (const key of Object.keys(look)) delete look[key];
    look.stops = [first];
    look.repeat = true;
    note = ` Turned it into a stop list.${had}`;
  }
  const added = Array.isArray(row.look.stops)
    ? row.look.stops.map((s) => structuredClone(s))
    : [stopOf(row.look.color)];
  look.stops.push(...added);
  const n = added.length;
  return {
    ok: true,
    message: `Added ${n === 1 ? `"${row.name}"` : `${n} stops from "${row.name}"`}`
      + ` - ${look.stops.length} stops now.${note}`,
  };
}

// --- the widget -----------------------------------------------------------

// This module carries its own stylesheet rather than adding a block to
// index.html's. Two reasons, and the second is the real one: it is entirely
// DOM-scoped (nothing outside a `.lib` root is touched), and it has to arrive
// in the offline bundle too - `tools/build_editor.py` lifts the page's
// stylesheet out of index.html and inlines these modules as script, so a rule
// injected at runtime reaches both shells from one place. Injected once,
// guarded by id, and it uses the page's own custom properties so it inherits
// the theme rather than restating it.
const LIBRARY_STYLE_ID = 'light-library-style';

const LIBRARY_CSS = `
.lib { display: flex; flex-direction: column; gap: 10px; padding: 6px 0 2px; }
.lib-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.lib .lib-search { width: auto; flex: 1 1 180px; min-width: 140px; max-width: 320px; }
.lib-note { color: var(--dim); font-size: 12px; }
.lib-note.warn { color: var(--amber); }
.lib-facets { display: flex; flex-direction: column; gap: 4px; }
.lib-facet { display: flex; gap: 5px; align-items: baseline; flex-wrap: wrap; }
.lib-facet-name { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
                  color: var(--dim); flex: 0 0 66px; }
.lib-chip { padding: 2px 9px; font-size: 12px; line-height: 1.5; color: var(--dim); }
.lib-chip[aria-pressed="true"] { color: var(--text); border-color: var(--blue); background: #16202f; }
.lib-chip-count { font-size: 10px; margin-left: 5px; opacity: .7; }
.lib-rows { display: flex; flex-wrap: wrap; gap: 6px; }
.lib-item { display: inline-flex; align-items: stretch; }
.lib-item .preset-dot { max-width: 220px; }
.lib-item .lib-add { padding: 4px 8px; line-height: 1; color: var(--dim); margin-left: -1px; }
.lib-item .lib-add:hover { color: var(--text); border-color: #9ec2ff; }
.lib-foot { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.lib-target { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.lib .lib-target-pick { width: auto; min-width: 170px; }
`;

function ensureLibraryStyles() {
  if (document.getElementById(LIBRARY_STYLE_ID)) return;
  document.head.append(el('style', { id: LIBRARY_STYLE_ID, textContent: LIBRARY_CSS }));
}

/** Ordered so what you typed comes first: a name that starts with the query,
 *  then a name that contains it, then everything the tags matched. */
function rankRows(rows, terms) {
  const first = terms[0] || '';
  const score = (row) => {
    const name = row.name.toLowerCase();
    if (first && name.startsWith(first)) return 0;
    if (first && name.includes(first)) return 1;
    return 2;
  };
  return rows.sort((a, b) => score(a) - score(b) || a.name.localeCompare(b.name));
}

/**
 * The library, as a widget.
 *
 * @param {object}   o
 * @param {Function} o.onPick        - (row) => void; "use this look"
 * @param {Function} [o.onAdd]       - (row) => void; the "+" composer. Absent
 *   means no "+" button, which is the picker-only case (the look editor).
 * @param {string}   [o.addTitle]    - what the "+" says it will do
 * @param {boolean}  [o.allowSequence] - offer rows the *host* walks (stop
 *   lists, Morse). Off by default, exactly as colorEngine's own flag: a
 *   palette entry ships to the device and renders unattended, so a schedule
 *   is not a look it can hold. Filtered rather than disabled, so the page
 *   never shows you something a Save would drop.
 * @param {Element}  [o.above]       - dropped in above the search bar (the
 *   composer's target picker, which belongs to the caller's model, not here)
 * @returns {{el: Element}}
 */
export function createLibraryBrowser(o) {
  ensureLibraryStyles();
  const root = el('div', { className: 'lib' });

  const search = el('input', {
    type: 'search', className: 'inp lib-search', placeholder: 'Search looks and tags…',
  });
  const note = el('span', { className: 'lib-note', textContent: 'Loading…' });
  const facetsEl = el('div', { className: 'lib-facets' });
  const rowsEl = el('div', { className: 'lib-rows' });
  const footEl = el('div', { className: 'lib-foot' });

  // Appended separately, not as a child in the list below: `Node.append`
  // stringifies whatever it is given, so a missing `above` handed to it turns
  // into the word "null" sitting above the search box. (dom.js's `el` filters
  // those out; this call does not go through it.)
  if (o.above) root.append(o.above);
  root.append(
    el('div', { className: 'lib-bar' }, [search, note]),
    facetsEl, rowsEl, footEl,
  );

  let catalog = null;
  // facet key -> Set of chosen value ids. Within one facet the values are
  // OR-ed, across facets they are AND-ed - what a chip row means everywhere.
  const chosen = new Map();
  let budget = LIBRARY_SHARD_BUDGET;
  let shown = LIBRARY_PAGE;
  // Every search carries a token; a run whose token has been superseded drops
  // its results on the floor instead of painting them over a newer query.
  let runToken = 0;

  const terms = () => search.value.toLowerCase().split(/\s+/).filter(Boolean);

  const matches = (row, words) => {
    if (!o.allowSequence && row.schedule) return false;
    // Walked over the manifest's facets rather than over what has been
    // clicked, because a facet's *declaration* is what says how to read a row
    // - see rowHasFacet on the boolean case.
    for (const facet of catalog.facets) {
      const values = chosen.get(facet.key);
      if (!values || !values.size) continue;
      let hit = false;
      for (const value of values) if (rowHasFacet(row, facet, value)) { hit = true; break; }
      if (!hit) return false;
    }
    return words.every((word) => row.haystack.includes(word));
  };

  /**
   * Which shards this search will look in, in the order to look.
   *
   * Two rules, and both are about not fetching 200 files. Picking the facet
   * the shards are partitioned by narrows the pool to exactly those shards -
   * one bounded fetch, the common case the format was built around. And
   * whatever the pool, shards already in memory go first: they cost nothing,
   * so a search answers out of what is loaded before it asks the network for
   * anything at all.
   */
  const candidates = () => {
    const key = catalog.shardKey;
    const picked = key ? chosen.get(key) : null;
    const pool = picked && picked.size
      ? catalog.shards.filter((s) => picked.has(String(s[key])))
      : catalog.shards;
    return [
      ...pool.filter((s) => catalog.cached(s)),
      ...pool.filter((s) => !catalog.cached(s)),
    ];
  };

  const renderChips = () => {
    clear(facetsEl);
    for (const facet of catalog.facets) {
      if (!facet.values.length) continue;
      const row = el('div', { className: 'lib-facet' },
        [el('span', { className: 'lib-facet-name', textContent: facet.label })]);
      for (const value of facet.values) {
        const on = chosen.get(facet.key)?.has(value.id) || false;
        const chip = el('button', {
          type: 'button', className: 'lib-chip', 'aria-pressed': String(on),
          onclick: () => {
            const set = chosen.get(facet.key) || new Set();
            if (set.has(value.id)) set.delete(value.id); else set.add(value.id);
            chosen.set(facet.key, set);
            // A new filter is a new search: the shard budget starts over, so
            // narrowing to one group never inherits "already searched eight".
            budget = LIBRARY_SHARD_BUDGET;
            shown = LIBRARY_PAGE;
            renderChips();
            run();
          },
        }, [
          el('span', { textContent: value.label }),
          el('span', { className: 'lib-chip-count', textContent: String(value.count) }),
        ]);
        row.append(chip);
      }
      facetsEl.append(row);
    }
  };

  const renderRows = (found, scanned, pool, missing, done) => {
    clear(rowsEl);
    clear(footEl);
    const words = terms();
    const ranked = rankRows(found.slice(), words);
    for (const row of ranked.slice(0, shown)) {
      const chip = el('span', { className: 'preset-dot-swatch' });
      applySwatch(chip, row.look);  // the same painter the LED uses
      const pick = el('button', {
        type: 'button', className: 'preset-dot',
        title: `${row.name} - ${describeEffect(row.look)}`
          + (row.tags.length ? `\n${row.tags.join(', ')}` : ''),
        onclick: () => o.onPick(row),
      }, [chip, el('span', { className: 'preset-dot-label', textContent: row.name })]);
      const item = el('div', { className: 'lib-item' }, [pick]);
      if (o.onAdd) {
        item.append(el('button', {
          type: 'button', className: 'mini lib-add', textContent: '+',
          title: o.addTitle || `Add ${row.name} to the look being composed`,
          onclick: () => o.onAdd(row),
        }));
      }
      rowsEl.append(item);
    }

    if (!ranked.length) {
      rowsEl.append(el('p', {
        className: 'empty',
        textContent: done
          ? 'Nothing matched.' : 'Nothing matched yet - still looking…',
      }));
    }
    if (ranked.length > shown) {
      footEl.append(el('button', {
        type: 'button', className: 'mini lib-more',
        textContent: `Show more (${ranked.length - shown} more matched)`,
        onclick: () => { shown += LIBRARY_PAGE; renderRows(found, scanned, pool, missing, done); },
      }));
    }
    // Honest about coverage rather than silent about it, which is what the
    // manifest's per-shard row counts exist to make possible: "searched 8 of
    // 24 groups" is a true sentence, and freezing until all 24 have landed is
    // not an improvement on it.
    const where = catalog.shardKey ? 'group' : 'shard';
    const drawn = Math.min(ranked.length, shown);
    const line = pool > scanned
      ? `${drawn} shown of ${found.length} found - searched ${scanned} of ${pool} ${where}s`
      : `${drawn} shown of ${found.length} found in ${scanned} ${where}${scanned === 1 ? '' : 's'}`;
    footEl.append(el('span', { className: 'lib-note', textContent: line }));
    if (missing) {
      footEl.append(el('span', {
        className: 'lib-note warn',
        textContent: `${missing} ${where}${missing === 1 ? '' : 's'} could not be loaded`,
      }));
    }
    if (pool > scanned && done) {
      footEl.append(el('button', {
        type: 'button', className: 'mini',
        textContent: `Search the other ${pool - scanned}`,
        onclick: () => { budget += LIBRARY_SHARD_BUDGET; run(); },
      }));
    }
  };

  /** Walk the candidate shards, painting as each one lands. */
  const run = async () => {
    runToken += 1;
    const token = runToken;
    const pool = candidates();
    const words = terms();
    const found = [];
    let scanned = 0;
    let fetched = 0;
    let missing = 0;
    // Nothing on screen yet and nothing loaded either: draw the empty frame so
    // the chips and the count are there while the first shard is in flight.
    renderRows(found, scanned, pool.length, missing, false);
    for (const shard of pool) {
      if (!catalog.cached(shard)) {
        if (fetched >= budget) break;
        fetched += 1;
      }
      const rows = await catalog.rowsFor(shard);
      if (token !== runToken) return;  // a newer query owns the view
      if (rows.failed) missing += 1;
      scanned += 1;
      for (const row of rows) if (matches(row, words)) found.push(row);
      renderRows(found, scanned, pool.length, missing, false);
      // Enough to fill several pages: past this the extra fetches buy nothing
      // a person is going to scroll to, and "Show more" can always ask again.
      if (found.length >= shown * 4) break;
    }
    if (token === runToken) renderRows(found, scanned, pool.length, missing, true);
  };

  let typingTimer = null;
  search.addEventListener('input', () => {
    clearTimeout(typingTimer);
    // Long enough that a fast typist causes one search, short enough that it
    // still feels like the list is following the keyboard.
    typingTimer = setTimeout(() => { shown = LIBRARY_PAGE; run(); }, 140);
  });

  loadLightCatalog().then((loaded) => {
    catalog = loaded;
    note.textContent = loaded.note;
    note.className = loaded.source === 'library' ? 'lib-note' : 'lib-note warn';
    renderChips();
    run();
  });

  return { el: root };
}
