// The only module that talks to the server. Everything else depends on
// this abstraction, not on fetch() - so the menu can be tested or repointed
// without touching its logic (Dependency Inversion).

export class ConfigApi {
  constructor(base = '') {
    this._base = base;
  }

  async _json(path, opts) {
    const res = await fetch(this._base + path, opts);
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error((data && (data.detail || data.error)) || `HTTP ${res.status}`);
    }
    return data;
  }

  _send(path, method, body) {
    return this._json(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  /** Current config: { path, raw, effective, warnings }. */
  get() {
    return this._json('/api/config');
  }

  /** Validate + persist + hot-reload. Returns { effective, warnings }. */
  put(body) {
    return this._send('/api/config', 'PUT', body);
  }

  /** Dry-run validation - no write. Returns { effective, warnings }. */
  validate(body) {
    return this._send('/api/config/validate', 'POST', body);
  }

  /** Live device state. The menu reads `active_modes` from it to mark which
   *  mode would answer a press right now - resolved by the host, never
   *  recomputed here. */
  status() {
    return this._json('/api/status');
  }

  /** Show one look on the button now, saving nothing. `{ clear: true }`
   *  drops back to whatever the config says. Returns what was accepted, so
   *  the picker can report a colour that fell back rather than lying about
   *  what is on the LED. */
  showLook(body) {
    return this._send('/api/dev/led', 'POST', body);
  }

  /** Per-(kind, name) totals from the whole log: count, last, extremes.
   *
   *  One request for a whole list (TODO 101) - the nav shows a live line under
   *  every app and re-renders as you type, so a query per row would be dozens
   *  per keystroke. Fetched once per load and applied to rows already on
   *  screen, which is also why a shell with no service degrades cleanly: it
   *  never patches, and keeps the line it computed from the config. */
  eventSummary() {
    return this._json('/api/events/summary');
  }

  /** Rows from the event log, newest first. Takes the same filters the Events
   *  table uses (`kind`, `name`, `mode`, `since`, `until`, `limit`).
   *
   *  What an app's own page reads to show what that app has actually done
   *  (TODO 51). Optional by construction like showLook and midiPorts: the
   *  offline editor's FileApi has no such method and no events behind it, so
   *  the readout section simply does not appear there.
   *
   *  **`limit` is not optional in practice.** The endpoint defaults to 50,
   *  which for a chart or a history is the quiet wrong answer - it renders,
   *  it looks right, and it is describing the last fifty rows. Every caller
   *  here passes one deliberately. */
  events(params = {}) {
    return this._json(`/api/events?${new URLSearchParams(params)}`);
  }

  /** The exact JSON body a webhook action would POST, without sending it -
   *  and with `send: true`, actually sent, reporting what came back.
   *
   *  The one action with nothing to show for itself until now (TODO 65): its
   *  body is the event's identity, plus whatever an app reports on the way
   *  out, plus the user's own payload, with a precedence rule between them.
   *  Optional by construction like showLook: the offline editor's FileApi has
   *  no such method, and the row does not appear there. */
  previewWebhook(body) {
    return this._send('/api/webhook/preview', 'POST', body);
  }

  /** MIDI ports this machine can reach: { available, out, in, note }. `out`
   *  is what the midi action sends to, `in` is what the metronome's clock
   *  listens on. `available` is false (with empty lists and a `note`) when
   *  there is no MIDI backend - never an error, so a caller can always just
   *  read the lists. Optional by construction like showLook: the offline
   *  editor's FileApi has no such method, and the midi port field's
   *  suggestions degrade to the plain text box when it is absent. */
  midiPorts() {
    return this._json('/api/midi/ports');
  }

  /** What the button would run with nobody connected, and whether what is on
   *  it is still current (TODO 111).
   *
   *  `{ buildable, bytes, wanted_crc, installed_crc, current, supported,
   *  menu, apps, dropped, skipped }` - or `{ buildable: false, why }` when
   *  nothing in the config compiles yet. The comparison is the point: a
   *  package is compiled from the config and pushed, and editing the config
   *  afterwards leaves the button quietly doing the old thing whenever the
   *  host is away.
   *
   *  Optional by construction like showLook and events: the offline editor's
   *  FileApi has no such method and no button behind it, so the section
   *  simply does not appear there. */
  appStatus() {
    return this._json('/api/app');
  }

  /** Compile the running config and push it to the button, over BLE.
   *
   *  The *service* does this rather than the browser or a CLI, because the
   *  service is what holds the radio - one BLE central, and it is already
   *  taken. Optional in the same way appStatus is. */
  installApp() {
    return this._json('/api/app/install', { method: 'POST' });
  }

  // --- scenes ---
  // Every one of these returns the same shape (the saved scenes, which is
  // active, the resulting effective config, and anything waiting on a
  // restart), so the scene bar re-renders from one payload however it got
  // there. See webui.py's _scene_state.

  /** All saved scenes plus which one is running. */
  scenes() {
    return this._json('/api/scenes');
  }

  /** One scene's file contents, for Export. */
  scene(id) {
    return this._json(`/api/scenes/${encodeURIComponent(id)}`);
  }

  /** Switch scenes, hot. Pass 'none' to run the base config on its own. */
  activateScene(id) {
    return this._json(`/api/scenes/${encodeURIComponent(id)}/activate`, { method: 'POST' });
  }

  /** Create one. `config` omitted means "snapshot what is running now". */
  createScene(body) {
    return this._send('/api/scenes', 'POST', body);
  }

  /** Overwrite one - it does not have to be the active scene. */
  saveScene(id, body) {
    return this._send(`/api/scenes/${encodeURIComponent(id)}`, 'PUT', body);
  }

  /** Delete one. The server refuses the active scene. */
  deleteScene(id) {
    return this._json(`/api/scenes/${encodeURIComponent(id)}`, { method: 'DELETE' });
  }
}
