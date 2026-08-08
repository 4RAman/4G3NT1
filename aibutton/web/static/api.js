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
