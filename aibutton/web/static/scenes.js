// The scene bar: which saved config the button is running, and the handful
// of operations on that set (switch, save as, rename, duplicate, delete,
// export, import).
//
// It sits above the tabs because a scene spans all of them - modes, lights
// and device settings are one saved thing, not three.
//
// It owns none of the editing. The menu owns the working copy; this asks for
// it (`getModel`) when saving a snapshot, asks whether it is dirty before
// throwing it away, and tells the menu to reload when the config underneath
// changes. Switching a scene replaces the entire config, so "reload" rather
// than "patch" is the only honest response to it.

import { el, clear } from './dom.js';
import { ConfigApi } from './api.js';

const NONE = 'none'; // the base config on its own - a real destination

export class SceneBar {
  /**
   * @param {Element} mount
   * @param {{getModel: () => object, isDirty: () => boolean, onChanged: () => void}} hooks
   */
  constructor(mount, hooks, api = new ConfigApi()) {
    this.mount = mount;
    this.hooks = hooks;
    this.api = api;
    this.state = null;
  }

  async load() {
    try {
      this.state = await this.api.scenes();
    } catch (err) {
      this.state = null;
      clear(this.mount);
      this.mount.append(el('span', {
        className: 'scene-msg err', textContent: `Scenes unavailable: ${err.message}`,
      }));
      return;
    }
    this._render();
  }

  /** Apply a scene-shaped response (every scene endpoint returns one) and
   *  tell the menu the config moved under it. */
  _applied(state, message) {
    this.state = state;
    this._render();
    if (message) this._say('ok', message);
    this.hooks.onChanged();
  }

  _say(cls, text) {
    if (this.msgEl) {
      this.msgEl.className = `scene-msg ${cls}`;
      this.msgEl.textContent = text;
    }
  }

  async _guard(what) {
    // Switching replaces the whole config, so unsaved edits to the current
    // one are simply gone. Ask rather than discard silently.
    if (!this.hooks.isDirty()) return true;
    return window.confirm(`You have unsaved changes. ${what} will discard them. Continue?`);
  }

  async _run(fn, message) {
    try {
      this._applied(await fn(), message);
    } catch (err) {
      this._say('err', err.message);
    }
  }

  _render() {
    clear(this.mount);
    const s = this.state;
    if (!s) return;

    const picker = el('select', { className: 'inp scene-pick', title: 'Which saved config the button is running' }, [
      el('option', { value: NONE, textContent: 'No scene - base config' }),
      ...s.scenes.map((scene) => el('option', {
        value: scene.id,
        textContent: scene.error
          ? `${scene.name} (broken)`
          : `${scene.name}${scene.mode_count == null ? '' : ` - ${scene.mode_count} mode(s)`}`,
        disabled: Boolean(scene.error),
      })),
    ]);
    picker.value = s.active || NONE;
    picker.addEventListener('change', async () => {
      const target = picker.value;
      if (!(await this._guard('Switching scene'))) {
        picker.value = s.active || NONE;
        return;
      }
      this._run(() => this.api.activateScene(target),
        target === NONE ? 'Running the base config.' : 'Scene loaded.');
    });

    this.msgEl = el('span', { className: 'scene-msg' });

    this.mount.append(
      el('span', { className: 'scene-label', textContent: 'Scene' }),
      picker,
      this._button('Save as…', () => this._saveAs()),
      this._button('Rename…', () => this._rename(), !s.active),
      this._button('Duplicate', () => this._duplicate(), !s.active),
      this._button('Delete', () => this._delete()),
      this._button('Export', () => this._export(), !s.active),
      this._importButton(),
      this.msgEl,
    );

    if (s.error) {
      this.mount.append(el('p', {
        className: 'scene-msg err',
        textContent: `config.json asks for "${s.configured}" but ${s.error} - running the base config.`,
      }));
    }
    if (s.needs_restart && s.needs_restart.length) {
      this.mount.append(el('p', {
        className: 'scene-msg warn',
        textContent: `Restart the service to apply: ${s.needs_restart.join(', ')}. `
          + 'These are only read when the service starts.',
      }));
    }
    this.mount.append(el('p', {
      className: 'scene-msg hint', 'data-help': true,
      textContent: `Scenes are plain files in ${s.dir} - edit them in any text editor with `
        + 'nothing running, then Reload. Saving here writes the active scene, not config.json.',
    }));
  }

  _button(text, fn, disabled = false) {
    const b = el('button', { type: 'button', className: 'scene-btn', textContent: text, disabled });
    b.addEventListener('click', fn);
    return b;
  }

  // A file input dressed as a button - the only way to read a file the user
  // picked, and the offline editor's way back in.
  _importButton() {
    const input = el('input', { type: 'file', accept: '.json,application/json', hidden: true });
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      input.value = ''; // so picking the same file twice fires again
      if (!file) return;
      let parsed;
      try {
        parsed = JSON.parse(await file.text());
      } catch (err) {
        return this._say('err', `${file.name} is not valid JSON: ${err.message}`);
      }
      const name = (typeof parsed.name === 'string' && parsed.name)
        || file.name.replace(/\.json$/i, '');
      this._run(
        () => this.api.createScene({ name, config: parsed, activate: false }),
        `Imported "${name}". Pick it above to run it.`,
      );
    });
    const b = this._button('Import…', () => input.click());
    return el('span', { className: 'scene-import' }, [b, input]);
  }

  async _saveAs() {
    const name = window.prompt('Save the current setup as a new scene called:', '');
    if (name === null || !name.trim()) return;
    // The working copy, not the saved one: "save as" on an edited config has
    // to capture what is on screen, or it silently saves the wrong thing.
    this._run(
      () => this.api.createScene({ name: name.trim(), config: this.hooks.getModel(), activate: true }),
      `Saved and switched to "${name.trim()}".`,
    );
  }

  async _rename() {
    const active = this.state.scenes.find((s) => s.id === this.state.active);
    if (!active) return;
    const name = window.prompt('Rename this scene to:', active.name);
    if (name === null || !name.trim()) return;
    // The id is the filename and stays put; only the label changes, so a
    // rename can never break another scene's file or the pointer.
    this._run(
      () => this.api.saveScene(active.id, { name: name.trim(), config: this.hooks.getModel() }),
      'Renamed.',
    );
  }

  async _duplicate() {
    const active = this.state.scenes.find((s) => s.id === this.state.active);
    if (!active) return;
    this._run(
      () => this.api.createScene({ name: `${active.name} copy`, config: this.hooks.getModel(), activate: false }),
      `Copied "${active.name}". Pick the copy above to edit it.`,
    );
  }

  async _delete() {
    const { active, scenes } = this.state;
    if (!active) return this._say('warn', 'No scene is active - there is nothing to delete.');
    const entry = scenes.find((s) => s.id === active);
    // The server refuses to delete the active scene, so switching away is
    // part of the operation rather than a thing the user is told to go do.
    if (!window.confirm(`Delete "${entry ? entry.name : active}"? This removes the file.`)) return;
    try {
      await this.api.activateScene(NONE);
      this._applied(await this.api.deleteScene(active), 'Deleted. Running the base config.');
    } catch (err) {
      this._say('err', err.message);
      await this.load();
    }
  }

  async _export() {
    const { active } = this.state;
    if (!active) return;
    try {
      const { raw } = await this.api.scene(active);
      const url = URL.createObjectURL(
        new Blob([`${JSON.stringify(raw, null, 2)}\n`], { type: 'application/json' }),
      );
      const link = el('a', { href: url, download: `${active}.json` });
      link.click();
      URL.revokeObjectURL(url);
      this._say('ok', `Exported ${active}.json.`);
    } catch (err) {
      this._say('err', err.message);
    }
  }
}
