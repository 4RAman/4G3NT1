// Orchestrates the configuration menu. Loads the effective config, edits a
// working copy, and renders into four mount points the page's tabs already
// gate the visibility of - Modes, Lights, Device settings, plus a shared
// sticky bar for Save/Check/Revert. It owns the modes list operations (add,
// remove, reorder, which one is selected) but delegates per-mode editing to
// ModeEditor and per-field editing to the widget factory.

import { el, clear } from './dom.js';
import { readFlag, writeFlag } from './prefs.js';
import { ConfigApi } from './api.js';
import {
  ACTIONS, ACTION_BY_TYPE, BUILTIN_MODES, GESTURES, LED_STATE_BY_KEY,
  SYSTEM_LED_STATES, MENU_TEMPLATES, MODE_GROUPS, REFLEX_ACTIONS, REFLEX_OPS,
  SETTINGS_GROUPS, TEMPLATES,
  TEMPLATE_BY_TYPE, danglingTargets, describeAction, describeActivation,
  describeEffect, describeReflex, describeTemplate, findEntryPoints, modeLook,
  reachableModes, STARTER_BY_KEY, actionRefs, actionUsedBy, readoutStat,
  startedBy,
} from './schema.js';
import { ModeEditor } from './modeEditor.js';
import { SceneBar } from './scenes.js';
import { createField } from './widgets.js';
import { createLookEditor } from './colorEngine.js';
// The one home for how this page writes a duration, a number and a day
// (CLAUDE.md) - the Events table and an app's readout already write them this
// way, and a nav line that rounded differently would be a third answer.
import { countOf, fmtDay, fmtDuration, fmtValue } from './format.js';
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
    // Same idea, one state at a time - see _renderStateRow (TODO 54).
    this._expandedState = null;
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
      if (!Array.isArray(this.model.reflexes)) this.model.reflexes = [];
      this.dirty = false;
      this.warningDetails = data.warning_details || [];
      this._render(data.warnings || []);
      this._loadEventStats();
    } catch (err) {
      for (const mount of this._ownMounts()) clear(mount);
      this.mounts.modes.append(el('p', {
        className: 'menu-result err', textContent: `Could not load configuration: ${err.message}`,
      }));
    }
  }

  /**
   * The live half of a nav row's line (TODO 101), fetched once and applied by
   * re-rendering rather than by patching text in place.
   *
   * **Deliberately not awaited.** The config is what the page is for; the
   * numbers are a garnish, and a slow or missing log must not hold the editor
   * closed. So this runs beside the render and the nav simply gains a clause
   * when it lands.
   *
   * **And it is optional at the API, which is the whole degradation.** The
   * offline editor's `FileApi` has no `eventSummary` - there is no service and
   * no log to summarise - so the check is `typeof`, the promise never happens,
   * and every row keeps the line it computed from the config alone.
   */
  _loadEventStats() {
    if (typeof this.api.eventSummary !== 'function') return;
    this.api.eventSummary().then((data) => {
      this.eventStats = data.rows || [];
      if (this.modeNavEl) this._renderModeNav();
    }).catch(() => { /* a log that will not answer costs the nav one clause */ });
  }

  /** "12 runs · last Aug 12 · best 214 ms", or null. The numbers come from
   *  `readoutStat`, which is pure and knows nothing about how they read. */
  _statLine(mode) {
    const stat = readoutStat(mode, this.eventStats);
    if (!stat) return null;
    // "so far" earns its four characters: a reaction timer's config line
    // already says "3 attempts" (the rounds it is set to) and this one says
    // how many have been played. Two numbers under one noun, on one row, is
    // exactly the ambiguity a live line was supposed to remove.
    const parts = [`${countOf(stat.count, stat.noun)} so far`];
    if (stat.last) parts.push(`last ${fmtDay(stat.last)}`);
    if (stat.best !== null) {
      const best = stat.bestIsDuration
        ? fmtDuration(stat.best)
        : `${fmtValue(stat.best)}${stat.unit ? ` ${stat.unit}` : ''}`;
      parts.push(`best ${best}`);
    }
    return parts.join(' · ');
  }

  _markDirty() {
    this.dirty = true;
    this._updateStatus();
    // What starts a takeover mode lives in *other* modes' gestures, so an
    // edit anywhere can change the open card's "to start it" line - including
    // whether it is reachable at all.
    this.detailEditor?.refreshExplainers();
    // The App page is the same fact at system scale, so it goes stale for the
    // same reasons and on the same edits - renaming a mode, repointing a
    // gesture, emptying a launcher's list. Rebuilt here rather than on a
    // narrower hook because *every* model change reaches it, and a page
    // reporting yesterday's reachability is worse than no page.
    this._refreshApps();
    this._applyActive(this._lastActive || {});
  }

  /** The mounts this menu draws into, and therefore the only ones it may
   *  clear. The scene bar renders into a mount of its own on its own
   *  schedule - wiping it here would erase whatever it had just drawn. */
  _ownMounts() {
    const owned = [this.mounts.modes, this.mounts.lights, this.mounts.device, this.mounts.bar];
    if (this.mounts.apps) owned.push(this.mounts.apps);
    // Optional like the rest: without it the two pools stay in the Modes
    // panel, which is where they were before TODO 102 and is what keeps the
    // offline editor whole.
    if (this.mounts.actions) owned.push(this.mounts.actions);
    // Optional, and absent in the offline editor - see _renderModesLayout.
    if (this.mounts.nav) owned.push(this.mounts.nav);
    return owned;
  }

  _render(warnings = []) {
    for (const mount of this._ownMounts()) clear(mount);
    if (this.selectedMode && !this.model.modes.includes(this.selectedMode)) this.selectedMode = null;

    // The named-action pool and the reactions are one page (TODO 102): a
    // reaction is a circumstance with an action attached, and its whole
    // vocabulary of consequences *is* that pool, so one is the ingredient
    // list for the other. Where they land is the mount's answer, not this
    // method's - absent, they stay under the modes, one section fewer.
    const pools = [this._renderActionPoolSection(), this._renderReflexSection()];
    this.mounts.modes.append(this._renderPrimer(), this._renderModesLayout());
    (this.mounts.actions || this.mounts.modes).append(...pools);
    if (this.mounts.apps) this.mounts.apps.append(this._renderAppsSection());
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

  // The three sentences that answer "how does it know what I meant?" -
  // tutorial content, so it rides on the page's Tips toggle (help.js) rather
  // than sitting on screen permanently.
  _renderPrimer() {
    const line = (text) => el('li', { className: 'primer-line', textContent: text });
    return el('div', { className: 'primer', 'data-help': true }, [
      el('p', { className: 'primer-lead', textContent: 'How this button decides what a press does' }),
      el('ol', { className: 'primer-list' }, [
        line('A menu: what one press (short, long, double) does while the button is just sitting there.'),
        line("Nothing to pick from a list - the button scans your menus top-down and fires the first one that's awake and has that press set."),
        line('An app is the other half: launch one and it owns every press until you leave. Listed separately below, with how to start and exit each.'),
      ]),
    ]);
  }

  /** Append `mode`, select it for editing, and flag unsaved changes. */
  _addMode(mode) {
    this.model.modes.push(mode);
    this._renderModes(mode);
    // Adding one from the side panel has to land you in its editor, or the
    // only feedback is a new line appearing in a list you are not looking at.
    this._showModesPanel();
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
      name: 'New menu',
      template: 'actions',
      activation: { type: 'always' },
      ...TEMPLATE_BY_TYPE.actions.defaults(),
    };
  }

  /** A mode's nature drives which group it lands in.
   *
   * **A template this page has never heard of has no nature, and saying it is
   * 'ambient' was a lie with a cost** (TODO 107). It filed the mode under
   * Menus, where a scheduled Notice looked exactly like a gesture map someone
   * had mis-added - which is what a stale `/static` module graph did to every
   * alarm the day `notice` was added. Unknown is its own answer now, and
   * `_membersOf` gives it its own group rather than guessing. */
  _natureOf(mode) {
    return TEMPLATE_BY_TYPE[mode?.template]?.nature || 'unknown';
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
    // A menu is a gesture map you write here and now; installing an app is a
    // choice between twelve of them, with ready-made versions of several, and
    // that belongs on the Apps tab rather than under a dropdown at the bottom
    // of a list (TODO 49). Installing used to have a second door here too
    // ("Manage apps →"), but the Apps tab it pointed at now exists in both
    // shells (TODO 82) - the served page's `.shell-nav` and the offline
    // editor's own `.tab-bar` - so the second door onto the same room is gone
    // rather than kept.
    const addMenu = el('button', {
      type: 'button', className: 'add-mode', textContent: '+ Add menu',
      onclick: () => this._addMode(this._defaultMode()),
    });
    const navCol = el('div', { className: 'mode-nav-col' }, [
      this.modeNavEl,
      el('div', { className: 'add-row' }, [addMenu]),
    ]);

    this._renderModes();

    // `mounts.nav` is the page's own side panel: the mode list is the primary
    // navigation there, so it sits outside the panel it drives and survives a
    // switch to Events or Lights. Optional on purpose - the offline editor is
    // the menu with no shell around it, and with nowhere to put the nav it
    // keeps the master/detail split inside the tab, exactly as before.
    if (this.mounts.nav) {
      this.mounts.nav.append(navCol);
      return el('div', { className: 'mode-layout detail-only' }, [this.modeDetailEl]);
    }
    return el('div', { className: 'mode-layout' }, [navCol, this.modeDetailEl]);
  }

  /** Ask the page to show the modes panel. A mode in the side panel is only
   *  navigation if selecting one brings its editor into view; the shell owns
   *  which panel is up, so this asks rather than reaching for it. Ignored
   *  where nothing is listening (the offline editor, where the nav is already
   *  inside the panel). */
  _showModesPanel() {
    document.dispatchEvent(new CustomEvent('button:show-panel', { detail: 'modes' }));
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

  /** Rebuild the App page in place. No-op where there is no mount (the
   *  offline editor) and before the first render. */
  _refreshApps() {
    if (!this.mounts.apps || !this.model) return;
    clear(this.mounts.apps);
    this.mounts.apps.append(this._renderAppsSection());
  }

  // --- the App page ------------------------------------------------------
  // Every app the button has, in one of three states, and the only place that
  // answers "can anything actually get to this?" - a question no single mode's
  // card can answer, because reachability runs through other modes (TODO 49).

  _renderAppsSection() {
    const wrap = el('div', { className: 'apps-page' });
    const reached = reachableModes(this.model.modes, this.model.actions, this.model.reflexes);
    const dangling = danglingTargets(this.model.modes, this.model.actions, this.model.reflexes);

    const installed = [];
    const available = [];
    for (const descriptor of TEMPLATES) {
      if (descriptor.nature !== 'takeover') continue;  // a gesture map is not an app
      const copies = this.model.modes.filter((m) => m && m.template === descriptor.type);
      (copies.length ? installed : available).push({ descriptor, copies });
    }

    wrap.append(el('p', { className: 'apps-lead', 'data-help': true, textContent:
      'Every app the button can run. Installed ones live in the list on the '
      + 'left; installing one here adds it there, ready to edit.' }));

    // No page-wide stranded-app count here (TODO 56) - it read as a wall of
    // alarm above every app, for someone who installed one thing and does not
    // know or care that three others exist. The same diagnosis already sits
    // on the app it is about: the "Unreachable" pill (_appStatus) and, per
    // copy, exactly why (_howReached).
    for (const [target, from] of dangling) {
      wrap.append(el('p', { className: 'apps-warn', textContent:
        `${from.join(', ')} opens “${target}”, and no mode has that name. `
        + 'Install it below, or point it somewhere else.' }));
    }

    wrap.append(this._appsGroup('Installed', installed, reached, true));
    wrap.append(this._appsGroup('Available', available, reached, false));
    return wrap;
  }

  _appsGroup(title, entries, reached, isInstalled) {
    const group = el('div', { className: 'apps-group' }, [
      el('div', { className: 'apps-group-title', textContent: `${title} (${entries.length})` }),
    ]);
    if (!entries.length) {
      group.append(el('p', { className: 'empty', textContent:
        isInstalled ? 'Nothing installed yet.' : 'Everything is installed.' }));
      return group;
    }
    for (const entry of entries) group.append(this._appCard(entry, reached, isInstalled));
    return group;
  }

  _appCard({ descriptor, copies }, reached, isInstalled) {
    const swatch = el('span', { className: 'apps-swatch' });
    // An app with no LED state of its own gets an empty ring rather than an
    // invented colour - the same rule the mode list follows.
    const look = copies.length
      ? this._modeLook(copies[0])
      : (this.model.led_palette || {})[(descriptor.ledStates || [])[0]] || null;
    swatch.classList.toggle('empty', !look);
    if (look) applySwatch(swatch, look); else unpaint(swatch);

    const head = el('div', { className: 'apps-head' }, [
      swatch,
      el('span', { className: 'apps-name', textContent: descriptor.label }),
      this._appStatus(copies, reached, isInstalled),
    ]);
    const card = el('div', { className: 'apps-card' }, [
      head,
      el('p', { className: 'apps-about', textContent: descriptor.about || '' }),
    ]);

    for (const mode of copies) {
      const ok = reached.has(mode);
      card.append(el('div', { className: `apps-copy${ok ? '' : ' unreachable'}` }, [
        el('button', {
          type: 'button', className: 'apps-copy-name', textContent: mode.name || '(unnamed)',
          onclick: () => { this._renderModes(mode); this._showModesPanel(); },
        }),
        el('span', { className: 'apps-copy-how', textContent: this._howReached(mode, ok) }),
      ]));
    }
    card.append(this._installRow(descriptor, copies.length));
    return card;
  }

  _appStatus(copies, reached, isInstalled) {
    if (!isInstalled) return el('span', { className: 'apps-pill available', textContent: 'Available' });
    const live = copies.filter((m) => reached.has(m)).length;
    if (!live) return el('span', { className: 'apps-pill stranded', textContent: 'Unreachable' });
    if (live < copies.length) {
      return el('span', { className: 'apps-pill partial', textContent: `${live} of ${copies.length} reachable` });
    }
    return el('span', {
      className: 'apps-pill installed',
      textContent: copies.length > 1 ? `Installed (${copies.length})` : 'Installed',
    });
  }

  /** Why this one is reachable, or the two ways to fix it if it is not. Said
   *  per copy rather than per app, because one alarm can be wired and another
   *  stranded and the app-level pill can only average them. */
  _howReached(mode, ok) {
    if (!ok) return 'nothing opens it - bind a gesture to "Launch an app", or add a launcher';
    if (this._isScheduled(mode)) return describeActivation(mode.activation);
    const entries = findEntryPoints(
      mode, this.model.modes, this.model.actions, this.model.reflexes,
    );
    if (entries.length) return entries.join(', or ');
    const launcher = this.model.modes.find((m) => m && m.template === 'launcher');
    return launcher ? `offered by ${launcher.name || 'the launcher'}` : 'reachable';
  }

  /** Install, or add another. The ready-made presets live here now rather than
   *  under the mode list: installing an app and choosing which *kind* of it you
   *  want are one decision, and they used to be two controls in two places. */
  _installRow(descriptor, installedCount) {
    const presets = BUILTIN_MODES.filter((b) => b.mode().template === descriptor.type);
    const row = el('div', { className: 'apps-install' });
    const add = (mode) => this._addMode(this._uniquelyNamed(mode));

    row.append(el('button', {
      type: 'button', className: 'mini',
      textContent: installedCount ? '+ Add another' : '+ Install',
      onclick: () => add({
        name: descriptor.label,
        template: descriptor.type,
        activation: { type: (descriptor.allowedActivations || ['manual'])[0] },
        ...descriptor.defaults(),
      }),
    }));

    if (!presets.length) return row;
    const picker = el('select', {
      className: 'inp apps-preset',
      onchange: () => {
        const chosen = presets.find((b) => b.id === picker.value);
        picker.value = '';
        if (chosen) add(chosen.mode());
      },
    }, [
      el('option', { value: '', textContent: presets.length > 1 ? 'or a ready-made one…' : 'or ready-made…' }),
      ...presets.map((b) => el('option', { value: b.id, textContent: `${b.label} - ${b.blurb}` })),
    ]);
    row.append(picker);
    return row;
  }

  /** Which modes a nav group lists.
   *
   * **A mode is listed once now** (TODO 101). It used to appear twice on
   * purpose (48a): the groups are questions, not boxes, and an alarm answered
   * two of them - a clock starts it, *and* it is an app while it runs - so it
   * sat under both. The starter glyph answers the second question **on the
   * row**, which is strictly better: one line says what it is and what sets it
   * off, and the list is shorter by every scheduled app you own.
   *
   * So the Reactions group holds reactions and nothing else. `_isScheduled`
   * survives because `startedBy` asks the same question of the descriptor -
   * a new template a clock starts still needs no edit here.
   */
  _membersOf(group) {
    const isMenu = (m) => MENU_TEMPLATES.includes(m?.template)
      || this._natureOf(m) === 'ambient';
    if (group.key === 'unknown') {
      return this.model.modes.filter((m) => this._natureOf(m) === 'unknown');
    }
    if (group.key === 'menus') return this.model.modes.filter(isMenu);
    return this.model.modes.filter(
      (m) => this._natureOf(m) === 'takeover' && !isMenu(m),
    );
  }

  _isScheduled(mode) {
    return TEMPLATE_BY_TYPE[mode?.template]?.startedBy === 'schedule';
  }

  /** Each group folds independently, remembered per browser
   *  ([prefs.js](aibutton/web/static/prefs.js)) rather than in config - it is
   *  a view preference, and a panel setting in config.json does not survive a
   *  Save. Asked for at eleven modes, where the side panel ran longer than
   *  the screen and the group you were not working in was pure scrolling
   *  (TODO 69). */
  _renderModeNav() {
    clear(this.modeNavEl);
    // One walk per render, not one per row (TODO 101). Reachability is a
    // property of the whole config, so it cannot differ between two rows of
    // one render - and `_renderModeNav` runs on every keystroke that changes
    // the model, which is where an O(n squared) answer would show up.
    this.reached = reachableModes(
      this.model.modes, this.model.actions || {}, this.model.reflexes || [],
    );
    // mode -> [entry, ...]. A list rather than one entry: nothing is listed
    // twice since TODO 101, but the live-dot ticker and the swatch repaint
    // walk whatever rows a mode has, and a Map of lists is the shape that
    // stays correct if a second listing is ever right again.
    this.navButtons = new Map();

    for (const group of MODE_GROUPS) {
      const members = this._membersOf(group);
      const total = members.length;
      // The one group that is absent rather than empty: every config has no
      // unrecognised modes, and a permanent "Unrecognised (0)" heading is
      // chrome that only ever says nothing.
      if (!total && group.key === 'unknown') continue;
      const foldKey = `nav-fold:${group.key}`;
      let folded = readFlag(foldKey, false);

      const body = el('div', { className: 'mode-nav-group-body' }, [
        el('p', { className: 'mode-nav-group-hint', 'data-help': true, textContent: group.blurb }),
      ]);
      if (!total) {
        body.append(el('p', { className: 'empty mode-nav-empty', textContent: group.emptyText }));
      } else if (group.key === 'apps') {
        this._appendApps(body, members);
      } else {
        for (const mode of members) body.append(this._navRow(mode, describeTemplate));
      }
      body.hidden = folded;

      const chevron = el('span', { className: 'mode-nav-group-chevron', textContent: folded ? '▸' : '▾' });
      const title = el('button', {
        type: 'button', className: 'mode-nav-group-title', 'aria-expanded': String(!folded),
        onclick: () => {
          folded = !folded;
          body.hidden = folded;
          chevron.textContent = folded ? '▸' : '▾';
          title.setAttribute('aria-expanded', String(!folded));
          writeFlag(foldKey, folded);
        },
      }, [chevron, `${group.title} (${total})`]);

      this.modeNavEl.append(el('div', { className: 'mode-nav-group' }, [title, body]));
    }
  }

  /** The Apps list, grouped by template.
   *
   * Several alarms are **one app with several alarms in it**, not several
   * apps, and a flat list said the opposite (TODO 48a). Grouping starts at
   * two: a header over a single child would double the list to say nothing,
   * and one stopwatch really is one stopwatch. Insertion order is kept, so
   * the list does not reshuffle itself as you add.
   *
   * The count is how many copies of the template exist, because that is what
   * the data holds. Nesting apps over items would make it an item count
   * instead - considered and parked (48b, parking lot): every runtime reader
   * of `modes` is flat, so the nesting would be undone at each of them. */
  _appendApps(groupEl, members) {
    const byTemplate = new Map();
    for (const mode of members) {
      const list = byTemplate.get(mode.template);
      if (list) list.push(mode);
      else byTemplate.set(mode.template, [mode]);
    }
    for (const [template, list] of byTemplate) {
      if (list.length < 2) {
        groupEl.append(this._navRow(list[0], describeTemplate));
        continue;
      }
      const label = TEMPLATE_BY_TYPE[template]?.label || template;
      groupEl.append(el('div', { className: 'mode-nav-app' }, [
        el('span', { className: 'mode-nav-app-name', textContent: label }),
        el('span', { className: 'mode-nav-app-count', textContent: String(list.length) }),
      ]));
      const nest = el('div', { className: 'mode-nav-nest' });
      for (const mode of list) nest.append(this._navRow(mode, describeTemplate));
      groupEl.append(nest);
    }
  }

  /** One row in the nav, registered so the live dot and the swatch can find
   *  every row a mode has. */
  _navRow(mode, summaryFor) {
    const dot = el('span', { className: 'mode-active-dot', hidden: true });
    // What sets this off, in one character (TODO 101). It sits with the name
    // rather than becoming a fifth column: a row already carries a live dot, a
    // look swatch, a name and a summary, and this is a sidebar.
    const starter = STARTER_BY_KEY[
      startedBy(mode, this.reached, this.model.actions || {}, this.model.reflexes || [])
    ];
    const glyph = el('span', {
      className: 'mode-nav-starter' + (starter?.key === 'none' ? ' unreachable' : ''),
      textContent: starter?.glyph || '',
      title: starter?.title || '',
    });
    const nameEl = el('span', { className: 'mode-nav-name', textContent: mode.name || '(unnamed)' });
    // Two halves, one line: what this item *is* (from the config, always
    // available) and what it has *done* (from the log, only once that has
    // answered). The config half is written first and alone, which is what a
    // shell with no service keeps.
    const summaryEl = el('span', { className: 'mode-nav-summary' });
    const writeSummary = () => {
      const stat = this._statLine(mode);
      summaryEl.textContent = summaryFor(mode) + (stat ? ` — ${stat}` : '');
    };
    writeSummary();
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
    const rows = this.navButtons.get(mode);
    // `writeSummary` rather than the raw `summaryFor`: the line has two
    // halves now and an editor rewriting only the config one would drop the
    // live numbers the moment you touched a field.
    const entry = { dot, nameEl, summaryEl, repaint, writeSummary };
    if (rows) rows.push(entry);
    else this.navButtons.set(mode, [entry]);
    return el('button', {
      type: 'button',
      className: 'mode-nav-item' + (mode === this.selectedMode ? ' selected' : ''),
      onclick: () => { this._renderModes(mode); this._showModesPanel(); },
    }, [dot, swatch, glyph, nameEl, summaryEl]);
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
    return modeLook(mode, this.model.looks || {}, this.model.led_palette || {});
  }

  /** Repaint every nav swatch. Called when a *pool* look changes, since that
   *  is an edit on another tab that several modes may be wearing. */
  _repaintNavSwatches() {
    for (const [, rows] of this.navButtons || []) for (const entry of rows) entry.repaint?.();
  }

  _renderModeDetail() {
    clear(this.modeDetailEl);
    this.detailEditor = null;
    const mode = this.selectedMode;
    if (!mode) {
      this.modeDetailEl.append(el('p', {
        className: 'mode-detail-empty',
        textContent: 'Pick a menu or an app from the list, or install one from Apps.',
      }));
      return;
    }
    this.detailEditor = new ModeEditor(mode, {
      onChange: () => {
        this._markDirty();
        // Every row this mode has. Nothing is listed twice since TODO 101,
        // but the loop is over whatever rows exist rather than over an
        // assumption about how many there are.
        for (const entry of this.navButtons?.get(mode) || []) {
          entry.nameEl.textContent = mode.name || '(unnamed)';
          entry.writeSummary();
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
      // Moving between the items of one app from inside it (TODO 51). The
      // editor asks rather than reaching for the modes list, exactly as it
      // does for every other list operation - this owns which one is selected.
      onSelect: (next) => this._renderModes(next),
      // "+ Add another" on an app's own page. Routed through the same two
      // helpers the App page's Install button uses, so an item added from
      // either place is named and seeded identically.
      onAddSibling: () => {
        const descriptor = TEMPLATE_BY_TYPE[mode.template];
        if (!descriptor) return;
        this._addMode(this._uniquelyNamed({
          name: descriptor.label,
          template: descriptor.type,
          activation: { type: (descriptor.allowedActivations || ['manual'])[0] },
          ...descriptor.defaults(),
        }));
      },
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
      getPalette: () => this.model.led_palette || {},
      getActions: () => this.model.actions || {},
      getFloor: () => this.model.min_flash_period_s,
      api: this.api,
      addLook: (name, effect) => this._addLook(name, effect),
      addAction: () => this._addAction(),
      onLooksChanged: () => {
        this._renderLooks();
        this._repaintNavSwatches();
        this._markDirty();
      },
    });
    this.modeDetailEl.append(this.detailEditor.el);
    this._markWarnings();
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

    for (const [mode, rows] of this.navButtons || []) {
      const gestures = gesturesFor(mode.name);
      for (const entry of rows) {
        entry.dot.hidden = !gestures.length;
        entry.dot.title = gestures.length
          ? `Right now, a ${gestures.join(' or a ')} would be handled by this mode.` : '';
      }
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

    this.systemStatesWrap = el('div', { className: 'palette-wrap' });
    this._renderSystemStates();

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
      this.systemStatesWrap,
      el('h3', { className: 'palette-group', textContent: 'Named looks' }),
      el('p', { className: 'menu-hint', 'data-help': true, textContent: 'A shared pool of appearances. Name one here and any mode - or any of the states above - can wear it, or make one straight from a mode. This is where they all end up either way.' }),
      this.looksWrap,
      add,
    ]);
  }

  /** The five system states as a list, one editor open at a time (TODO 54) -
   *  the pool's own pattern (`_renderLookEntry`), reused rather than
   *  reinvented. They used to render fully expanded, which was the exact
   *  "six editors, which one is Ember?" problem the pool's row was written
   *  to fix, still there in the one place a novice lands first. */
  _renderSystemStates() {
    clear(this.systemStatesWrap);
    for (const state of SYSTEM_LED_STATES) {
      if (!this.model.led_palette[state.key]) continue; // server decides the set
      this.systemStatesWrap.append(this._renderStateRow(state));
    }
  }

  /** One state: the line, plus its editor when it is the open one. Mirrors
   *  `_renderLookEntry` minus Duplicate/Delete - a system state is fixed,
   *  never added or removed. */
  _renderStateRow(state) {
    const effect = this.model.led_palette[state.key];
    const open = this._expandedState === state.key;

    const swatch = el('span', { className: 'palette-swatch' });
    applySwatch(swatch, effect);
    const summary = el('span', { className: 'palette-summary', textContent: describeEffect(effect) });

    const line = el('div', { className: 'look-line' }, [
      swatch,
      el('span', { className: 'palette-name', textContent: state.label }),
      el('span', { className: 'palette-meaning', textContent: state.meaning }),
      summary,
      el('button', {
        type: 'button', className: 'mini',
        textContent: open ? 'Done' : 'Edit',
        onclick: () => {
          this._expandedState = open ? null : state.key;
          this._renderSystemStates();
        },
      }),
    ]);

    if (!open) return el('div', { className: 'look-entry' }, [line]);

    const editor = this._renderEffectRow({
      get: () => this.model.led_palette[state.key],
      label: state.label,
      meaning: state.meaning,
      previewState: state.key,
      // What makes "a named look" an option in this row's Style dropdown
      // (TODO 36f). Handed in rather than reached for, so the engine never
      // learns where a state look is stored - the same seam the pool and
      // the mode editor already use.
      namedLook: this._stateLookHandle(state),
    });
    return el('div', { className: 'look-entry open' }, [line, editor]);
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
  /** A free-named pool entry (`{action: 'log', event: ''}`), added and
   *  rendered. Shared by the pool's own "+ Add" button and a gesture's empty
   *  named-action picker (TODO 61's "Make one") - one path to a new entry,
   *  not two. Returns the name actually used. */
  _addAction() {
    if (!this.model.actions) this.model.actions = {};
    let name = 'action';
    for (let n = 2; this.model.actions[name]; n += 1) name = `action ${n}`;
    this.model.actions[name] = { action: 'log', event: '' };
    this._renderActionPool();
    this._markDirty();
    return name;
  }

  // --- reflexes (TODO 71) ------------------------------------------------
  // A circumstance with an action attached, fired by something that is not a
  // finger. It sits on this tab rather than a tab of its own for the reason
  // the action pool does - concept count is the enemy - and above the pool
  // because a reflex is a thing you *want* and a named action is plumbing.
  //
  // Listed even when nothing has ever fired one: a reflex is invisible by
  // nature - there is no press to watch for - so the config is the only place
  // it can be seen at all, and each row carries the URL that fires it.

  /** A new reflex, named uniquely, with the likeliest action pre-chosen.
   *  `enter_mode` rather than the pool's `log`: what people ask reflexes for
   *  is "when X happens, start this". */
  _addReflex() {
    if (!Array.isArray(this.model.reflexes)) this.model.reflexes = [];
    const taken = new Set(this.model.reflexes.map((r) => r && r.name));
    let name = 'reaction';
    for (let n = 2; taken.has(name); n += 1) name = `reaction ${n}`;
    this.model.reflexes.push({ name, then: ACTION_BY_TYPE.enter_mode.defaults() });
    this._renderReflexes();
    this._markDirty();
    return name;
  }

  _renderReflexSection() {
    this.reflexWrap = el('div', { className: 'palette-wrap' });
    this._renderReflexes();
    const add = el('button', {
      type: 'button', textContent: '+ Add a reaction',
      onclick: () => this._addReflex(),
    });
    return el('div', { className: 'action-pool' }, [
      el('h3', { className: 'palette-group', textContent: 'Reactions' }),
      el('p', { className: 'menu-hint', 'data-help': true, textContent:
        'The button acting with nobody pressing it. Each one has a name and an '
        + 'action, and anything that can make an HTTP request fires it - a '
        + 'sensor, a script, a cron job, a phone shortcut - so a plant that has '
        + 'gone dry can ring an alarm. Nothing fires these on its own: the '
        + 'address under each one is the whole interface.' }),
      this.reflexWrap,
      el('div', { className: 'add-row' }, [add]),
    ]);
  }

  _renderReflexes() {
    clear(this.reflexWrap);
    // The nav no longer *lists* reactions (TODO 102), and still depends on
    // them: an app a reaction opens wears the reaction glyph (TODO 101), so
    // adding, deleting or repointing one changes what a row over in Apps says
    // about itself. Rebuilt from here rather than left to go stale.
    if (this.modeNavEl) this._renderModeNav();
    const list = this.model.reflexes || [];
    if (!list.length) {
      this.reflexWrap.append(el('p', { className: 'menu-hint', textContent: 'No reactions yet.' }));
      return;
    }
    list.forEach((reflex, index) => {
      this.reflexWrap.append(this._renderReflexRow(reflex, index));
    });
  }

  /** One reflex: its name, what it does, and what it can be limited to. */
  _renderReflexRow(reflex, index) {
    // A sentinel, not an action type - the same one the gesture sub-editor
    // uses, and for the same reason: naming a pooled action is a different way
    // of *holding* one, not a kind of one.
    const NAMED = '__named__';
    const offered = ACTIONS.filter((a) => REFLEX_ACTIONS.includes(a.type));

    // Built first so the handlers below can reach it: the name is what the nav
    // finds this row by, so it has to follow the input rather than the render.
    const row = el('div', { className: 'gesture-row', 'data-reflex': reflex.name || '' });

    // Renaming rewrites nothing, and that is not an oversight: what points at
    // a reflex is a URL in something outside this config, which the editor
    // cannot reach. So the address is shown instead, and follows the name.
    const url = el('code', { className: 'menu-hint' });
    const nameInput = el('input', {
      type: 'text', className: 'inp', value: reflex.name || '',
      oninput: () => {
        reflex.name = nameInput.value.trim();
        url.textContent = this._reflexUrl(reflex);
        row.setAttribute('data-reflex', reflex.name);
        restate();
        this._markDirty();
      },
    });
    url.textContent = this._reflexUrl(reflex);

    const summary = el('span', { className: 'menu-hint', textContent: describeReflex(reflex) });
    // One sentence for the whole reflex, restated by every control on the row
    // - the test, the action and the scope all change what it says. The nav
    // lists the same sentence (TODO 75), so it is rebuilt here rather than
    // left to go stale: two descriptions of one object is how a page lies.
    const restate = () => {
      summary.textContent = describeReflex(reflex);
      if (this.modeNavEl) this._renderModeNav();
    };
    const fields = el('div', { className: 'gesture-fields' });

    const buildFields = () => {
      clear(fields);
      const named = typeof reflex.then === 'string';
      if (named) {
        fields.append(this._reflexNamedField(reflex, restate));
        return;
      }
      const descriptor = reflex.then && ACTION_BY_TYPE[reflex.then.action];
      if (!descriptor) return;
      for (const spec of descriptor.fields) {
        const ctx = {
          getModes: () => this.model.modes, api: this.api, rebuild: buildFields,
          // A sequence step may name a pooled action, so the pool travels
          // with every context that can build one.
          getActions: () => this.model.actions || {},
        };
        const field = createField(spec, reflex.then, () => {
          restate();
          this._markDirty();
        }, ctx);
        fields.append(field.el);
      }
    };

    const kind = el('select', {
      className: 'inp',
      onchange: () => {
        // An empty name rather than a guessed one, exactly as a gesture does:
        // picking the pool's first entry would point this at something nobody
        // chose.
        reflex.then = kind.value === NAMED ? '' : ACTION_BY_TYPE[kind.value].defaults();
        buildFields();
        restate();
        this._markDirty();
      },
    }, [
      ...offered.map((a) => el('option', { value: a.type, textContent: a.label })),
      el('option', { value: NAMED, textContent: 'Use a named action' }),
    ]);
    kind.value = typeof reflex.then === 'string'
      ? NAMED : (reflex.then?.action || 'enter_mode');

    const remove = el('button', {
      type: 'button', textContent: 'Delete',
      onclick: () => {
        this.model.reflexes.splice(index, 1);
        this._renderReflexes();
        this._refreshApps();
        this._markDirty();
      },
    });

    buildFields();
    row.append(
      el('div', { className: 'gesture-head' }, [nameInput, kind, remove]),
      summary,
      url,
      fields,
      this._reflexFrom(reflex, restate),
      this._reflexWhen(reflex, restate),
      this._reflexScope(reflex, restate),
    );
    return row;
  }

  /** The address that fires it. Shown rather than explained: the only thing
   *  between a reaction and the script that fires it is knowing where to post,
   *  and this page is served by the host that answers.
   *
   *  `/api/reaction/` since TODO 103, and `/api/reflex/` still answers - see
   *  webui.py. Only one can be shown, and it has to be the new one, or the
   *  page teaches a spelling the docs no longer use. */
  _reflexUrl(reflex) {
    const name = reflex.name || '…';
    const origin = typeof location !== 'undefined' && location.origin && location.origin !== 'null'
      ? location.origin : '';
    return `POST ${origin}/api/reaction/${encodeURIComponent(name)}`;
  }

  /** A picker over the named-action pool - the reflex half of the gesture
   *  editor's `_namedActionField`, same dangling rules, same "Make one". */
  _reflexNamedField(reflex, onChanged) {
    const names = Object.keys(this.model.actions || {}).sort();
    const options = [el('option', { value: '', textContent: '- pick one -' })];
    // A deleted pool entry stays listed and stays selected, marked: silently
    // repointing this is exactly what a dangling name exists to prevent.
    if (reflex.then && !names.includes(reflex.then)) {
      options.push(el('option', { value: reflex.then, textContent: `${reflex.then} (missing)` }));
    }
    options.push(...names.map((n) => el('option', { value: n, textContent: n })));
    const pick = el('select', {
      className: 'inp',
      onchange: () => { reflex.then = pick.value; onChanged(); this._markDirty(); },
    }, options);
    pick.value = reflex.then || '';
    const make = el('button', {
      type: 'button', className: 'mini', textContent: 'Make one',
      onclick: () => {
        const name = this._addAction();
        pick.append(el('option', { value: name, textContent: name }));
        pick.value = name;
        reflex.then = name;
        onChanged();
      },
    });
    return el('label', { className: 'fld' }, [
      el('span', { className: 'fld-label', textContent: 'Named action' }),
      pick, make,
    ]);
  }

  /** `from`: what fires this besides its own URL (TODO 73).
   *
   *  A **source**, not a test - it says which messages reach the reflex, and
   *  `Only when` above decides whether they fire it. That is the whole reason
   *  MIDI needed no comparison language of its own: *note 95 velocity 127* is
   *  this control plus `velocity == 127`, and the dark half of the same lamp
   *  is the same source with the opposite test.
   *
   *  The URL never goes away - a source *adds* a way in - so a MIDI reflex is
   *  still testable with `curl` while the DAW is closed. */
  _reflexFrom(reflex, onChanged) {
    const fields = el('div', { className: 'gesture-fields' });

    const spec = () => (reflex.from && reflex.from.midi) || null;
    const build = () => {
      clear(fields);
      const midi = spec();
      if (!midi) return;
      const numberKey = 'cc' in midi ? 'cc' : 'note';

      // The port goes through the schema widget so it gets the service's own
      // list of inputs as suggestions - and stays a free-text field where
      // there is no service to ask (the offline editor).
      const port = createField(
        { key: 'port', label: 'MIDI port', kind: 'text', suggest: 'midi_in',
          hint: 'Any part of the port name. Blank takes the first input.' },
        midi, () => { onChanged(); this._markDirty(); }, { api: this.api },
      );
      const number = el('input', {
        type: 'number', className: 'inp', min: 0, max: 127, step: 1,
        value: midi[numberKey] ?? 0,
        oninput: () => {
          midi[numberKey] = Number(number.value);
          onChanged();
          this._markDirty();
        },
      });
      // Blank means any channel, which is the useful default: a control
      // surface protocol pins the note number and leaves the channel to
      // whatever the DAW was set up with.
      const channel = el('input', {
        type: 'number', className: 'inp', min: 1, max: 16, step: 1,
        value: midi.channel ?? '', placeholder: 'any',
        oninput: () => {
          if (channel.value === '') delete midi.channel;
          else midi.channel = Number(channel.value);
          onChanged();
          this._markDirty();
        },
      });
      fields.append(
        port.el,
        el('label', { className: 'fld' }, [
          el('span', { className: 'fld-label',
            textContent: numberKey === 'cc' ? 'Controller number' : 'Note number' }),
          number,
        ]),
        el('label', { className: 'fld' }, [
          el('span', { className: 'fld-label', textContent: 'Channel' }),
          channel,
          el('span', { className: 'fld-hint', 'data-help': true,
            textContent: 'Leave blank for any channel.' }),
        ]),
      );
    };

    const pick = el('select', {
      className: 'inp',
      onchange: () => {
        const midi = spec() || {};
        if (!pick.value) {
          delete reflex.from;
        } else {
          const number = midi.note ?? midi.cc ?? 0;
          const next = { port: midi.port || '' };
          next[pick.value] = number;
          if (midi.channel != null) next.channel = midi.channel;
          reflex.from = { midi: next };
        }
        build();
        onChanged();
        this._markDirty();
      },
    }, [
      el('option', { value: '', textContent: 'its address only' }),
      el('option', { value: 'note', textContent: 'a MIDI note' }),
      el('option', { value: 'cc', textContent: 'a MIDI control change' }),
    ]);
    pick.value = spec() ? ('cc' in spec() ? 'cc' : 'note') : '';

    build();
    return el('div', { className: 'fld' }, [
      el('span', { className: 'fld-label', textContent: 'Fired by' }),
      pick,
      el('span', { className: 'fld-hint', 'data-help': true, textContent:
        'A DAW that lights up a control surface is telling you what it is '
        + 'doing - point its feedback at a port the button listens on and a '
        + 'note becomes a reaction. The value rides along as “velocity” (a '
        + 'note) or “value” (a control change), for Only when to test.' }),
      fields,
    ]);
  }

  /** `when`: one field of the posted body, one operator, one number (TODO
   *  72). Three controls on one line, because that is exactly what the test
   *  is - and there is deliberately no "add another condition": two of these
   *  would be an expression language, and an expression language cannot move
   *  onto the button.
   *
   *  An empty field name means no test, the same "unset is absent" idiom the
   *  scope row uses. */
  _reflexWhen(reflex, onChanged) {
    const test = reflex.when || {};
    const write = () => {
      const name = field.value.trim();
      if (!name) {
        delete reflex.when;
      } else {
        reflex.when = {
          field: name,
          op: op.value,
          value: Number(value.value) || 0,
        };
      }
      onChanged();
      this._markDirty();
    };
    const field = el('input', {
      type: 'text', className: 'inp', value: test.field || '',
      placeholder: 'moisture', oninput: write,
    });
    const op = el('select', { className: 'inp', onchange: write },
      REFLEX_OPS.map((o) => el('option', { value: o, textContent: o })));
    op.value = test.op || '<';
    const value = el('input', {
      type: 'number', className: 'inp', step: 'any',
      value: test.value ?? 0, oninput: write,
    });
    return el('label', { className: 'fld' }, [
      el('span', { className: 'fld-label', textContent: 'Only when' }),
      el('div', { className: 'scope-row' }, [field, op, value]),
      el('span', { className: 'fld-hint', 'data-help': true, textContent:
        'Left blank it fires on every arrival. Filled in, it reads one field '
        + 'of the JSON you post - {"moisture": 12} - and fires only if the '
        + 'comparison holds. The number is logged either way, so the Events '
        + 'page charts it whether or not it crossed the line; a field that is '
        + 'missing never fires.' }),
    ]);
  }

  /** `while`: limit this reflex to one running app. Rare by design - a reflex
   *  is about the button and the world, not about one app - so it is one
   *  select that defaults to "any time". */
  _reflexScope(reflex, onChanged) {
    const apps = (this.model.modes || []).filter(
      (m) => TEMPLATE_BY_TYPE[m?.template]?.nature === 'takeover',
    );
    const options = [el('option', { value: '', textContent: 'any time' })];
    if (reflex.while && !apps.some((m) => m.name === reflex.while)) {
      options.push(el('option', { value: reflex.while, textContent: `${reflex.while} (missing)` }));
    }
    options.push(...apps.map((m) => el('option', { value: m.name, textContent: m.name })));
    const pick = el('select', {
      className: 'inp',
      onchange: () => {
        if (pick.value) reflex.while = pick.value; else delete reflex.while;
        onChanged();
        this._markDirty();
      },
    }, options);
    pick.value = reflex.while || '';
    return el('label', { className: 'fld' }, [
      el('span', { className: 'fld-label', textContent: 'Only while' }),
      pick,
      el('span', { className: 'fld-hint', 'data-help': true, textContent:
        'Left at "any time" it fires whenever it arrives, and waits if an app '
        + 'is running. Naming an app is how a reaction reaches *into* one while '
        + 'it runs - "Put an app on a position" needs this, and so does '
        + 'anything meant for that app and nothing else.' }),
    ]);
  }

  _renderActionPoolSection() {
    this.actionsWrap = el('div', { className: 'palette-wrap' });
    this._renderActionPool();

    const add = el('button', {
      type: 'button', textContent: '+ Add a named action',
      onclick: () => this._addAction(),
    });

    return el('div', { className: 'action-pool' }, [
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
        // Every slot in one walk (TODO 102). This was a hand-written list -
        // gestures and a signal light's positions - and it quietly missed
        // hooks, a Notice's outcomes, a reaction's `then` and a sequence's
        // steps, so renaming from the editor could dangle exactly the
        // references the parser then warned about. The list of usages and the
        // list of things to rewrite are the same list.
        for (const ref of actionRefs(this.model.modes, this.model.reflexes, this.model.actions)) {
          if (ref.owner[ref.key] === name) ref.owner[ref.key] = next;
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

    // The same thing the look pool's row says, asked of the second pool
    // (TODO 102): editing a shared action changes it everywhere, and that has
    // to be visible before the edit. An entry nothing points at is worth
    // saying too - it is either about to be used or forgotten.
    const usedBy = actionUsedBy(name, this.model.modes, this.model.reflexes, this.model.actions);
    const used = el('span', {
      className: usedBy.length ? 'menu-hint' : 'menu-hint empty',
      textContent: usedBy.length ? `used by ${usedBy.join(', ')}` : 'not used anywhere yet',
      title: usedBy.length ? 'Editing this action changes it everywhere it is used.' : '',
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
          getActions: () => this.model.actions || {},
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
      used,
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

  /** A read-only view of the working config, plus a copy button (TODO 59).
   *  The tinkerer persona is defined by wanting to see the document; Export
   *  downloads a scene and Import replaces one, neither of which answers
   *  "what does this control actually write" without leaving the page. */
  _renderRawJson() {
    const pre = el('pre', { className: 'menu-result', hidden: true });
    const copyBtn = el('button', {
      type: 'button', className: 'mini', textContent: 'Copy', hidden: true,
      onclick: async () => {
        try {
          await navigator.clipboard.writeText(pre.textContent);
          copyBtn.textContent = 'Copied!';
        } catch {
          copyBtn.textContent = 'Copy failed';
        }
        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
      },
    });
    const toggle = el('button', {
      type: 'button', className: 'mini',
      textContent: 'View raw JSON',
      onclick: () => {
        const show = pre.hidden;
        if (show) pre.textContent = JSON.stringify(this.model, null, 2);
        pre.hidden = !show;
        copyBtn.hidden = !show;
        toggle.textContent = show ? 'Hide raw JSON' : 'View raw JSON';
      },
    });
    return el('div', { className: 'settings-group' }, [
      el('h4', { className: 'settings-title', textContent: 'Raw config' }),
      el('p', { className: 'menu-hint', textContent:
        'Read-only, and always the working copy - editing here does nothing. '
        + 'The fastest way to learn what any control above actually writes.' }),
      el('div', { className: 'add-row' }, [toggle, copyBtn]),
      pre,
    ]);
  }

  _renderSettingsSection() {
    const wrap = el('div', { className: 'settings-wrap' });
    this.settingValidators = [];
    wrap.append(this._renderRawJson());
    for (const group of SETTINGS_GROUPS) {
      const grid = el('div', { className: 'settings-grid' });
      for (const spec of group.fields) {
        const field = createField(spec, this.model, () => this._markDirty());
        this.settingValidators.push(field.validate);
        grid.append(field.el);
      }
      // A group whose every field is Tinker-tier is itself Tinker-tier, or a
      // basic user gets a heading with nothing under it - which is what the
      // Device page did: "WEB SERVER" followed by empty space, because all
      // three of its fields are hidden (TODO 47's fix pass). Derived from the
      // specs rather than declared on the group, so a group that gains one
      // basic field starts showing again on its own.
      const allTinker = group.fields.every((spec) => spec.tier === 'tinker');
      wrap.append(el('div', {
        className: 'settings-group',
        ...(allTinker ? { 'data-tier': 'tinker' } : {}),
      }, [
        el('h4', { className: 'settings-title', textContent: group.title }),
        group.note ? el('p', { className: 'menu-hint', textContent: group.note }) : null,
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
  // Each error carries where to find it (TODO 60) - which panel, and which
  // mode if it's a mode's - so a failed Check/Save can take you there instead
  // of leaving you to guess among eleven. `.text` is still the flat string
  // the Save bar has always shown; callers that only want that map over it.
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
      for (const err of editor.validate()) errors.push({ text: `${label}: ${err}`, panel: 'modes', mode });
    }
    for (const validate of this.settingValidators) {
      const error = validate();
      if (error) errors.push({ text: error, panel: 'device', mode: null });
    }
    for (const validate of (this.paletteValidators || [])) {
      const error = validate();
      if (error) errors.push({ text: error, panel: 'lights', mode: null });
    }
    return errors;
  }

  // Switches to wherever the first error lives and scrolls its field into
  // view, re-validating a mode we just switched to so its inline .fld-err
  // spans - only ever populated live for the mode on screen - actually show
  // something. Settings and palette validators already ran against their
  // live fields in _collectErrors, so no re-run is needed for those panels.
  _jumpToError(errors) {
    if (!errors.length) return;
    const first = errors[0];
    document.dispatchEvent(new CustomEvent('button:show-panel', { detail: first.panel }));
    if (first.panel === 'modes' && first.mode !== this.selectedMode) this._renderModes(first.mode);
    if (first.panel === 'modes') this.detailEditor?.validate();
    requestAnimationFrame(() => {
      const container = first.panel === 'modes' ? this.modeDetailEl : this.mounts[first.panel];
      const bad = container?.querySelector('.fld-err:not(:empty)');
      const field = bad?.closest('.fld, .gesture-row');
      if (!field) return;
      field.scrollIntoView({ block: 'center', behavior: 'smooth' });
      field.classList.add('fld-jump');
      setTimeout(() => field.classList.remove('fld-jump'), 1600);
    });
  }

  async check() {
    const errors = this._collectErrors();
    if (errors.length) {
      this._jumpToError(errors);
      return this._showResult('err', `Fix these first:\n• ${errors.map((e) => e.text).join('\n• ')}`);
    }
    try {
      const res = await this.api.validate(this.model);
      this.warningDetails = res.warning_details || [];
      this._markWarnings();
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
    if (errors.length) {
      this._jumpToError(errors);
      return this._showResult('err', `Fix these first:\n• ${errors.map((e) => e.text).join('\n• ')}`);
    }
    try {
      const res = await this.api.put(this.model);
      this.warningDetails = res.warning_details || [];
      // Re-seed from the normalized server result so the form shows exactly
      // what was stored (per-key fallbacks included).
      this.model = structuredClone(res.effective);
      if (!Array.isArray(this.model.modes)) this.model.modes = [];
      if (!Array.isArray(this.model.reflexes)) this.model.reflexes = [];
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

  /**
   * Put the parser's complaints on the fields they are about (TODO 62).
   *
   * The index is the join: a warning carries `modes[3]`, and the editor on
   * screen renders `this.selectedMode`, so this is the only place that can
   * pair them - the editor knows nothing about the config it sits in, and the
   * warning knows nothing about which mode is open.
   */
  _markWarnings() {
    if (!this.detailEditor || !this.selectedMode) return;
    const index = this.model.modes.indexOf(this.selectedMode);
    this.detailEditor.showWarnings(
      (this.warningDetails || []).filter((w) => w && w.mode === index),
    );
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
  // The shell's side panel, where the mode list lives on the served page.
  // Absent in the offline editor, which keeps the nav inside the panel.
  nav: document.getElementById('mode-nav-mount'),
  // Optional for the same reason: the offline editor has no App page, and a
  // missing mount means one section fewer, not a broken menu.
  apps: document.getElementById('panel-apps'),
  // The pool page (TODO 102). Optional for the same reason `apps` is.
  actions: document.getElementById('panel-actions'),
  lights: document.getElementById('panel-lights'),
  device: document.getElementById('panel-device'),
  bar: document.getElementById('menu-bar'),
  // Optional: no scene bar in the page (the standalone editor) simply means
  // no scene switching, not a broken menu.
  scenes: document.getElementById('scene-bar'),
};
if (mounts.modes) new ConfigMenu(mounts).load();
