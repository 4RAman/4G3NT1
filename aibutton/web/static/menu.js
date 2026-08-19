// Orchestrates the configuration menu. Loads the effective config, edits a
// working copy, and renders into four mount points the page's tabs already
// gate the visibility of - Modes, Lights, Device settings, plus a shared
// sticky bar for Save/Check/Revert. It owns the modes list operations (add,
// remove, reorder, which one is selected) but delegates per-mode editing to
// ModeEditor and per-field editing to the widget factory.

import { el, clear } from './dom.js';
import { ConfigApi } from './api.js';
import {
  BUILTIN_MODES, GESTURES, SYSTEM_LED_STATES,
  MODE_GROUPS, SETTINGS_GROUPS, TEMPLATE_BY_TYPE, describeTemplate,
} from './schema.js';
import { ModeEditor } from './modeEditor.js';
import { SceneBar } from './scenes.js';
import { createField } from './widgets.js';
import { createLookEditor } from './colorEngine.js';

export class ConfigMenu {
  /** @param {{modes: Element, lights: Element, device: Element, bar: Element, scenes?: Element}} mounts */
  constructor(mounts, api = new ConfigApi()) {
    this.mounts = mounts;
    this.api = api;
    this.model = null; // working copy of the effective config
    this.dirty = false;
    this.selectedMode = null; // the mode object shown in the detail pane
    // The scene bar lives outside the tabs and outlives a re-render: a scene
    // spans modes, lights and settings, so rebuilding it per tab render would
    // be both wasteful and a flicker on every keystroke-driven redraw.
    this.sceneBar = mounts.scenes
      ? new SceneBar(mounts.scenes, {
        getModel: () => this.model,
        isDirty: () => this.dirty,
        // A switch replaces the whole config; nothing on screen survives it.
        onChanged: () => this.load({ refreshScenes: false }),
      }, api)
      : null;
  }

  /** Re-read the config and rebuild. `refreshScenes` is false when the scene
   *  bar is the one that caused this, since it has already rendered the
   *  response it got - re-fetching would only wipe its own status line. */
  async load({ refreshScenes = true } = {}) {
    if (this.sceneBar && refreshScenes) this.sceneBar.load();
    try {
      const data = await this.api.get();
      this.model = structuredClone(data.effective);
      if (!Array.isArray(this.model.modes)) this.model.modes = [];
      this.dirty = false;
      this._render(data.warnings || []);
    } catch (err) {
      for (const mount of this._ownMounts()) clear(mount);
      this.mounts.modes.append(el('p', {
        className: 'menu-result err', textContent: `Could not load configuration: ${err.message}`,
      }));
    }
  }

  _markDirty() {
    this.dirty = true;
    this._updateStatus();
    // What starts a takeover mode lives in *other* modes' gestures, so an
    // edit anywhere can change the open card's "to start it" line - including
    // whether it is reachable at all.
    this.detailEditor?.refreshExplainers();
    this._applyActive(this._lastActive || {});
  }

  /** The mounts this menu draws into, and therefore the only ones it may
   *  clear. The scene bar renders into a mount of its own on its own
   *  schedule - wiping it here would erase whatever it had just drawn. */
  _ownMounts() {
    return [this.mounts.modes, this.mounts.lights, this.mounts.device, this.mounts.bar];
  }

  _render(warnings = []) {
    for (const mount of this._ownMounts()) clear(mount);
    if (this.selectedMode && !this.model.modes.includes(this.selectedMode)) this.selectedMode = null;

    this.mounts.modes.append(this._renderPrimer(), this._renderModesLayout());
    this.mounts.lights.append(this._renderPaletteSection());
    this.mounts.device.append(this._renderSettingsSection());

    this.statusEl = el('span', { className: 'menu-status' });
    this.resultEl = el('pre', { className: 'menu-result' });
    const mkBtn = (text, cls, fn) => {
      const b = el('button', { type: 'button', className: cls, textContent: text });
      b.addEventListener('click', fn);
      return b;
    };
    this.mounts.bar.append(
      mkBtn('Save', 'primary', () => this.save()),
      mkBtn('Check', '', () => this.check()),
      mkBtn('Revert', '', () => this.load()),
      this.statusEl,
      this.resultEl,
    );

    if (warnings.length) this._showResult('warn', `Loaded with warnings:\n${warnings.join('\n')}`);
    this._updateStatus();
    this._startActivePolling();
  }

  // The three sentences that answer "how do I switch modes?" - tutorial
  // content, so it rides on the page's Tips toggle (help.js) rather than
  // sitting on screen permanently.
  _renderPrimer() {
    const line = (text) => el('li', { className: 'primer-line', textContent: text });
    return el('div', { className: 'primer', 'data-help': true }, [
      el('p', { className: 'primer-lead', textContent: 'How this button decides what a press does' }),
      el('ol', { className: 'primer-list' }, [
        line('A mode is a set of instructions: what a short press, a long press and a double tap should each do.'),
        line('You never pick a mode by hand. The button looks down your everyday modes from the top and uses the first one that is switched on right now and has something set for the press you made.'),
        line('Some modes take over instead: once started, they own every press until you leave them. Those are listed separately below, each with how to start it and how to get out.'),
      ]),
    ]);
  }

  // Ready-made modes. Each drops in a complete, valid mode you then edit -
  // faster than assembling a Pomodoro field by field, and it doubles as the
  // answer to "what can this thing do?".
  _renderBuiltins() {
    const picker = el('select', { className: 'inp builtin-pick' }, [
      el('option', { value: '', textContent: 'Add a ready-made mode…' }),
      ...BUILTIN_MODES.map((b) => el('option', { value: b.id, textContent: b.label })),
    ]);
    const blurb = el('span', { className: 'menu-hint builtin-blurb' });
    const describe = () => {
      const chosen = BUILTIN_MODES.find((b) => b.id === picker.value);
      blurb.textContent = chosen ? chosen.blurb : '';
    };
    picker.addEventListener('change', () => {
      const chosen = BUILTIN_MODES.find((b) => b.id === picker.value);
      if (!chosen) return describe();
      this._addMode(this._uniquelyNamed(chosen.mode()));
      picker.value = '';
      describe();
    });
    return el('span', { className: 'builtin-wrap' }, [picker, blurb]);
  }

  /** Append `mode`, select it for editing, and flag unsaved changes. */
  _addMode(mode) {
    this.model.modes.push(mode);
    this._renderModes(mode);
    this._markDirty();
  }

  /** "Pomodoro" -> "Pomodoro 2" if that name is taken. Two modes may share a
   *  name without breaking anything, but `enter_mode` targets are resolved by
   *  name, so duplicates would make the picker ambiguous. */
  _uniquelyNamed(mode) {
    const taken = new Set((this.model.modes || []).map((m) => m && m.name));
    if (!taken.has(mode.name)) return mode;
    let n = 2;
    while (taken.has(`${mode.name} ${n}`)) n += 1;
    return { ...mode, name: `${mode.name} ${n}` };
  }

  // A sensible default new mode: an actions/always mode with one gesture.
  _defaultMode() {
    return {
      name: 'New mode',
      template: 'actions',
      activation: { type: 'always' },
      ...TEMPLATE_BY_TYPE.actions.defaults(),
    };
  }

  /** A mode's nature drives which group it lands in. Unknown templates read
   *  as everyday, which is the harmless default: they answer gestures. */
  _natureOf(mode) {
    return TEMPLATE_BY_TYPE[mode?.template]?.nature || 'ambient';
  }

  // --- modes: master/detail --------------------------------------------
  // A narrow nav list (grouped by nature) plus one detail pane showing
  // whichever mode is selected, fully open. Only ever one ModeEditor is on
  // screen at a time, which is also why Save/Check has to validate the other
  // modes itself rather than asking their (nonexistent) editors - see
  // _collectErrors().

  _renderModesLayout() {
    this.modeNavEl = el('div', { className: 'mode-nav scroll-fade' });
    this.modeDetailEl = el('div', { className: 'mode-detail' });
    const addBtn = el('button', { type: 'button', className: 'add-mode', textContent: '+ Add mode' });
    addBtn.addEventListener('click', () => this._addMode(this._defaultMode()));

    this._renderModes();

    return el('div', { className: 'mode-layout' }, [
      el('div', { className: 'mode-nav-col' }, [
        this.modeNavEl,
        el('div', { className: 'add-row' }, [addBtn, this._renderBuiltins()]),
      ]),
      this.modeDetailEl,
    ]);
  }

  /** Rebuild the nav list and detail pane. Pass a mode to select it (e.g. one
   *  just added); otherwise the current selection is kept if it still exists,
   *  falling back to the first mode. */
  _renderModes(selectMode) {
    if (selectMode !== undefined) this.selectedMode = selectMode;
    if (this.selectedMode && !this.model.modes.includes(this.selectedMode)) this.selectedMode = null;
    if (!this.selectedMode && this.model.modes.length) this.selectedMode = this.model.modes[0];
    this._renderModeNav();
    this._renderModeDetail();
    this._applyActive(this._lastActive || {});
  }

  _renderModeNav() {
    clear(this.modeNavEl);
    this.navButtons = new Map(); // mode -> { dot, nameEl, summaryEl }

    for (const group of MODE_GROUPS) {
      const members = this.model.modes.filter((m) => this._natureOf(m) === group.nature);
      const groupEl = el('div', { className: 'mode-nav-group' }, [
        el('div', { className: 'mode-nav-group-title', textContent: group.title }),
        el('p', { className: 'mode-nav-group-hint', 'data-help': true, textContent: group.blurb }),
      ]);

      if (!members.length) {
        groupEl.append(el('p', { className: 'empty mode-nav-empty', textContent: group.emptyText }));
      }
      for (const mode of members) {
        const dot = el('span', { className: 'mode-active-dot', hidden: true });
        const nameEl = el('span', { className: 'mode-nav-name', textContent: mode.name || '(unnamed)' });
        const summaryEl = el('span', { className: 'mode-nav-summary', textContent: describeTemplate(mode) });
        const item = el('button', {
          type: 'button',
          className: 'mode-nav-item' + (mode === this.selectedMode ? ' selected' : ''),
        }, [dot, nameEl, summaryEl]);
        item.addEventListener('click', () => this._renderModes(mode));
        this.navButtons.set(mode, { dot, nameEl, summaryEl });
        groupEl.append(item);
      }
      this.modeNavEl.append(groupEl);
    }
  }

  _renderModeDetail() {
    clear(this.modeDetailEl);
    this.detailEditor = null;
    const mode = this.selectedMode;
    if (!mode) {
      this.modeDetailEl.append(el('p', {
        className: 'mode-detail-empty', textContent: 'Select or add a mode.',
      }));
      return;
    }
    this.detailEditor = new ModeEditor(mode, {
      onChange: () => {
        this._markDirty();
        const entry = this.navButtons?.get(mode);
        if (entry) {
          entry.nameEl.textContent = mode.name || '(unnamed)';
          entry.summaryEl.textContent = describeTemplate(mode);
        }
      },
      onRemove: () => {
        this.model.modes.splice(this.model.modes.indexOf(mode), 1);
        this.selectedMode = null;
        this._renderModes();
        this._markDirty();
      },
      onMoveUp: () => this._move(mode, -1),
      onMoveDown: () => this._move(mode, 1),
      // Only everyday modes are read in order, so only they get the reorder
      // arrows - a takeover mode is found by name, and offering to reorder
      // it would imply a priority it does not have.
      canReorder: this._natureOf(mode) === 'ambient',
      // Lets the enter_mode target picker list the current sibling modes
      // (filtered to takeover templates) live, without ModeEditor knowing
      // where the modes list lives.
      getModes: () => this.model.modes,
      // The look pool is config-wide, so the mode editor reads and adds to it
      // rather than owning it. Adding from a mode is the normal way a look
      // gets made now that mode colour lives here - the Lights tab is where
      // they are *managed*, not where they have to be born.
      getLooks: () => this.model.looks || {},
      getFloor: () => this.model.min_flash_period_s,
      api: this.api,
      addLook: (name, effect) => this._addLook(name, effect),
      onLooksChanged: () => {
        this._renderLooks();
        this._markDirty();
      },
    });
    this.modeDetailEl.append(this.detailEditor.el);
  }

  // Swap with the nearest neighbour of the same kind. Order is meaningful
  // only inside a group, so stepping over an intervening takeover mode is
  // what "move up" has to mean for the arrow to match what the user sees.
  _move(mode, delta) {
    const modes = this.model.modes;
    const index = modes.indexOf(mode);
    const nature = this._natureOf(mode);
    let target = index + delta;
    while (target >= 0 && target < modes.length && this._natureOf(modes[target]) !== nature) {
      target += delta;
    }
    if (target < 0 || target >= modes.length) return;
    [modes[index], modes[target]] = [modes[target], modes[index]];
    this._renderModes();
    this._markDirty();
  }

  // --- "active now" marks -------------------------------------------------
  // Which mode answers a press is resolved by the host (see _active_modes in
  // webui.py). The menu only displays that answer; it never recomputes the
  // rules, so the mark cannot drift from the button's real behaviour.

  _startActivePolling() {
    const tick = async () => {
      try {
        const status = await this.api.status();
        this._lastActive = status.active_modes || {};
        this._applyActive(this._lastActive);
      } catch { /* server briefly away - keep the last marks */ }
    };
    clearInterval(this._activeTimer);
    this._activeTimer = setInterval(tick, 2000);
    tick();
  }

  _applyActive(activeModes) {
    const gesturesByMode = new Map();
    for (const [trigger, name] of Object.entries(activeModes)) {
      if (!name) continue;
      const label = GESTURES.find((g) => g.key === trigger)?.label || trigger;
      if (!gesturesByMode.has(name)) gesturesByMode.set(name, []);
      gesturesByMode.get(name).push(label);
    }
    // With unsaved edits the host is still running the config on disk, so a
    // mark here would describe a mode that no longer exists as shown. Say
    // nothing until it is saved rather than something confidently wrong.
    const gesturesFor = (name) => (this.dirty ? [] : (gesturesByMode.get(name) || []));

    for (const [mode, entry] of this.navButtons || []) {
      const gestures = gesturesFor(mode.name);
      entry.dot.hidden = !gestures.length;
      entry.dot.title = gestures.length
        ? `Right now, a ${gestures.join(' or a ')} would be handled by this mode.` : '';
    }
    if (this.detailEditor && this.selectedMode) {
      this.detailEditor.setActive(gesturesFor(this.selectedMode.name));
    }
  }

  // Two groups, and the split is the point rather than tidiness: the button's
  // own vocabulary is edited once and globally, and a named look is a shared
  // appearance any mode can wear. Mode-owned states are edited on the mode -
  // see the note in the return below. Mirrors SYSTEM_LED_STATES in config.py.
  _renderPaletteSection() {
    if (!this.model.led_palette) this.model.led_palette = {};
    if (!this.model.looks) this.model.looks = {};
    this.paletteValidators = [];

    const group = (states) => {
      const wrap = el('div', { className: 'palette-wrap' });
      for (const state of states) {
        if (!this.model.led_palette[state.key]) continue; // server decides the set
        wrap.append(this._renderEffectRow({
          get: () => this.model.led_palette[state.key],
          label: state.label,
          meaning: state.meaning,
          previewState: state.key,
        }));
      }
      return wrap;
    };

    this.looksWrap = el('div', { className: 'palette-wrap' });
    this._renderLooks();

    const add = el('button', { type: 'button', textContent: '+ Add a look' });
    add.addEventListener('click', () => {
      let name = 'look';
      for (let n = 2; this.model.looks[name]; n += 1) name = `look ${n}`;
      this.model.looks[name] = { style: 'breathe', color: '#ff8800', color2: '#000000', period_s: 2 };
      this._renderLooks();
      this._markDirty();
    });

    // Two sections, and the omission is the point. **Mode colours are not
    // here.** A mode's appearance belongs on the mode's own page, or a mode is
    // not modular: you would edit a Pomodoro in one tab and its colour in
    // another, and "change every Pomodoro at once" is a thing almost nobody
    // wants and everybody eventually does by accident.
    //
    // The palette entries for those states still exist in config as the
    // invisible fallback a mode with no named look renders (`base_look` reads
    // them) - only the editor group is gone. Removing the entries as well
    // would leave such a mode with nothing to show.
    return el('div', {}, [
      el('p', { className: 'menu-hint', 'data-help': true, textContent: "The button's own vocabulary - what it looks like when it is idle, listening, thinking, or reporting a result. Saving sends these straight to the device: no reflash, no restart." }),
      group(SYSTEM_LED_STATES),
      el('h3', { className: 'palette-group', textContent: 'Named looks' }),
      el('p', { className: 'menu-hint', 'data-help': true, textContent: 'A shared pool of appearances. Name one here and any mode can wear it, or make one straight from a mode - this is where they all end up either way.' }),
      this.looksWrap,
      add,
    ]);
  }

  /** Put `effect` in the pool under a free name derived from `name`, and
   *  return the name actually used. Deduping here rather than at the call
   *  site is what lets a mode add "Ember" twice without either clobbering the
   *  first one or having to invent a name itself. */
  _addLook(name, effect) {
    if (!this.model.looks) this.model.looks = {};
    const base = (name || 'look').trim() || 'look';
    let chosen = base;
    for (let n = 2; this.model.looks[chosen]; n += 1) chosen = `${base} ${n}`;
    this.model.looks[chosen] = { ...effect };
    this._renderLooks();
    this._markDirty();
    return chosen;
  }

  _renderLooks() {
    clear(this.looksWrap);
    const names = Object.keys(this.model.looks).sort();
    if (!names.length) {
      this.looksWrap.append(el('p', { className: 'menu-hint', textContent: 'No named looks yet.' }));
      return;
    }
    for (const name of names) {
      this.looksWrap.append(this._renderEffectRow({
        get: () => this.model.looks[name],
        label: name,
        meaning: '',
        // Renaming rewrites every mode pointing here, so the pool and the
        // references can never drift into a dangling name from the UI. The
        // Python parser still warns about one, because a hand-edited config
        // can always produce it.
        rename: (next) => {
          if (!next || next === name || this.model.looks[next]) return false;
          this.model.looks[next] = this.model.looks[name];
          delete this.model.looks[name];
          for (const mode of this.model.modes || []) {
            for (const [state, look] of Object.entries(mode.looks || {})) {
              if (look === name) mode.looks[state] = next;
            }
          }
          return true;
        },
        remove: () => {
          delete this.model.looks[name];
          // Deliberately leaves the references. The mode editor shows a
          // "(missing)" entry and the parser warns, which is more honest than
          // silently changing what several modes look like.
          this._renderLooks();
          this._markDirty();
        },
      }));
    }
  }

  // One control for every colour in the app - see colorEngine.js. This is a
  // thin adapter: the Lights tab's own concerns are marking the config dirty
  // and collecting validators, and neither of those belongs in the engine.
  _renderEffectRow(spec) {
    const editor = createLookEditor({
      get: spec.get,
      onChange: () => this._markDirty(),
      floor: this.model?.min_flash_period_s,
      api: this.api,
      label: spec.label,
      meaning: spec.meaning,
      previewState: spec.previewState,
      rename: spec.rename && ((next) => {
        if (!spec.rename(next)) return false;
        this._renderLooks();
        this._markDirty();
        return true;
      }),
      onRemove: spec.remove,
    });
    this.paletteValidators.push(editor.validate);
    return editor.el;
  }

  _renderSettingsSection() {
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
    return wrap;
  }

  // Only the selected mode has a live ModeEditor; every other mode is
  // validated through a throwaway instance built - and never attached to the
  // document - purely to run its validators against the real mode object.
  // Widget validate() functions all read from the data object, not the DOM,
  // so this is exactly as correct as validating an on-screen card.
  _collectErrors() {
    const errors = [];
    for (const mode of this.model.modes) {
      const editor = (mode === this.selectedMode && this.detailEditor)
        ? this.detailEditor
        : new ModeEditor(mode, {
          getModes: () => this.model.modes,
          getLooks: () => this.model.looks || {},
        });
      const label = mode.name || '(unnamed mode)';
      for (const err of editor.validate()) errors.push(`${label}: ${err}`);
    }
    for (const validate of [...this.settingValidators, ...(this.paletteValidators || [])]) {
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
      // A save changes the active scene's mode count and can introduce a
      // setting that needs a restart, both of which the bar reports.
      this.sceneBar?.load();
      // Say which file took the edit when it wasn't config.json: with a scene
      // active, "Saved" without a name is the one ambiguous word here.
      const where = res.scene ? ` to scene "${res.scene}"` : '';
      const restart = res.needs_restart?.length
        ? `\nRestart the service to apply: ${res.needs_restart.join(', ')}.` : '';
      this._showResult(
        res.warnings.length || restart ? 'warn' : 'ok',
        (res.warnings.length
          ? `Saved${where} with warnings:\n${res.warnings.join('\n')}`
          : `Saved${where} & applied.`) + restart,
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

// Composition root: wire a ConfigMenu to its mount points if present.
const mounts = {
  modes: document.getElementById('panel-modes'),
  lights: document.getElementById('panel-lights'),
  device: document.getElementById('panel-device'),
  bar: document.getElementById('menu-bar'),
  // Optional: no scene bar in the page (the standalone editor) simply means
  // no scene switching, not a broken menu.
  scenes: document.getElementById('scene-bar'),
};
if (mounts.modes) new ConfigMenu(mounts).load();
