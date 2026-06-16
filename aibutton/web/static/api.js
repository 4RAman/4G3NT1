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
}
