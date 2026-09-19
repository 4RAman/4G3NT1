// The scene gallery (TODO 114b): the shipped scenes, browsable, with what each
// one assumes about this machine said out loud.
//
// **This file invents no format.** The owner settled that on 2026-09-09: the
// scene gallery reuses 113's contract whole - an `index.json` carrying counts,
// facets with counts and a shard list, plus one shard per group - and only the
// *row body* changes. So the shape below is lightLibrary.js's, deliberately,
// down to the names: `loadSceneCatalog` answers the same
// `{source, total, note, facets, shards, shardKey, cached, rowsFor}` object, the
// chips are drawn from the manifest's facets **generically**, and the counts on
// them come off the manifest before a single row has been fetched.
// docs/light-library-format.md section 7 is the contract; the manifest is
// written by tools/build_scene_index.py.
//
// **A missing library is a normal state.** The offline one-file editor has no
// server to fetch from, and a checkout that has never run the builder has
// nothing to serve - both mean "no gallery here", said in one line, with no
// dialog and no console noise. There is no inlined fallback the way schema.js
// carries `LOOK_PRESETS`: a scene is a whole config, and thirteen of them
// inlined into the editor bundle would be the page weight this format exists to
// avoid. The manifest says so itself, in `fallback: null`.
//
// **A scene is not a preset, and this is the one place that matters.** Picking
// a look copies a body into the thing being edited and nothing reaches
// config.json. Picking a *scene* writes a file into `scenes/` and moves
// `scenes.active` - `ConfigManager.write_path` then sends every later edit to
// that file. So the pick is handed back to the caller (scenes.js) rather than
// done here: the guard about unsaved changes, the create-and-activate call and
// the `needs_restart` line all belong to the bar that owns the scene set.
//
// **One facet is not a fact about the files.** "Does this machine have that
// MIDI port" cannot come out of a static manifest - it would be a lie by the
// time anybody read it - so the *verdicts* arrive live on `/api/scenes`
// (`webui.py`'s `_scene_library_state`, table in `scenes.py`) and the facet's
// key and labels arrive with them, as data. This file still names no facet: it
// appends whatever facet the server handed it to the ones the manifest
// declared, and fills in the counts, which are the only part that depends on
// which rows have loaded.

import { clear, el } from './dom.js';

// Absolute, matching webui.py's mount, and fetched directly rather than through
// api.js for lightLibrary.js's reason: api.js is the module that talks to the
// *service*, and this is a static data directory with no request body, no error
// contract and nothing behind it.
const GALLERY_BASE = '/scene-library/';

// How many cards are drawn at once. Far above today's thirteen - a scene card
// is text, not a live rAF swatch, so the ceiling here is the page's height
// rather than its frame budget.
const GALLERY_PAGE = 24;

// How many *uncached* shards one search will fetch before it stops and says so.
// One shard holds the whole library today; this is what makes the page behave
// the same when it does not.
const GALLERY_SHARD_BUDGET = 4;

// The three answers a check can give (scenes.py's OK/UNMET/UNCHECKED). Only
// `unmet` is a warning: an unchecked assumption is shown, never marked wrong.
const STATE_UNMET = 'unmet';
const STATE_OK = 'ok';

// --- the boundary ---------------------------------------------------------

/**
 * One row, from a shard. `fields` is the source record kept whole, because a
 * facet this file has never heard of has to be able to find its value in it.
 *
 * `haystack` is precomputed: it is read once per row per keystroke, and for a
 * scene the searchable corpus is the whole header - the `for` sentence in
 * particular, since "streamer", "tabletop" and "time-blind" are what somebody
 * actually types.
 */
function galleryRow(raw) {
  const assumes = Array.isArray(raw.assumes) ? raw.assumes.map(String) : [];
  const tags = Array.isArray(raw.tags) ? raw.tags.map((t) => String(t).toLowerCase()) : [];
  return {
    id: String(raw.id || ''),
    title: String(raw.title || raw.id || 'Untitled scene'),
    blurb: String(raw.blurb || ''),
    audience: String(raw.for || ''),
    assumes,
    modes: Number(raw.modes) || 0,
    warnings: Array.isArray(raw.warnings) ? raw.warnings : [],
    config: raw.config && typeof raw.config === 'object' ? raw.config : {},
    fields: raw,
    haystack: [raw.title, raw.blurb, raw.for, assumes.join(' '), tags.join(' ')]
      .join(' ').toLowerCase(),
  };
}

/**
 * The scene *file* this row came from, header and all.
 *
 * The index splits a scene into a header and a config half - the header is
 * what the cards read, and keeping it out of `config` is what stops it being
 * handed to the parser twice. Installing one has to put them back together, or
 * the copy that lands in `scenes/` is anonymous data and the picker forgets
 * what it is a week later. This is the only place that mapping is written
 * down: the module that took the file apart is the one that reassembles it.
 */
export function sceneFileFrom(row) {
  const header = {};
  if (row.title) header.title = row.title;
  if (row.blurb) header.blurb = row.blurb;
  if (row.audience) header.for = row.audience;
  if (row.assumes.length) header.assumes = row.assumes.slice();
  // Header first, because a person opening the file should read what it is
  // before four hundred lines of modes. The config half wins any collision,
  // which cannot happen today and is the safe way round if it ever does.
  return { ...header, ...structuredClone(row.config) };
}

/**
 * Does `row` carry `value` for `facet` - one entry of `{key, values}`?
 *
 * Generic on purpose; this file names no facet. Where the value lives, in
 * order:
 *   - the row's own `facets` table, which is where a value that would collide
 *     with a displayed field lives (`assumes` the field is the phrases a person
 *     reads; `assumes` the facet is their slugs);
 *   - failing that, a top-level field of the same name.
 *
 * `facets` first rather than second - the one place this diverges from
 * lightLibrary.js's ordering, and deliberately: an explicit facet table is a
 * statement, a same-named field is a coincidence, and where both exist the
 * statement should win. A row with neither matches nothing, which is the right
 * answer for a chip whose facet that row does not participate in.
 */
export function sceneHasFacet(row, facet, value) {
  const table = row.fields.facets;
  const raw = (table && table[facet.key] !== undefined)
    ? table[facet.key] : row.fields[facet.key];
  if (raw === undefined || raw === null) return false;
  if (typeof raw === 'boolean') {
    const ids = facet.values.map((v) => v.id);
    const yes = ids.includes(facet.key) ? facet.key : (ids.includes('true') ? 'true' : ids[0]);
    return raw ? value === yes : value !== yes;
  }
  const values = Array.isArray(raw) ? raw.map(String) : [String(raw)];
  return values.includes(value);
}

/**
 * Which facet the shards are partitioned by, worked out rather than named -
 * the one filter answerable without fetching anything.
 */
function galleryShardKey(facets, shards) {
  return facets.map((f) => f.key)
    .find((key) => shards.length && shards.every((s) => s[key] !== undefined)) || null;
}

/** The fetched gallery, from a parsed `index.json`. */
function sceneManifestCatalog(manifest) {
  const shards = Array.isArray(manifest.shards) ? manifest.shards : [];
  // Object.entries, not a list of names: a facet a later builder adds appears
  // here with no edit to this file.
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
    note: `${total} scene${total === 1 ? '' : 's'} in the library`,
    facets,
    shards,
    shardKey: galleryShardKey(facets, shards),
    cached: (shard) => cache.has(shard.file),
    async rowsFor(shard) {
      if (cache.has(shard.file)) return cache.get(shard.file);
      // A shard that will not load costs its group and nothing else; the
      // caller counts these and says how many are missing rather than
      // pretending the search was complete.
      let rows = [];
      try {
        const res = await fetch(GALLERY_BASE + shard.file);
        if (res.ok) {
          const body = await res.json();
          rows = (Array.isArray(body.rows) ? body.rows : []).map(galleryRow);
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

/** Nothing to browse. A state, not an error - see the head of this file. */
function noGalleryCatalog(note) {
  return {
    source: 'none',
    total: 0,
    note,
    facets: [],
    shards: [],
    shardKey: null,
    cached: () => true,
    rowsFor: () => Promise.resolve([]),
  };
}

// One in-flight load for the whole page: opening the gallery twice must not be
// two manifest fetches, and the answer does not change while the page is up.
let galleryPromise = null;

/**
 * The catalogue, if this page can have one.
 *
 * **Every failure is the same answer.** A 404, a `file://` URL, a half-written
 * JSON file, a directory nobody has generated - all of them mean "there is no
 * scene library here". Nothing throws and nothing logs.
 */
export function loadSceneCatalog() {
  if (galleryPromise) return galleryPromise;
  galleryPromise = (async () => {
    try {
      // A `file:` page has nothing to fetch from, and browsers refuse the
      // attempt *loudly* - a red console line for a completely normal state.
      if (typeof location !== 'undefined' && location.protocol === 'file:') {
        throw new Error('no server');
      }
      const res = await fetch(`${GALLERY_BASE}index.json`);
      if (!res.ok) throw new Error(String(res.status));
      const manifest = await res.json();
      if (!manifest || !Array.isArray(manifest.shards) || !manifest.shards.length) {
        throw new Error('empty manifest');
      }
      return sceneManifestCatalog(manifest);
    } catch {
      return noGalleryCatalog(
        'No scene library here - run tools/build_scene_index.py to build one '
        + 'from scenes/library/. (The offline editor never has one: there is no server to fetch it from.)',
      );
    }
  })();
  return galleryPromise;
}

// --- what this machine makes of a scene ------------------------------------

/**
 * Index the server's verdicts by the exact phrase they are about, so a row
 * looks up the string it is about to display and needs no copy of the alias
 * table and no slug function.
 *
 * @param {Array} checks - `/api/scenes`'s `library.checks`
 */
export function checkIndex(checks) {
  const byText = new Map();
  for (const check of checks || []) {
    if (check && typeof check.text === 'string') byText.set(check.text, check);
  }
  return byText;
}

/**
 * What became of each of `row.assumes` on this machine.
 *
 * **Every entry, always.** A phrase nobody can check is still a thing the
 * person about to install this scene needs told, so it is listed with its
 * reason rather than hidden - and a phrase the server has never heard of
 * degrades to exactly the same "shown, not checked" rather than to an error.
 * Only `unmet` is a warning.
 */
export function assumeStatuses(row, byText) {
  return row.assumes.map((text) => {
    const found = byText.get(text);
    return {
      text,
      state: found ? String(found.state) : 'unchecked',
      detail: found ? String(found.detail || '') : '',
    };
  });
}

/** Which of this row's assumptions this machine says are missing. */
export function unmetOf(row, byText) {
  return assumeStatuses(row, byText).filter((s) => s.state === STATE_UNMET);
}

// --- the widget -----------------------------------------------------------

// Its own stylesheet, injected once and guarded by id, for lightLibrary.js's
// two reasons: it is entirely DOM-scoped, and it has to arrive in the offline
// bundle too, which inlines these modules as script and lifts the page's
// stylesheet out of index.html. It uses the page's own custom properties, so it
// inherits the theme rather than restating it.
const GALLERY_STYLE_ID = 'scene-gallery-style';

const GALLERY_CSS = `
.gal-wrap { border-top: 1px solid var(--line); margin-top: 8px; width: 100%; }
.gal { display: flex; flex-direction: column; gap: 10px; padding: 8px 0 4px; }
.gal-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.gal .gal-search { width: auto; flex: 1 1 200px; min-width: 150px; max-width: 340px; }
.gal-note { color: var(--dim); font-size: 12px; }
.gal-note.warn { color: var(--amber); }
.gal-facets { display: flex; flex-direction: column; gap: 4px; }
.gal-facet { display: flex; gap: 5px; align-items: baseline; flex-wrap: wrap; }
.gal-facet-name { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
                  color: var(--dim); flex: 0 0 66px; }
.gal-chip { padding: 2px 9px; font-size: 12px; line-height: 1.5; color: var(--dim);
            text-align: left; }
.gal-chip[aria-pressed="true"] { color: var(--text); border-color: var(--blue); background: #16202f; }
.gal-chip-count { font-size: 10px; margin-left: 5px; opacity: .7; }
/* min(): the scene bar lives in a popover ~340px wide, and a track wider than
   its container would push a horizontal scrollbar through the whole panel. */
.gal-rows { display: grid; gap: 8px;
            grid-template-columns: repeat(auto-fill, minmax(min(260px, 100%), 1fr)); }
.gal-card { display: flex; flex-direction: column; gap: 5px;
            border: 1px solid var(--line); background: var(--panel); padding: 9px 10px; }
.gal-card.gal-blocked { border-color: #4a3a1c; }
.gal-title { font-size: 14px; font-weight: 600; color: var(--text); }
.gal-blurb { font-size: 12px; color: var(--text); }
.gal-for { font-size: 11px; color: var(--dim); }
.gal-assumes { display: flex; flex-direction: column; gap: 2px; margin: 2px 0 0; padding: 0;
               list-style: none; font-size: 11px; color: var(--dim); }
.gal-assume { display: flex; gap: 5px; align-items: baseline; }
.gal-mark { flex: 0 0 auto; width: 11px; text-align: center; }
.gal-assume.is-unmet { color: var(--amber); }
.gal-assume.is-ok .gal-mark { color: var(--green); }
.gal-detail { display: block; color: var(--dim); }
.gal-card-foot { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 4px; }
.gal-count { font-size: 11px; color: var(--dim); }
.gal-foot { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
`;

function ensureGalleryStyles() {
  if (document.getElementById(GALLERY_STYLE_ID)) return;
  document.head.append(el('style', { id: GALLERY_STYLE_ID, textContent: GALLERY_CSS }));
}

/** What you typed first: a title that starts with the query, then one that
 *  contains it, then everything the rest of the header matched. */
export function rankScenes(rows, terms) {
  const first = terms[0] || '';
  const score = (row) => {
    const title = row.title.toLowerCase();
    if (first && title.startsWith(first)) return 0;
    if (first && title.includes(first)) return 1;
    return 2;
  };
  return rows.sort((a, b) => score(a) - score(b) || a.title.localeCompare(b.title));
}

/**
 * The gallery, as a widget.
 *
 * @param {object}   o
 * @param {Function} o.onPick   - (row) => void; "use this scene". The caller
 *   owns the guard about unsaved changes and the write - see the head of this
 *   file for why a scene pick is not a preset pick.
 * @param {Array}    [o.checks] - `/api/scenes`'s `library.checks`: this
 *   machine's verdict on each assumption. Absent means every assumption shows
 *   as unchecked, which is the honest answer for a page with no service.
 * @param {object}   [o.readyFacet] - the server's `library.facet`: the key and
 *   labels for "does this machine satisfy it". Absent means no such chip row.
 * @returns {{el: Element, setChecks: Function}}
 */
export function createSceneGallery(o) {
  ensureGalleryStyles();
  const root = el('div', { className: 'gal' });

  const search = el('input', {
    type: 'search', className: 'inp gal-search', placeholder: 'Search scenes…',
  });
  const note = el('span', { className: 'gal-note', textContent: 'Loading…' });
  const facetsEl = el('div', { className: 'gal-facets' });
  const rowsEl = el('div', { className: 'gal-rows' });
  const footEl = el('div', { className: 'gal-foot' });

  root.append(
    el('div', { className: 'gal-bar' }, [search, note]),
    facetsEl, rowsEl, footEl,
  );

  let catalog = null;
  let byText = checkIndex(o.checks);
  let readyFacet = o.readyFacet || null;
  // facet key -> Set of chosen value ids. OR within a facet, AND across them.
  const chosen = new Map();
  let budget = GALLERY_SHARD_BUDGET;
  let shown = GALLERY_PAGE;
  let runToken = 0;
  // Every row seen so far, for the machine facet's counts - the one facet
  // whose counts cannot come from the manifest, because they depend on this
  // machine and on which shards have landed.
  let seenRows = [];

  const terms = () => search.value.toLowerCase().split(/\s+/).filter(Boolean);

  /** The manifest's facets plus the machine's, which is appended rather than
   *  special-cased: everything below walks one list and names none of them. */
  const allFacets = () => {
    const base = catalog ? catalog.facets : [];
    if (!readyFacet || !Array.isArray(readyFacet.values)) return base;
    const counts = new Map();
    for (const row of seenRows) {
      const id = readyValue(row);
      counts.set(id, (counts.get(id) || 0) + 1);
    }
    return [...base, {
      key: readyFacet.key,
      label: readyFacet.label || readyFacet.key,
      values: readyFacet.values.map((v) => ({
        id: String(v.id), label: v.label || String(v.id), count: counts.get(String(v.id)) || 0,
      })),
      // Marked so `matches` can read this row's value without asking the row,
      // which does not carry it - it is about the machine, not the file.
      derived: true,
    }];
  };

  /** Which of the machine facet's two values this row is in. The ids come from
   *  the server; the first is the good one, which is the same convention
   *  lightLibrary's boolean facets use. */
  const readyValue = (row) => {
    const ids = (readyFacet.values || []).map((v) => String(v.id));
    return unmetOf(row, byText).length ? (ids[1] || 'needs-setup') : (ids[0] || 'ready');
  };

  const matches = (row, words) => {
    for (const facet of allFacets()) {
      const values = chosen.get(facet.key);
      if (!values || !values.size) continue;
      const hit = facet.derived
        ? values.has(readyValue(row))
        : [...values].some((value) => sceneHasFacet(row, facet, value));
      if (!hit) return false;
    }
    return words.every((word) => row.haystack.includes(word));
  };

  /** Which shards to look in, in the order to look: the shard facet narrows
   *  the pool to one bounded fetch, and whatever the pool, what is already in
   *  memory goes first because it costs nothing. */
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
    for (const facet of allFacets()) {
      // A facet with one value filters nothing - the `group` chip row while
      // the whole library is one group. Kept in the manifest (it is what says
      // how the shards are partitioned) and simply not drawn.
      if (facet.values.length < 2) continue;
      const row = el('div', { className: 'gal-facet' },
        [el('span', { className: 'gal-facet-name', textContent: facet.label })]);
      for (const value of facet.values) {
        const on = chosen.get(facet.key)?.has(value.id) || false;
        row.append(el('button', {
          type: 'button', className: 'gal-chip', 'aria-pressed': String(on),
          title: value.label,
          onclick: () => {
            const set = chosen.get(facet.key) || new Set();
            if (set.has(value.id)) set.delete(value.id); else set.add(value.id);
            chosen.set(facet.key, set);
            budget = GALLERY_SHARD_BUDGET;
            shown = GALLERY_PAGE;
            renderChips();
            run();
          },
        }, [
          el('span', { textContent: value.label }),
          el('span', { className: 'gal-chip-count', textContent: String(value.count) }),
        ]));
      }
      facetsEl.append(row);
    }
  };

  /** One scene's assumptions, in full, whatever this machine could tell. */
  const assumesList = (row) => {
    if (!row.assumes.length) {
      return el('p', { className: 'gal-for', textContent: 'Needs nothing but the button.' });
    }
    const list = el('ul', { className: 'gal-assumes' });
    for (const status of assumeStatuses(row, byText)) {
      const mark = status.state === STATE_UNMET ? '!' : (status.state === STATE_OK ? '✓' : '·');
      const item = el('li', {
        className: `gal-assume is-${status.state}`,
        // The reason lives in the title too, so a check nobody can run says
        // why on hover as well as in the line below it.
        title: status.detail || 'not checked on this machine',
      }, [
        el('span', { className: 'gal-mark', textContent: mark, 'aria-hidden': 'true' }),
        el('span', {}, [
          el('span', { textContent: status.text }),
          status.detail
            ? el('span', { className: 'gal-detail', textContent: status.detail })
            : null,
        ]),
      ]);
      list.append(item);
    }
    return list;
  };

  const card = (row) => {
    const missing = unmetOf(row, byText);
    const body = el('div', {
      className: `gal-card${missing.length ? ' gal-blocked' : ''}`,
    }, [
      el('div', { className: 'gal-title', textContent: row.title }),
      row.blurb ? el('div', { className: 'gal-blurb', textContent: row.blurb }) : null,
      row.audience ? el('div', { className: 'gal-for', textContent: `For ${row.audience}` }) : null,
      assumesList(row),
    ]);
    const use = el('button', {
      type: 'button', className: 'mini',
      // Never disabled over an unmet assumption: it is a warning, not a gate.
      // The scene still installs and still runs - the mute key simply does
      // nothing until the app it presses for is there.
      textContent: missing.length ? 'Use it anyway' : 'Use this scene',
      title: missing.length
        ? `Installs and runs; ${missing.length} thing(s) it expects are not here yet`
        : `Copy "${row.title}" into your scenes and switch to it`,
      onclick: () => o.onPick(row),
    });
    body.append(el('div', { className: 'gal-card-foot' }, [
      use,
      el('span', {
        className: 'gal-count',
        textContent: `${row.modes} mode${row.modes === 1 ? '' : 's'}`,
      }),
    ]));
    return body;
  };

  const renderRows = (found, scanned, pool, missing, done) => {
    clear(rowsEl);
    clear(footEl);
    const ranked = rankScenes(found.slice(), terms());
    for (const row of ranked.slice(0, shown)) rowsEl.append(card(row));

    if (!ranked.length) {
      rowsEl.append(el('p', {
        className: 'empty',
        textContent: catalog.source === 'none'
          ? catalog.note
          : (done ? 'No scene matched.' : 'Nothing matched yet - still looking…'),
      }));
    }
    if (ranked.length > shown) {
      footEl.append(el('button', {
        type: 'button', className: 'mini',
        textContent: `Show more (${ranked.length - shown} more matched)`,
        onclick: () => { shown += GALLERY_PAGE; renderRows(found, scanned, pool, missing, done); },
      }));
    }
    if (catalog.source === 'none') return;
    // Honest about coverage rather than silent about it, which is what the
    // manifest's per-shard row counts exist to make possible.
    const drawn = Math.min(ranked.length, shown);
    footEl.append(el('span', {
      className: 'gal-note',
      textContent: pool > scanned
        ? `${drawn} shown of ${found.length} found - searched ${scanned} of ${pool} group(s)`
        : `${drawn} shown of ${found.length} found`,
    }));
    if (missing) {
      footEl.append(el('span', {
        className: 'gal-note warn',
        textContent: `${missing} group(s) could not be loaded`,
      }));
    }
    if (pool > scanned && done) {
      footEl.append(el('button', {
        type: 'button', className: 'mini',
        textContent: `Search the other ${pool - scanned}`,
        onclick: () => { budget += GALLERY_SHARD_BUDGET; run(); },
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
      for (const row of rows) {
        if (!seenRows.includes(row)) seenRows.push(row);
        if (matches(row, words)) found.push(row);
      }
      // The machine facet's counts move as rows land, so the chips are redrawn
      // with them - the manifest-declared chips never change and simply repaint
      // with the same numbers.
      renderChips();
      renderRows(found, scanned, pool.length, missing, false);
    }
    if (token === runToken) renderRows(found, scanned, pool.length, missing, true);
  };

  let typingTimer = null;
  search.addEventListener('input', () => {
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => { shown = GALLERY_PAGE; run(); }, 140);
  });

  loadSceneCatalog().then((loaded) => {
    catalog = loaded;
    note.textContent = loaded.note;
    note.className = loaded.source === 'library' ? 'gal-note' : 'gal-note warn';
    renderChips();
    run();
  });

  return {
    el: root,
    /** New verdicts (a scene operation refreshed `/api/scenes`). Re-reads
     *  rather than re-fetches: the rows have not changed, only what this
     *  machine says about them. */
    setChecks(checks, facet) {
      byText = checkIndex(checks);
      if (facet) readyFacet = facet;
      if (catalog) { renderChips(); run(); }
    },
  };
}
