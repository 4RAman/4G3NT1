// Orchestrates the configuration menu: loads the effective config, edits a
// working copy, renders the collapsible Modes list and the Device settings
// drawer, and saves/checks through the ConfigApi. It owns the modes list
// operations (add, remove, reorder) but delegates per-mode editing to
// ModeEditor and per-field editing to the widget factory.

import { el, clear } from './dom.js';
import { ConfigApi } from './api.js';
import { SETTINGS_GROUPS, TEMPLATE_BY_TYPE } from './schema.js';
import { ModeEditor } from './modeEditor.js';
import { createField } from './widgets.js';

export class ConfigMenu {
  constructor(root, api = new ConfigApi()) {
    this.root = root;
    this.api = api;
    this.model = null; // working copy of the effective config
    this.dirty = false;
  }

  async load() {
    try {
      const data = await this.api.get();
      this.model = structuredClone(data.effective);
      if (!Array.isArray(this.model.modes)) this.model.modes = [];
      this.dirty = false;
      this._render(data.warnings || []);
    } catch (err) {
      clear(this.root);
      this.root.append(el('p', { className: 'menu-result err', textContent: `Could not load configuration: ${err.message}` }));
    }
  }

  _markDirty() {
    this.dirty = true;
    this._updateStatus();
  }

  _render(warnings = []) {
    clear(this.root);

    this.modesWrap = el('div', { className: 'modes-wrap' });
    this._renderModes();
    const addBtn = el('button', { type: 'button', className: 'add-mode', textContent: '+ Add mode' });
    addBtn.addEventListener('click', () => {
      this.model.modes.push(this._defaultMode());
      this._renderModes(this.model.modes.length - 1); // expand the newcomer
      this._markDirty();
    });

    this.statusEl = el('span', { className: 'menu-status' });
    this.resultEl = el('pre', { className: 'menu-result' });
    const mkBtn = (text, cls, fn) => {
      const b = el('button', { type: 'button', className: cls, textContent: text });
      b.addEventListener('click', fn);
      return b;
    };
    const bar = el('div', { className: 'menu-bar' }, [
      mkBtn('Save & apply', 'primary', () => this.save()),
      mkBtn('Check', '', () => this.check()),
      mkBtn('Revert', '', () => this.load()),
      this.statusEl,
    ]);

    this.root.append(
      el('h3', { className: 'menu-h', textContent: 'Modes' }),
      el('p', { className: 'menu-hint', textContent: 'Ambient modes are checked top to bottom; the first that matches the time and defines the pressed gesture wins. Takeover modes (Alarm, Stopwatch, Counter) own the button until you exit them: an Alarm fires on its own schedule, a Stopwatch or Counter is started by an Enter a mode gesture.' }),
      this.modesWrap,
      addBtn,
      this._renderSettingsDrawer(),
      bar,
      this.resultEl,
    );

    if (warnings.length) this._showResult('warn', `Loaded with warnings:\n${warnings.join('\n')}`);
    this._updateStatus();
  }

  // A sensible default new mode: an actions/always mode with one prompt.
  _defaultMode() {
    return {
      name: 'New mode',
      template: 'actions',
      activation: { type: 'always' },
      ...TEMPLATE_BY_TYPE.actions.defaults(),
    };
  }

  _renderModes(expandIndex = -1) {
    clear(this.modesWrap);
    this.editors = [];
    this.model.modes.forEach((mode, index) => {
      const editor = new ModeEditor(mode, {
        onChange: () => this._markDirty(),
        onRemove: () => { this.model.modes.splice(index, 1); this._renderModes(); this._markDirty(); },
        onMoveUp: () => this._move(index, -1),
        onMoveDown: () => this._move(index, 1),
        // Lets the enter_mode target picker list the current sibling modes
        // (filtered to takeover templates) live, without ModeEditor knowing
        // where the modes list lives.
        getModes: () => this.model.modes,
      });
      if (index === expandIndex) {
        editor.expanded = true;
        editor._applyExpanded();
      }
      this.editors.push(editor);
      this.modesWrap.append(editor.el);
    });
    if (!this.model.modes.length) {
      this.modesWrap.append(el('p', { className: 'menu-hint', textContent: 'No modes - the built-in defaults will be used.' }));
    }
  }

  _move(index, delta) {
    const target = index + delta;
    if (target < 0 || target >= this.model.modes.length) return;
    const modes = this.model.modes;
    [modes[index], modes[target]] = [modes[target], modes[index]];
    this._renderModes();
    this._markDirty();
  }

  _renderSettingsDrawer() {
    const wrap = el('div', { className: 'settings-wrap' });
    this.settingValidators = [];
    for (const group of SETTINGS_GROUPS) {
      const grid = el('div', { className: 'settings-grid' });
      for (const spec of group.fields) {
        const field = createField(spec, this.model, () => this._markDirty());
        this.settingValidators.push(field.validate);
        grid.append(field.el);
      }
      wrap.append(el('div', { className: 'settings-group' }, [
        el('h4', { className: 'settings-title', textContent: group.title }),
        grid,
      ]));
    }
    // Collapsed by default so device plumbing stays out of the way.
    return el('details', { className: 'settings-drawer' }, [
      el('summary', { className: 'settings-summary', textContent: 'Device settings (AI hosts, timeouts, ports…)' }),
      wrap,
    ]);
  }

  _collectErrors() {
    const errors = [];
    for (const editor of this.editors) errors.push(...editor.validate());
    for (const validate of this.settingValidators) {
      const error = validate();
      if (error) errors.push(error);
    }
    return errors;
  }

  async check() {
    const errors = this._collectErrors();
    if (errors.length) return this._showResult('err', `Fix these first:\n• ${errors.join('\n• ')}`);
    try {
      const res = await this.api.validate(this.model);
      this._showResult(
        res.warnings.length ? 'warn' : 'ok',
        res.warnings.length ? `Will apply with warnings:\n${res.warnings.join('\n')}` : 'Looks good - ready to save.',
      );
    } catch (err) {
      this._showResult('err', `Check failed: ${err.message}`);
    }
  }

  async save() {
    const errors = this._collectErrors();
    if (errors.length) return this._showResult('err', `Fix these first:\n• ${errors.join('\n• ')}`);
    try {
      const res = await this.api.put(this.model);
      // Re-seed from the normalized server result so the form shows exactly
      // what was stored (per-key fallbacks included).
      this.model = structuredClone(res.effective);
      if (!Array.isArray(this.model.modes)) this.model.modes = [];
      this.dirty = false;
      this._render();
      this._showResult(
        res.warnings.length ? 'warn' : 'ok',
        res.warnings.length ? `Saved with warnings:\n${res.warnings.join('\n')}` : 'Saved & applied.',
      );
    } catch (err) {
      this._showResult('err', `Save failed: ${err.message}`);
    }
  }

  _showResult(cls, text) {
    this.resultEl.className = `menu-result ${cls}`;
    this.resultEl.textContent = text;
  }

  _updateStatus() {
    if (this.statusEl) this.statusEl.textContent = this.dirty ? 'Unsaved changes' : 'Saved';
  }
}

// Composition root: wire a ConfigMenu to its mount point if present.
const mount = document.getElementById('config-menu');
if (mount) new ConfigMenu(mount).load();
