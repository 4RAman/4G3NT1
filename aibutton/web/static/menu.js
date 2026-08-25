// Orchestrates the configuration menu. Loads the effective config, edits a
// working copy, and renders into four mount points the page's tabs already
// gate the visibility of - Modes, Lights, Device settings, plus a shared
// sticky bar for Save/Check/Revert. It owns the modes list operations (add,
// remove, reorder, which one is selected) but delegates per-mode editing to
// ModeEditor and per-field editing to the widget factory.

import { el, clear } from './dom.js';
import { ConfigApi } from './api.js';
import {
  ACTIONS, ACTION_BY_TYPE, BUILTIN_MODES, GESTURES, LED_STATE_BY_KEY,
  SYSTEM_LED_STATES, MODE_GROUPS, SETTINGS_GROUPS, TEMPLATE_BY_TYPE,
  describeAction, describeEffect, describeTemplate,
} from './schema.js';
import { ModeEditor } from './modeEditor.js';
import { SceneBar } from './scenes.js';
import { createField } from './widgets.js';
import { createLookEditor } from './colorEngine.js';
import { paint as applySwatch, unpaint } from './ledPreview.js';

export class ConfigMenu {
  /** @param {{modes: Element, lights: Element, device: Element, bar: Element, scenes?: Element}} mounts */
  constructor(mounts, api = new ConfigApi()) {
    this.mounts = mounts;
    this.api = api;
    this.model = null; // working copy of the effective config
    this.dirty = false;
    this.selectedMode = null; // the mode object shown in the detail pane
    // Which named look has its editor open, if any. One at a time: the pool
    // is a list you scan, and every entry expanded at once is the state this
    // replaced.
    this._expandedLook = null;
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

    this.mounts.modes.append(
      this._renderPrimer(), this._renderModesLayout(), this._renderActionPoolSection(),
    );
    this.mounts.lights.append(this._renderPaletteSection());
    this.mounts.device.append(this._renderSettingsSection());

    this.statusEl = el('span', { className: 'menu-status' });
    this.resultEl = el('pre', { className: 'menu-result' });
    const bar = (text, className, onclick) => el('button', { type: 'button', className, textContent: text, onclick });
    this.mounts.bar.append(
      bar('Save', 'primary', () => this.save()),
      bar('Check', '', () => this.check()),
      bar('Revert', '', () => this.load()),
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
        line('A mode: instructions for what each press (short, long, double) does.'),
        line("No manual picking - the button scans your everyday modes top-down and uses the first one that's on now and has this press set."),
        line('Some modes take over instead: once started, they own every press until you leave. Listed separately below, with how to start and exit each.'),
      ]),
    ]);
  }

  // Ready-made modes. Each drops in a complete, valid mode you then edit -
  // faster than assembling a Pomodoro field by field, and it doubles as the
  // answer to "what can this thing do?".
  _renderBuiltins() {
    const blurb = el('span', { className: 'menu-hint builtin-blurb' });
    const picker = el('select', {
      className: 'inp builtin-pick',
      onchange: () => {
        const chosen = BUILTIN_MODES.find((b) => b.id === picker.value);
        if (chosen) {
          this._addMode(this._uniquelyNamed(chosen.mode()));
          picker.value = '';  // back to the prompt entry: nothing stays selected
        }
        // Re-read after that reset - the blurb describes what is selected now.
        blurb.textContent = BUILTIN_MODES.find((b) => b.id === picker.value)?.blurb || '';
      },
    }, [
      el('option', { value: '', textContent: 'Add a ready-made mode…' }),
      ...BUILTIN_MODES.map((b) => el('option', { value: b.id, textContent: b.label })),
    ]);
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
    const addBtn = el('button', {
      type: 'button', className: 'add-mode', textContent: '+ Add mode',
      onclick: () => this._addMode(this._defaultMode()),
    });

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
        const swatch = el('span', { className: 'mode-nav-swatch' });
        const repaint = () => {
          const look = this._modeLook(mode);
          swatch.classList.toggle('empty', !look);
          swatch.title = look
            ? `While it is running: ${describeEffect(look)}`
            : "No colour of its own - it runs the button's own lights.";
          // Unregistered explicitly, not just restyled: the ticker only
          // forgets a node that has left the document, so a mode that just
          // lost its look would keep being repainted in it.
          if (look) applySwatch(swatch, look);
          else unpaint(swatch);
        };
        repaint();
        this.navButtons.set(mode, { dot, nameEl, summaryEl, repaint });
        groupEl.append(el('button', {
          type: 'button',
          className: 'mode-nav-item' + (mode === this.selectedMode ? ' selected' : ''),
          onclick: () => this._renderModes(mode),
        }, [dot, swatch, nameEl, summaryEl]));
      }
      this.modeNavEl.append(groupEl);
    }
  }

  /**
   * The colour a mode runs in, or null if it has none of its own.
   *
   * **Mirrors `main.app_look`** - the resolution a launcher already does to
   * paint the app it is about to offer: the template's first LED state, the
   * mode's named look for it, falling back to that state's palette entry. Same
   * answer here as on the button, which is the whole point of showing it.
   *
   * Null for a template that owns no LED state at all (an everyday actions
   * mode, a launcher, hot/cold, a signal): those wear the button's own
   * vocabulary or compute every frame, so there is no one colour to show and
   * inventing one would be worse than the gap.
   */
  _modeLook(mode) {
    const states = TEMPLATE_BY_TYPE[mode.template]?.ledStates || [];
    if (!states.length) return null;
    const named = mode.looks?.[states[0]];
    return (named && this.model.looks?.[named])
      || this.model.led_palette?.[states[0]]
      || null;
  }

  /** Repaint every nav swatch. Called when a *pool* look changes, since that
   *  is an edit on another tab that several modes may be wearing. */
  _repaintNavSwatches() {
    for (const [, entry] of this.navButtons || []) entry.repaint?.();
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
          entry.repaint();
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
      // arrows - a takeover mode is found by name, and offering to reorder it
      // would imply a priority it does not have.
      canReorder: this._natureOf(mode) === 'ambient',
      // The three pools below are config-wide, so the mode editor reads them
      // through a handler rather than owning them or knowing where they live
      // (Dependency Inversion). Adding a look from a mode is the normal path
      // now that mode colour lives there - the Lights tab is where looks are
      // *managed*, not where they have to be born.
      getModes: () => this.model.modes,
      getLooks: () => this.model.looks || {},
      getActions: () => this.model.actions || {},
      getFloor: () => this.model.min_flash_period_s,
      api: this.api,
      addLook: (name, effect) => this._addLook(name, effect),
      onLooksChanged: () => {
        this._renderLooks();
        this._repaintNavSwatches();
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
    // Reset with the section, not appended to: these close over elements that
    // are about to be thrown away, and keeping the old ones would collect a
    // validator per re-render for nodes nobody can see.
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
          // What makes "a named look" an option in this row's Style dropdown
          // (TODO 36f). Handed in rather than reached for, so the engine never
          // learns where a state look is stored - the same seam the pool and
          // the mode editor already use.
          namedLook: this._stateLookHandle(state),
        }));
      }
      return wrap;
    };

    this.looksWrap = el('div', { className: 'palette-wrap looks-list' });
    this._renderLooks();

    const add = el('button', {
      type: 'button', textContent: '+ Add a look',
      onclick: () => {
        let name = 'look';
        for (let n = 2; this.model.looks[name]; n += 1) name = `look ${n}`;
        this.model.looks[name] = { style: 'breathe', color: '#ff8800', color2: '#000000', period_s: 2 };
        this._expandedLook = name;
        this._renderLooks();
        this._markDirty();
      },
    });

    // Two sections, and the omission is the point: **mode colours are not
    // here**, they are on the mode's own page - CLAUDE.md's "the Lights tab is
    // the button's vocabulary" invariant, which also says why their palette
    // entries stay in config even though this stopped editing them.
    return el('div', {}, [
      el('p', { className: 'menu-hint', 'data-help': true, textContent: "The button's own vocabulary - what it looks like when it is idle, listening, thinking, or reporting a result. Saving sends these straight to the device: no reflash, no restart." }),
      group(SYSTEM_LED_STATES),
      el('h3', { className: 'palette-group', textContent: 'Named looks' }),
      el('p', { className: 'menu-hint', 'data-help': true, textContent: 'A shared pool of appearances. Name one here and any mode - or any of the states above - can wear it, or make one straight from a mode. This is where they all end up either way.' }),
      this.looksWrap,
      add,
    ]);
  }

  /**
   * How one system state names a look, as the four calls colorEngine needs.
   *
   * **The palette entry underneath does not go away, and that is the design**
   * (TODO 36a) - CLAUDE.md's "a stop list is the rich form; a palette entry is
   * the fallback form". The engine folds it into a drawer rather than dropping
   * it, which is what lets one row answer both "what does this state look
   * like" and "what does it look like with nothing connected".
   */
  _stateLookHandle(state) {
    return {
      get: () => (this.model.state_looks || {})[state.key] || '',
      set: (name) => {
        if (!this.model.state_looks) this.model.state_looks = {};
        if (name) this.model.state_looks[state.key] = name;
        else delete this.model.state_looks[state.key];
        this._markDirty();
      },
      names: () => Object.keys(this.model.looks || {}).sort(),
      look: (name) => (this.model.looks || {})[name],
    };
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

  /**
   * The pool as a *list*: one line each, and the colour editor only for the
   * one being edited.
   *
   * Every entry used to be expanded at once, which made a pool of six looks a
   * page of six full colour editors and turned "which one is Ember?" into a
   * scrolling problem. A named look is identified by its name and its light,
   * so those are the line - the editing is a click away, and only one is open
   * at a time because two open editors is the state this replaced.
   */
  _renderLooks() {
    clear(this.looksWrap);
    const names = Object.keys(this.model.looks).sort();
    if (!names.length) {
      this.looksWrap.append(el('p', { className: 'menu-hint', textContent: 'No named looks yet.' }));
      return;
    }
    for (const name of names) this.looksWrap.append(this._renderLookEntry(name));
  }

  /** One pool entry: the line, plus its editor when it is the open one. */
  _renderLookEntry(name) {
    const look = this.model.looks[name];
    const open = this._expandedLook === name;

    const swatch = el('span', { className: 'palette-swatch' });
    applySwatch(swatch, look);

    const summary = el('span', { className: 'palette-summary', textContent: describeEffect(look) });
    const usedBy = this._looksUsedBy(name);

    const line = el('div', { className: 'look-line' }, [
      swatch,
      el('span', { className: 'palette-name', textContent: name }),
      usedBy.length
        ? el('span', {
          className: 'palette-meaning',
          textContent: `worn by ${usedBy.join(', ')}`,
          title: 'Editing this look changes it everywhere it is worn.',
        })
        : el('span', { className: 'palette-meaning', textContent: 'not used yet' }),
      summary,
      el('button', {
        type: 'button', className: 'mini',
        textContent: open ? 'Done' : 'Edit',
        onclick: () => {
          this._expandedLook = open ? null : name;
          this._renderLooks();
        },
      }),
      el('button', {
        type: 'button', className: 'mini', textContent: 'Duplicate',
        title: 'A copy under a new name, pointing at nothing - so editing it '
          + 'cannot change what anything already wears.',
        onclick: () => {
          this._expandedLook = this._addLook(name, structuredClone(look));
          this._renderLooks();
        },
      }),
      el('button', {
        type: 'button', className: 'mini danger', textContent: 'Delete',
        // Deliberately leaves the references dangling - CLAUDE.md's rule for
        // a deleted pool entry: "(missing)" wherever it was worn and a parser
        // warning beat quietly changing what several modes look like.
        onclick: () => {
          delete this.model.looks[name];
          if (this._expandedLook === name) this._expandedLook = null;
          this._renderLooks();
          this._renderModes();
          this._markDirty();
        },
      }),
    ]);

    if (!open) return el('div', { className: 'look-entry' }, [line]);

    const editor = this._renderEffectRow({
      get: () => this.model.looks[name],
      // No label in the head: the line above already carries the name, and the
      // engine's own rename box is where a rename happens.
      label: name,
      meaning: '',
      // Pool looks may be stop lists; palette entries may not (they ship
      // to the device), which is why the flag is here and not in the
      // palette section's spec above.
      allowSequence: true,
      openPresets: true,
      // Renaming rewrites every mode pointing here, so the pool and the
      // references can never drift into a dangling name from the UI.
      rename: (next) => {
        if (!next || next === name || this.model.looks[next]) return false;
        this.model.looks[next] = this.model.looks[name];
        delete this.model.looks[name];
        for (const mode of this.model.modes || []) {
          for (const [state, worn] of Object.entries(mode.looks || {})) {
            if (worn === name) mode.looks[state] = next;
          }
        }
        // The button's own states name looks too (TODO 36a), and they are
        // the half that is easy to forget: they live on the config root
        // rather than on a mode, so a rename that only walked the modes
        // would leave the Lights tab pointing at a name nothing answers to.
        for (const [state, worn] of Object.entries(this.model.state_looks || {})) {
          if (worn === name) this.model.state_looks[state] = next;
        }
        this._expandedLook = next;
        return true;
      },
    });
    return el('div', { className: 'look-entry open' }, [line, editor]);
  }

  /** Where `name` is worn, in the words the user chose - a mode's name, or a
   *  system state's label. What makes "editing this changes it everywhere"
   *  visible before the edit rather than after it. */
  _looksUsedBy(name) {
    const worn = [];
    for (const [state, look] of Object.entries(this.model.state_looks || {})) {
      if (look === name) worn.push(LED_STATE_BY_KEY[state]?.label || state);
    }
    for (const mode of this.model.modes || []) {
      if (Object.values(mode.looks || {}).includes(name)) worn.push(mode.name || '(unnamed)');
    }
    return worn;
  }

  /**
   * The named-action pool (TODO 30a) - `looks` again, for actions.
   *
   * **Tinker-tier by the whole item's design, not by timidity.** A novice does
   * not think "I want to make an action", they think "I want it to count
   * cigarettes"; starting from an action and hunting for somewhere to attach
   * it is backwards. So this powers the recipe-shaped path without appearing
   * in it. On the Modes tab rather than a tab of its own, because concept
   * count is the enemy and an action is a thing a *gesture* has.
   */
  _renderActionPoolSection() {
    this.actionsWrap = el('div', { className: 'palette-wrap' });
    this._renderActionPool();

    const add = el('button', {
      type: 'button', textContent: '+ Add a named action',
      onclick: () => {
        if (!this.model.actions) this.model.actions = {};
        let name = 'action';
        for (let n = 2; this.model.actions[name]; n += 1) name = `action ${n}`;
        this.model.actions[name] = { action: 'log', event: '' };
        this._renderActionPool();
        this._markDirty();
      },
    });

    return el('div', { className: 'action-pool', 'data-tier': 'tinker' }, [
      el('h3', { className: 'palette-group', textContent: 'Named actions' }),
      el('p', { className: 'menu-hint', 'data-help': true, textContent: 'A shared pool of actions. Name one here and any gesture can point at it by name, so the three gestures that all send the same webhook are one thing to edit rather than three. Naming is optional - an action used once is better written straight on the gesture.' }),
      this.actionsWrap,
      el('div', { className: 'add-row' }, [add]),
    ]);
  }

  _renderActionPool() {
    clear(this.actionsWrap);
    const pool = this.model.actions || {};
    const names = Object.keys(pool).sort();
    if (!names.length) {
      this.actionsWrap.append(el('p', { className: 'menu-hint', textContent: 'No named actions yet.' }));
      return;
    }
    for (const name of names) this.actionsWrap.append(this._renderActionRow(name));
  }

  /** One pool entry: its name, what it is, and the two edits a pool needs. */
  _renderActionRow(name) {
    // Renaming rewrites every gesture pointing here, so the pool and its
    // references can never drift into a dangling name *from the UI*.
    const nameInput = el('input', {
      type: 'text', className: 'inp', value: name,
      onchange: () => {
        const next = nameInput.value.trim();
        if (!next || next === name || this.model.actions[next]) {
          nameInput.value = name;  // refused: taken, empty, or unchanged
          return;
        }
        this.model.actions[next] = this.model.actions[name];
        delete this.model.actions[name];
        for (const mode of this.model.modes || []) {
          for (const gesture of GESTURES) {
            if (mode[gesture.key] === name) mode[gesture.key] = next;
          }
          for (const state of mode.states || []) {
            if (state && state.action === name) state.action = next;
          }
        }
        this._renderActionPool();
        this._renderModes();
        this._markDirty();
      },
    });

    const summary = el('span', {
      className: 'menu-hint',
      textContent: describeAction(this.model.actions[name]),
    });

    const edit = el('div', { className: 'gesture-fields' });
    const buildFields = () => {
      clear(edit);
      const action = this.model.actions[name];
      const descriptor = action && ACTION_BY_TYPE[action.action];
      if (!descriptor) return;
      for (const spec of descriptor.fields) {
        const ctx = {
          getModes: () => this.model.modes, api: this.api, rebuild: buildFields,
        };
        const field = createField(spec, action, () => {
          summary.textContent = describeAction(action);
          this._markDirty();
        }, ctx);
        edit.append(field.el);
      }
    };

    const kind = el('select', {
      className: 'inp',
      onchange: () => {
        this.model.actions[name] = ACTION_BY_TYPE[kind.value].defaults();
        buildFields();
        summary.textContent = describeAction(this.model.actions[name]);
        this._markDirty();
      },
    }, ACTIONS.map((a) => el('option', { value: a.type, textContent: a.label })));
    kind.value = this.model.actions[name].action || 'log';

    const remove = el('button', {
      type: 'button', textContent: 'Delete',
      // Leaves the references dangling, exactly as deleting a look does.
      onclick: () => {
        delete this.model.actions[name];
        this._renderActionPool();
        this._renderModes();
        this._markDirty();
      },
    });

    buildFields();
    return el('div', { className: 'gesture-row' }, [
      el('div', { className: 'gesture-head' }, [nameInput, kind, remove]),
      summary,
      edit,
    ]);
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
      allowSequence: spec.allowSequence,
      openPresets: spec.openPresets,
      namedLook: spec.namedLook,
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
          getActions: () => this.model.actions || {},
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
