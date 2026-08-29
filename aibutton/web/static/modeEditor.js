// Renders and edits a single mode, always fully open: name → template
// <select> (swaps the template body) → activation <select> (swaps the
// activation body). Only ever one is on screen (menu.js's detail pane), so
// this has no collapse state of its own; a second, never-attached instance
// exists only to run validate() over a mode that is not selected.
//
// Fields come from the widget factory and the template/activation choices
// from the schema registries, so it knows nothing about specific template,
// activation, action or field kinds (Dependency Inversion). It mutates the
// mode object in place and reports edits, moves and removal through injected
// handlers - it does not own the modes list.

import { el, clear } from './dom.js';
import {
  GESTURES, MODE_HOOKS, DAYS, ACTIONS, ACTION_BY_TYPE,
  TEMPLATES, TEMPLATE_BY_TYPE,
  ACTIVATIONS, ACTIVATION_BY_TYPE, describeActivation,
  describeExit, findEntryPoints, modeLook,
  LED_STATE_BY_KEY, describeEffect, LOOK_PRESETS, LOOK_PRESET_GROUPS, presetLook,
} from './schema.js';
import { paint as applySwatch, unpaint } from './ledPreview.js';
import { createField } from './widgets.js';
import { createLookEditor } from './colorEngine.js';
import { createReadout } from './appReadout.js';

export class ModeEditor {
  /**
   * @param {object} mode - the mode object (mutated in place)
   * @param {{onChange?: Function, onRemove?: Function,
   *          onMoveUp?: Function, onMoveDown?: Function, canReorder?: boolean,
   *          getModes?: Function}} handlers
   */
  constructor(mode, handlers = {}) {
    this.mode = mode;
    this.handlers = handlers;
    this._validators = []; // each returns an error string or null
    // config key -> the element rendering it, so a parser warning can mark
    // its own field (TODO 62). Rebuilt with the body; `_warnings` is kept so
    // marks survive a template swap or a redraw, which is exactly when a
    // warning is still true and would otherwise vanish.
    this._byKey = new Map();
    this._warnings = [];
    // Which state's look is expanded, one at a time - the Lights tab's own
    // `_expandedState` pattern (menu.js), so an app with several owned states
    // reads as a short list rather than several editors stacked open.
    this._expandedLookState = null;
    this.el = el('div', { className: 'mode-card' });
    this._build();
  }

  _changed() {
    this.refreshExplainers();
    this.handlers.onChange?.();
  }

  // Context handed to dynamic widgets (e.g. the enter_mode target select).
  // `api` rides along for widgets whose suggestions come from the service
  // (the MIDI port datalist) - optional by construction, absent offline.
  _fieldCtx() {
    return {
      getModes: this.handlers.getModes || (() => []),
      // The picker that chooses a mode shows the light it runs in, which needs
      // both halves of the resolution the nav does - the named-look pool and
      // the palette underneath it (TODO 50).
      getLooks: this.handlers.getLooks || (() => ({})),
      getPalette: this.handlers.getPalette || (() => ({})),
      api: this.handlers.api,
      // What this app reports when it finishes, so a webhook bound to its
      // `on_exit` can show the keys that will actually arrive (TODO 65/66).
      // Read through a function rather than captured, because the template
      // can be swapped while the editor is open. Absent elsewhere - a
      // reflex's webhook has no app, and saying so beats inventing one.
      summaryKeys: () => (TEMPLATE_BY_TYPE[this.mode.template] || {}).summaryKeys || [],
      modeName: () => this.mode.name || null,
    };
  }

  /** The named-action pool, as `{name: action}`. Read through the handler for
   *  the same reason `getModes` is - and an editor built off-screen purely to
   *  run validators may be handed none at all. */
  _actionPool() {
    return (this.handlers.getActions ? this.handlers.getActions() : null) || {};
  }

  _build() {
    clear(this.el);
    this._validators = [];
    this._byKey = new Map();
    // Every `<details>` `_section()` wrapped this build (TODO 85), so a
    // warning or error painted afterward knows which ones to force open.
    this._sectionEls = [];
    this.el.append(this._body());
    this._paintWarnings();
  }

  /**
   * Show the parser's complaints about *this* mode on the fields they are
   * about (TODO 62).
   *
   * @param {{message: string, key: ?string}[]} warnings - already filtered to
   *   this mode by the caller, which is the only thing that knows this mode's
   *   index in the config it came from.
   *
   * **A warning with no key still counts.** It cannot be placed on a field,
   * and the Save bar goes on printing every one of them regardless - this
   * marks what it can and silently leaves the rest to the bar, because a
   * complaint that appeared in neither place would be a warning nobody acts
   * on. That is also why the bar was not replaced.
   */
  showWarnings(warnings = []) {
    this._warnings = warnings;
    this._paintWarnings();
  }

  _paintWarnings() {
    for (const element of this._byKey.values()) {
      element.classList.remove('fld-warn');
      element.querySelector('.fld-warned')?.remove();
    }
    for (const warning of this._warnings) {
      const element = warning.key && this._byKey.get(warning.key);
      if (!element || element.querySelector('.fld-warned')) continue;
      element.classList.add('fld-warn');
      element.append(el('span', {
        className: 'fld-warned',
        // The parser's own sentence, minus the "config: " and the location it
        // already put you next to - the rest of it is the part that says what
        // to do, and re-reading `modes[3].ladder` beside the ladder is noise.
        textContent: warning.message
          .replace(/^config: /, '')
          .replace(/^modes\[\d+\](\.[\w.[\]']*)? ?/, ''),
      }));
    }
    this._openSectionsWithProblems();
  }

  /**
   * A collapsed section stays collapsed only while nothing inside it needs
   * looking at (TODO 85). Called after every warning paint and every
   * client-side validate() - both leave their marks as DOM state (`.fld-warn`
   * for a parser warning, a non-empty `.fld-err` for a widget's own check),
   * so this is a plain sweep rather than a second bookkeeping structure that
   * could drift from what is actually on screen.
   */
  _openSectionsWithProblems() {
    for (const details of this._sectionEls || []) {
      const warned = details.querySelector('.fld-warn');
      const errored = Array.from(details.querySelectorAll('.fld-err'))
        .some((e) => e.textContent.trim());
      if (warned || errored) details.open = true;
    }
  }

  /**
   * Mark this card as the one answering `gestures` right now.
   * @param {string[]} gestures - gesture labels, empty for "not in charge".
   */
  setActive(gestures) {
    if (!this.activeEl) return;
    this.activeEl.hidden = !gestures.length;
    if (!gestures.length) return;
    this.activeEl.textContent = '● Active now';
    this.activeEl.title = `Right now, a ${gestures.join(' or a ')} would be handled by this mode.`;
  }

  // --- body -----------------------------------------------------------

  _body() {
    this.bodyEl = el('div', { className: 'mode-body' });
    // A stable container so refreshExplainers() can rewrite the how-to-get-in
    // / how-to-get-out lines without rebuilding the fields you are editing.
    this.howtoEl = el('div', { className: 'howto' });
    // Colour above the mechanics, deliberately: what a mode looks like is how
    // you recognise it going off from across the room, not an afterthought
    // setting. Only takeover modes have one - an everyday mode never owns the
    // light long enough to have an appearance of its own.
    // Above the settings, deliberately (TODO 51): if a stopwatch is an app,
    // its page should *be* the stopwatch, and what it has done is the thing
    // you came to look at. The knobs are what you came to change, which is a
    // rarer visit.
    this.bodyEl.append(
      this._header(), this._siblings(), this.howtoEl, this._readoutSection(),
      this._section('How it looks', this._looksPicker(), this._looksDefaultOpen()),
      // Always open: you reached this page by opening this app, and hiding
      // the one section that holds its settings would be the wrong kind of
      // quiet. The heading names the app rather than asking what it is
      // (TODO 87) - see `_templateHeading`.
      this._section(this._templateHeading(), this._templatePicker(), true),
      this._section("When it's on", this._activationPicker(), this._activationDefaultOpen()),
      this._section('Around the session', this._hooks(), this._hooksDefaultOpen(), { tinker: true }),
    );
    this.refreshExplainers();
    return this.bodyEl;
  }

  /**
   * Wrap `contentEl` in a collapsible `<details>` named by `label` (TODO 85) -
   * closed when `defaultOpen` is false, so a simple mode's card is mostly
   * headings rather than four always-open blocks. `_openSectionsWithProblems`
   * can still force one open later regardless of this initial state.
   *
   * Content with nothing to show at all (an ambient mode's "How it looks", an
   * everyday mode's hooks) arrives already `.hidden` from its own builder and
   * is returned as-is - a `<details>` around nothing is still a control that
   * does nothing. `tinker: true` moves the whole section behind the Tinker
   * toggle as one unit (help.js's `[data-tier="tinker"]`), which is what
   * "Around the session" already did before it had a summary to carry that
   * attribute instead.
   */
  _section(label, contentEl, defaultOpen, { tinker = false } = {}) {
    if (contentEl.hidden) return contentEl;
    const details = el('details', {
      className: 'mode-section', open: defaultOpen,
      ...(tinker ? { 'data-tier': 'tinker' } : {}),
    }, [
      el('summary', { className: 'fld-label', textContent: label }),
      contentEl,
    ]);
    this._sectionEls.push(details);
    return details;
  }

  /** "How it looks" opens when some owned state already names a look. TODO
   *  86 made each row collapse on its own; this decides whether the section
   *  heading around that short list is worth opening to begin with. */
  _looksDefaultOpen() {
    return Boolean(this.mode.looks && Object.values(this.mode.looks).some(Boolean));
  }

  /** "When it's on" opens when the activation differs from that type's own
   *  bare `defaults()` - the same object a type switch seeds it with, so this
   *  is a diff against the seed rather than a second declaration of what
   *  "untouched" means. */
  _activationDefaultOpen() {
    const activation = this.mode.activation || {};
    const bare = ACTIVATION_BY_TYPE[activation.type]?.defaults();
    if (!bare) return true; // an unrecognised activation type is not "nothing to see"
    return JSON.stringify(activation) !== JSON.stringify(bare);
  }

  /** "Around the session" opens when a hook is actually bound. */
  _hooksDefaultOpen() {
    return MODE_HOOKS.some((hook) => Boolean(this.mode[hook.key]));
  }

  /**
   * The other items of this app, so you can move between them from inside it
   * (TODO 51) - 48's item list wearing the app's own interface.
   *
   * **Two or more, like the nav's grouping (48a).** A row of chips holding
   * only the item you are already looking at doubles the page to say nothing,
   * and one stopwatch really is one stopwatch.
   *
   * Switching is just a re-selection, so unsaved edits survive it: menu.js
   * holds one working copy of the whole config and every item on this page is
   * a live object inside it. Same as clicking a name in the nav, which is what
   * this is a shortcut for.
   */
  _siblings() {
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    const wrap = el('div', { className: 'siblings' });
    if (!descriptor || descriptor.nature !== 'takeover' || !this.handlers.onSelect) {
      wrap.hidden = true;
      return wrap;
    }
    const copies = (this.handlers.getModes?.() || []).filter(
      (m) => m && m.template === this.mode.template,
    );
    if (copies.length < 2) {
      wrap.hidden = true;
      return wrap;
    }

    // No plural of the app's label anywhere here: "Intervals" and "Hot / Cold"
    // do not take an -s, and a label built by adding one breaks on a template
    // nobody thought about. The chips say what they are.
    wrap.append(el('span', { className: 'fld-label', textContent: 'In this app' }));
    const row = el('div', { className: 'sibling-row' });
    for (const item of copies) {
      const swatch = el('span', { className: 'pick-swatch' });
      const look = modeLook(
        item, this.handlers.getLooks?.() || {}, this.handlers.getPalette?.() || {},
      );
      swatch.classList.toggle('empty', !look);
      if (look) applySwatch(swatch, look); else unpaint(swatch);
      row.append(el('button', {
        type: 'button',
        className: `sibling${item === this.mode ? ' current' : ''}`,
        // The one you are on is a label, not a link: clicking it would rebuild
        // the page you are already looking at and lose your cursor.
        disabled: item === this.mode,
        onclick: () => this.handlers.onSelect(item),
      }, [swatch, el('span', { textContent: item.name || '(unnamed)' })]));
    }
    if (this.handlers.onAddSibling) {
      row.append(el('button', {
        type: 'button', className: 'mini sibling-add', textContent: '+ Add another',
        onclick: () => this.handlers.onAddSibling(),
      }));
    }
    wrap.append(row);
    return wrap;
  }

  /** What this app has actually done, read out of the event log. Null for a
   *  template that logs nothing and wherever there is no service to ask (the
   *  offline editor) - see appReadout.js. */
  _readoutSection() {
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    const readout = createReadout(this.mode, descriptor, this.handlers.api);
    return readout ? readout.el : el('div', { hidden: true });
  }

  /**
   * One row per LED state this template owns, naming a look from the pool
   * (or the standard colour) - a *reference*, not an inline effect, which is
   * what lets two Pomodoros differ while `WORKING` stays one shared state
   * (ROADMAP D4). Mirrors the Lights tab's own state rows (menu.js's
   * `_renderStateRow`/`_renderLookEntry`): collapsed to a swatch and a
   * summary until "Edit" is clicked, one open at a time, so an app with
   * several owned states reads as a short list rather than several always-
   * open pickers (TODO 86).
   */
  _looksPicker() {
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    const states = descriptor?.ledStates || [];
    const wrap = el('div', { className: 'looks-row' });
    if (!states.length) {
      wrap.hidden = true;
      return wrap;
    }
    this._looksStates = states;
    this.looksWrapEl = wrap;
    this.looksListEl = el('div', {});
    wrap.append(this.looksListEl);
    this._renderLooksPicker();
    return wrap;
  }

  /** Rebuild the state-row list in place - cheap, and it is never more than a
   *  handful of rows. Called on every Edit/Done click rather than the whole
   *  mode card, so an open editor elsewhere on the card survives it. */
  _renderLooksPicker() {
    if (!this.looksListEl) return;
    clear(this.looksListEl);
    for (const key of this._looksStates || []) {
      this.looksListEl.append(this._renderLookStateRow(key));
    }
  }

  /** What state `key` currently shows: the named look if one is set and
   *  still in the pool, missing if it was deleted out from under it, or
   *  nothing (the palette fallback) - the same three answers `paint()`
   *  below computes for the picker itself, read once for the collapsed
   *  line's snapshot. */
  _resolvedLook(key) {
    const name = this.mode.looks?.[key] || '';
    if (!name) return { name: '', effect: null, missing: false };
    const effect = (this.handlers.getLooks?.() || {})[name];
    return { name, effect: effect || null, missing: !effect };
  }

  _renderLookStateRow(key) {
    const state = LED_STATE_BY_KEY[key] || { key, label: key, meaning: '' };
    const open = this._expandedLookState === key;

    const { name, effect, missing } = this._resolvedLook(key);
    const swatch = el('span', { className: 'palette-swatch' });
    if (effect) applySwatch(swatch, effect);
    const summary = el('span', {
      className: 'palette-summary',
      textContent: missing
        ? `${name} (missing)`
        : (effect ? describeEffect(effect) : 'the standard colour for this state'),
    });

    const line = el('div', { className: 'look-line' }, [
      swatch,
      el('span', { className: 'palette-name', textContent: state.label }),
      state.meaning ? el('span', { className: 'palette-meaning', textContent: state.meaning }) : null,
      summary,
      el('button', {
        type: 'button', className: 'mini', textContent: open ? 'Done' : 'Edit',
        onclick: () => {
          this._expandedLookState = open ? null : key;
          this._renderLooksPicker();
        },
      }),
    ].filter(Boolean));

    if (!open) return el('div', { className: 'look-entry' }, [line]);
    return el('div', { className: 'look-entry open' }, [line, this._renderLookStateBody(key)]);
  }

  /** The open row's body: which look this state names, a way to start a new
   *  one from a preset, and - once a look is chosen - that pool look's own
   *  editor, in place. Unchanged from before TODO 86 except for where it
   *  lives: this is what makes "Edit" open straight into the colour
   *  sequencer rather than sending you elsewhere. */
  _renderLookStateBody(key) {
    const select = el('select', {
      className: 'inp',
      onchange: () => { setLook(select.value); paint(); this._changed(); },
    });

    const swatch = el('span', { className: 'palette-swatch' });
    const summary = el('span', { className: 'palette-summary' });
    const editorSlot = el('div', { className: 'looks-editor' });

    const setLook = (name) => {
      if (!this.mode.looks) this.mode.looks = {};
      if (name) this.mode.looks[key] = name;
      else delete this.mode.looks[key];
      // An empty map is how "uses the palette" round-trips, and the Python
      // serialiser omits the key entirely - so drop it here too.
      if (!Object.keys(this.mode.looks).length) delete this.mode.looks;
    };

    const sharedBy = (name) => (this.handlers.getModes?.() || []).filter(
      (m) => m !== this.mode && Object.values(m.looks || {}).includes(name),
    ).length;

    const paint = () => {
      const current = this.handlers.getLooks?.() || {};
      const effect = current[select.value];
      clear(editorSlot);
      if (effect) {
        applySwatch(swatch, effect);
        summary.textContent = describeEffect(effect);
      } else {
        swatch.style.background = '';
        summary.textContent = select.value
          ? 'no such look'
          : 'the built-in colour for this state';
      }
      if (!effect) return;

      const editor = createLookEditor({
        get: () => effect,
        onChange: () => {
          applySwatch(swatch, effect);
          summary.textContent = describeEffect(effect);
          this.handlers.onLooksChanged?.();
        },
        floor: this.handlers.getFloor?.(),
        api: this.handlers.api,
        label: select.value,
        previewState: key,
        // This edits a *pool* look in place, and pool looks may be stop
        // lists - the same rule as the Lights tab's named-look rows.
        allowSequence: true,
      });
      editorSlot.append(editor.el);

      // Editing a shared look from here changes it everywhere, which is
      // the correct behaviour for a *named* look and a genuinely surprising
      // one if nobody says so. The copy button is the escape hatch, and it
      // is offered only when there is something to escape.
      const others = sharedBy(select.value);
      if (others) {
        editorSlot.append(el('div', { className: 'looks-shared' }, [
          el('span', {
            className: 'menu-hint',
            textContent: `Shared with ${others} other mode${others > 1 ? 's' : ''} - editing changes it for all of them.`,
          }),
          el('button', {
            type: 'button',
            textContent: 'Make a copy just for this mode',
            onclick: () => adopt(this.handlers.addLook?.(select.value, effect)),
          }),
        ]));
      }
    };

    // A look deleted from the pool leaves a dangling name. It stays listed,
    // marked, rather than silently snapping to the standard colour - the
    // Python parser warns about exactly this, and the two should agree.
    const rebuildOptions = (selected) => {
      const current = Object.keys(this.handlers.getLooks?.() || {}).sort();
      clear(select);
      select.append(el('option', { value: '', textContent: '- standard colour -' }));
      for (const n of current) select.append(el('option', { value: n, textContent: n }));
      if (selected && !current.includes(selected)) {
        select.append(el('option', { value: selected, textContent: `${selected} (missing)` }));
      }
      select.value = selected || '';
    };

    // Point this state at a look that has just been added to the pool.
    const adopt = (name) => {
      if (!name) return;
      rebuildOptions(name);
      setLook(name);
      paint();
      this._changed();
    };

    // Making a look from a preset, without going anywhere. This is the path
    // that replaces "add one in the Lights tab first" - the pool still owns
    // it afterwards, so nothing about the shared-look model changes.
    const fromPreset = el('select', {
      className: 'inp',
      onchange: () => {
        const preset = LOOK_PRESETS.find((p) => p.id === fromPreset.value);
        fromPreset.value = '';
        // `presetLook`, not `preset.effect` - **most presets have no
        // `effect`.** 105 of the 142 are sequence-only and carry `stops`
        // instead, so reading `.effect` gave `undefined`, `_addLook` spread
        // it into `{}`, and the new look arrived empty: the editor showed
        // "single colour" because an empty object has no stops, and the
        // colours you picked were never copied anywhere to come back from.
        // Reported 2026-08-26 as "it always defaults to single colour".
        // `presetLook` is `sequence || effect` **deep-copied**, and the copy
        // matters as much as the fallback: handing over `preset.effect`
        // directly would share the stops array with the module-level preset
        // table, so adding a row to your look would edit the preset for
        // every later use in that session. Every other preset consumer in
        // the app already goes through it; this was the one that did not.
        if (preset) adopt(this.handlers.addLook?.(preset.label, presetLook(preset)));
      },
    }, [
      el('option', { value: '', textContent: 'New look from a preset…' }),
      ...LOOK_PRESET_GROUPS.map((group) => el('optgroup', { label: group },
        LOOK_PRESETS.filter((p) => p.group === group).map(
          (p) => el('option', { value: p.id, textContent: p.label }),
        ))),
    ]);

    rebuildOptions(this.mode.looks?.[key] || '');
    paint();
    // `.palette-row` on purpose: `.look-entry.open > .palette-row` is what
    // gives the Lights tab's own open rows their indent and left border, and
    // this is a direct child of the same `.look-entry.open` wrapper.
    return el('div', { className: 'palette-row' }, [
      el('div', { className: 'looks-pick' }, [swatch, select, fromPreset, summary]),
      editorSlot,
    ]);
  }

  /**
   * The mode's lifecycle hooks - one action as the session starts, one as it
   * ends. Rendered by `_gesture`, because a hook *is* a binding and only what
   * triggers it differs, which is why adding these cost no new widget.
   *
   * Takeover-only: an everyday mode is never entered or left, so a hook on one
   * could never fire - the same fact the parser warns about, one step earlier.
   */
  _hooks() {
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    if (!descriptor || descriptor.nature !== 'takeover') {
      // Unmarked, not merely hidden: help.js unhides every
      // [data-tier="tinker"] node when Tinker goes on, so a marked empty row
      // would appear the moment it was switched on.
      return el('div', { hidden: true });
    }
    // `gestures` for the layout, because that is literally what this row holds
    // - a stack of gesture-rows - and a second class copying its four
    // properties would be a rule waiting to drift. `data-tier` moved to the
    // `<details>` wrapper `_body()` puts around this (TODO 85) - the whole
    // section disappears as one unit when Tinker is off, rather than leaving
    // an empty collapsed heading behind.
    const wrap = el('div', { className: 'gestures hooks-row' });
    // TODO 66: what on_exit actually hands a webhook or OSC binding, read
    // here rather than in main.py. In the order summary.clean will send it -
    // key-sorted, which is also OSC's argument order.
    if (descriptor.summaryKeys?.length) {
      const list = descriptor.summaryKeys
        .map((k) => `${k.key} (${k.about})`).join(', ');
      wrap.append(el('span', { className: 'fld-hint', 'data-help': true,
        textContent: `Reports on exit: ${list}.` }));
    }
    for (const hook of MODE_HOOKS) wrap.append(this._gesture(hook));
    return wrap;
  }

  /**
   * Rewrite the takeover mode's "how do I get in / how do I get out" lines.
   * Called on every edit - including edits to *other* modes, since what starts
   * this one lives in their gestures, not in this card.
   */
  refreshExplainers() {
    if (!this.howtoEl) return;
    clear(this.howtoEl);
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    // Everyday modes are never entered or left, so there is nothing to explain.
    if (!descriptor || descriptor.nature !== 'takeover') {
      this.howtoEl.hidden = true;
      return;
    }
    this.howtoEl.hidden = false;

    if (descriptor.startedBy === 'schedule') {
      this.howtoEl.append(el('p', {
        className: 'howto-line',
        textContent: `Starts ${describeActivation(this.mode.activation)}`,
      }));
    } else {
      const entries = findEntryPoints(this.mode, this.handlers.getModes?.() || []);
      this.howtoEl.append(entries.length
        ? el('p', { className: 'howto-line', textContent: `Start: ${entries.join(', or ')}` })
        : el('p', { className: 'howto-line howto-warn' }, [
          '⚠ Not reachable',
          el('span', {
            'data-help': true,
            textContent: ' - give a gesture the "Launch an app" action, pointing here.',
          }),
        ]));
    }

    const exit = describeExit(this.mode);
    if (exit) this.howtoEl.append(el('p', { className: 'howto-line', textContent: `Exit: ${exit}` }));
  }

  // Whether *this* mode is the last ambient (actions-template) mode with an
  // Always activation. Recomputed from the live sibling list every time,
  // never cached - the same reason config.py's `_ensure_ambient_always`
  // treats it as structural rather than a stored flag: a stored answer goes
  // stale the moment a sibling changes, and can be edited away exactly like
  // the mode it was meant to protect.
  _isOnlyAmbientAlways() {
    const isAmbientAlways = (m) => m.template === 'actions' && m.activation?.type === 'always';
    if (!isAmbientAlways(this.mode)) return false;
    const modes = this.handlers.getModes?.() || [];
    return modes.filter(isAmbientAlways).length <= 1;
  }

  /** What this page is editing, in the app paradigm's own words: an app's
   *  page is one *item* of that app - one of your alarms, one of your
   *  countdowns - and a gesture map's page is a menu. The nav groups by app
   *  and the App page lists the copies; this was the one screen still calling
   *  everything a mode (TODO 48c). "Menu" rather than "reflex" since TODO 75,
   *  where that word went to the thing that fires with nobody pressing. */
  _noun() {
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];
    if (!descriptor) return { kind: 'mode', label: '' };
    if (descriptor.nature !== 'takeover') return { kind: 'menu', label: '' };
    return { kind: 'item', label: descriptor.label };
  }

  _header() {
    const noun = this._noun();
    const name = el('input', {
      type: 'text', className: 'inp mode-name',
      value: this.mode.name || '',
      // Named for what it is: two alarms are two alarms, and "Mode name" was
      // the last place that called one of them a mode.
      placeholder: noun.kind === 'item' ? `${noun.label} name` : 'Menu name',
      oninput: () => { this.mode.name = name.value; this._changed(); },
    });

    // Filled in by setActive() from the host's own resolution - this is the
    // one place "which mode is actually in charge right now?" gets answered.
    this.activeEl = el('span', { className: 'mode-active', hidden: true });

    const btn = (text, title, className, onclick, disabled = false) => el('button', {
      type: 'button', className: `mini ${className}`, textContent: text, title, onclick, disabled,
    });
    // Reorder arrows only where order decides anything: everyday modes are
    // read top to bottom, takeover modes are found by name.
    const reorder = this.handlers.canReorder === false ? [] : [
      btn('↑', 'Move up - higher modes win', '', () => this.handlers.onMoveUp?.()),
      btn('↓', 'Move down - lower modes win', '', () => this.handlers.onMoveDown?.()),
    ];
    // Refused, not just discouraged: this mode is the only ambient mode left
    // with an Always activation, and deleting it would leave the button with
    // no mode to fall back on for an ordinary press. This protects the
    // invariant, not this particular mode - once a second Always-ambient mode
    // exists, either one may be deleted.
    const lastFloor = this._isOnlyAmbientAlways();
    return el('div', { className: 'mode-edit-head' }, [
      // The app this belongs to, stated rather than implied - the page is
      // reached from a list that groups by app, and arriving at a bare name
      // field lost that context.
      noun.kind === 'item'
        ? el('span', { className: 'mode-edit-app', textContent: noun.label })
        : el('span', { className: 'fld-label', textContent: 'Menu' }),
      name,
      this.activeEl,
      ...reorder,
      btn(
        '✕',
        lastFloor
          ? "Can't delete - this is the only menu that's always on, and the button needs one to fall back to."
          : `Delete “${this.mode.name || 'this one'}”`,
        'danger',
        () => this.handlers.onRemove?.(),
        lastFloor,
      ),
    ]);
  }

  // --- template picker (swaps the template body) ---------------------------

  /** "Stopwatch settings" - the app's own name, not a question (TODO 87).
   *
   *  A mode with a template this page does not know keeps the old wording:
   *  there is no name to put here, and inventing one is the classification a
   *  fallback may not invent (TODO 107). */
  _templateHeading() {
    const label = TEMPLATE_BY_TYPE[this.mode.template]?.label;
    return label ? `${label} settings` : 'What it does';
  }

  /**
   * The template's own fields, with the template itself stated rather than
   * offered (TODO 87).
   *
   * **This was a `<select>`, and it was the one control on the page that could
   * destroy the page it was on.** You reached here by opening this app, so a
   * dropdown saying "what it does" was redundant with where you were - and
   * changing it swapped the whole body, discarding every field the old
   * template owned. It looked like a label and behaved like a delete.
   *
   * Removing it rather than confirming it is what **TODO 88/101** decided:
   * once the nav groups items under the app they belong to, an item's template
   * is *which group it lives in*, and changing it means moving it. A select
   * that silently rehomes a row is not merely risky, it is describing
   * something the rest of the page no longer believes.
   *
   * So changing type is delete-and-add, which is what it always was
   * underneath. The line saying so is the whole replacement - a door people
   * used, removed in silence, is how a page earns a bug report.
   */
  _templatePicker() {
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template];

    this.templateBody = el('div', { className: 'tpl-body' });
    this._buildTemplateBody();

    const head = el('div', { className: 'pick-head' }, [
      el('span', { className: 'menu-hint', textContent: descriptor?.about || '' }),
    ]);
    head.hidden = !descriptor;
    return el('div', { className: 'pick-row' }, [
      head,
      this.templateBody,
      el('p', {
        className: 'menu-hint', 'data-help': true,
        textContent: 'This is what kind of app it is, and it does not change: '
          + 'add the one you want and delete this, which is what changing it '
          + 'always did underneath.',
      }),
    ]);
  }

  _buildTemplateBody() {
    clear(this.templateBody);
    const descriptor = TEMPLATE_BY_TYPE[this.mode.template] || TEMPLATES[0];
    if (descriptor.body === 'actions') {
      // Which gestures, and whether there is an unless-logged rule, are the
      // descriptor's business - both data rather than a branch on template
      // name, so a third gesture-mapped template costs nothing here.
      this.templateBody.append(this._gestures(descriptor));
      if (descriptor.unlessLogged !== false) this.templateBody.append(this._unlessLogged());
    }
    // An action bound to something that is not a press - an alarm going
    // unanswered, so far. Rendered by the same sub-editor a gesture and a hook
    // use, because all three *are* bindings and only the trigger differs.
    for (const binding of descriptor.bindings || []) {
      this.templateBody.append(this._gesture(binding));
    }
    if (descriptor.fields) {
      const grid = el('div', { className: 'tpl-fields' });
      for (const spec of descriptor.fields) {
        const field = createField(spec, this.mode, () => this._changed(), this._fieldCtx());
        grid.append(field.el);
        this._validators.push(field.validate);
        // Which element holds which config key, so a parser warning can mark
        // the field it is about rather than being printed into a banner the
        // next Save overwrites (TODO 62).
        this._byKey.set(spec.key, field.el);
      }
      this.templateBody.append(grid);
    }
  }

  // --- activation picker (swaps the activation body) -----------------------

  _activationPicker() {
    const tplDescriptor = TEMPLATE_BY_TYPE[this.mode.template] || TEMPLATES[0];
    const allowed = new Set(tplDescriptor.allowedActivations);
    const select = el('select', {
      className: 'inp',
      onchange: () => {
        this.mode.activation = ACTIVATION_BY_TYPE[select.value].defaults();
        this._build();
        this._changed();
      },
    }, ACTIVATIONS.filter((a) => allowed.has(a.type))
      .map((a) => el('option', { value: a.type, textContent: a.label })));
    select.value = this.mode.activation?.type || tplDescriptor.allowedActivations[0];

    // Same refusal as the delete button, same reason: switching this mode's
    // activation away from Always is exactly as destructive to the invariant
    // as deleting it would be, when nothing else is holding the floor up.
    if (this._isOnlyAmbientAlways()) {
      select.disabled = true;
      select.title = "Can't change - this is the only menu that's always on. "
        + 'Give another menu an Always activation first.';
    }

    this.activationBody = el('div', { className: 'act-body' });
    this._buildActivationBody();

    return el('div', { className: 'pick-row' }, [
      el('div', { className: 'pick-head' }, [select]),
      this.activationBody,
    ]);
  }

  _buildActivationBody() {
    clear(this.activationBody);
    const activation = this.mode.activation || {};
    if (activation.type === 'window') {
      this.activationBody.append(this._window(activation), this._days(activation));
    } else if (activation.type === 'schedule') {
      this.activationBody.append(this._scheduleTime(activation), this._days(activation));
    }
    // 'always' and 'manual' have no scope fields, so no body.
  }

  // window: optional [HH:MM, HH:MM] between range (may cross midnight).
  _window(activation) {
    const has = Array.isArray(activation.between);
    const sync = () => {
      if (toggle.checked) activation.between = [start.value, end.value];
      else delete activation.between;
      start.disabled = end.disabled = !toggle.checked;
      this._changed();
    };
    const toggle = el('input', { type: 'checkbox', checked: has, onchange: sync });
    const time = (value) => el('input', {
      type: 'time', className: 'inp', value, disabled: !has, oninput: sync,
    });
    const start = time(has ? activation.between[0] : '');
    const end = time(has ? activation.between[1] : '');
    const err = el('span', { className: 'fld-err' });

    this._validators.push(() => {
      const bad = toggle.checked && (!start.value || !end.value);
      err.textContent = bad ? 'Set both times' : '';
      return bad ? 'time window needs a start and an end' : null;
    });

    return el('div', { className: 'scope-row' }, [
      el('label', { className: 'fld-check' }, [toggle, el('span', { textContent: 'Only between' })]),
      start, el('span', { className: 'sep', textContent: '-' }), end, err,
    ]);
  }

  // schedule: a single fire time (required).
  _scheduleTime(activation) {
    const input = el('input', {
      type: 'time', className: 'inp', value: activation.at || '',
      oninput: () => { activation.at = input.value; this._changed(); },
    });
    const err = el('span', { className: 'fld-err' });
    this._validators.push(() => {
      const bad = !input.value;
      err.textContent = bad ? 'Set a time' : '';
      return bad ? 'a scheduled alarm needs a time' : null;
    });
    return el('div', { className: 'scope-row' }, [
      el('span', { className: 'scope-lbl', textContent: 'Fire at' }),
      input, err,
    ]);
  }

  // days: optional 3-letter weekday set, shared by window + schedule.
  _days(activation) {
    const chosen = new Set(Array.isArray(activation.days) ? activation.days : []);
    const row = el('div', { className: 'scope-row days-row' }, [
      el('span', { className: 'scope-lbl', textContent: 'On days' }),
    ]);
    for (const day of DAYS) {
      const cb = el('input', {
        type: 'checkbox', checked: chosen.has(day.key),
        onchange: () => {
          if (cb.checked) chosen.add(day.key);
          else chosen.delete(day.key);
          if (chosen.size) activation.days = DAYS.filter((d) => chosen.has(d.key)).map((d) => d.key);
          else delete activation.days;
          this._changed();
        },
      });
      row.append(el('label', { className: 'day-pill' }, [cb, el('span', { textContent: day.label })]));
    }
    return row;
  }

  // --- actions template body: unless_logged_today + gesture sub-editor -----

  _unlessLogged() {
    const input = el('input', {
      type: 'text', className: 'inp',
      value: this.mode.unless_logged_today || '', placeholder: 'event name (optional)',
      oninput: () => {
        const value = input.value.trim();
        if (value) this.mode.unless_logged_today = value;
        else delete this.mode.unless_logged_today;
        this._changed();
      },
    });
    return el('div', { className: 'scope-row' }, [
      el('span', { className: 'scope-lbl', textContent: 'Skip if already logged today' }),
      input,
    ]);
  }

  _gestures(descriptor) {
    const only = descriptor && descriptor.gestures;
    const offered = only ? GESTURES.filter((g) => only.includes(g.key)) : GESTURES;
    const wrap = el('div', { className: 'gestures' });
    for (const gesture of offered) wrap.append(this._gesture(gesture));
    return wrap;
  }

  _gesture(gesture) {
    // A sentinel, not an action type: naming a pooled action is a different
    // *way of holding* one, which is why it is absent from ACTIONS and from
    // the parser's kind branches. The leading underscores keep it out of the
    // namespace an action type could ever occupy.
    const NAMED = '__named__';
    // A binding may narrow what it will accept (MODE_HOOKS does; a gesture
    // does not). Offering an action the parser will drop is the failure this
    // list exists to prevent, and filtering here keeps it one rule rather than
    // a second sub-editor.
    // `appOnly` actions are never offered here: they are performed *by* a
    // running app (a position), and a gesture is answered at the ambient
    // layer where no app is running to perform one (TODO 74).
    const offered = gesture.actions
      ? ACTIONS.filter((a) => gesture.actions.includes(a.type))
      : ACTIONS.filter((a) => !a.appOnly);
    const select = el('select', {
      className: 'inp',
      onchange: () => {
        if (!select.value) delete this.mode[gesture.key];
        // An empty name rather than a guessed one: picking the pool's first
        // entry for someone would bind a gesture to an action they never
        // chose, and the validator below stops an empty one being saved.
        else if (select.value === NAMED) this.mode[gesture.key] = '';
        else this.mode[gesture.key] = ACTION_BY_TYPE[select.value].defaults();
        buildFields();
        this._changed();
      },
    }, [
      el('option', { value: '', textContent: '- do nothing -' }),
      ...offered.map((a) => el('option', { value: a.type, textContent: a.label })),
      el('option', { value: NAMED, textContent: 'Use a named action' }),
    ]);
    // A string binding is a pool reference (config.py's NamedAction). Read as
    // `?.action` it would show as "do nothing" and then be deleted on Save, so
    // the string case is checked first everywhere this method inspects one.
    const isNamed = (value) => typeof value === 'string';
    select.value = isNamed(this.mode[gesture.key])
      ? NAMED
      : (this.mode[gesture.key]?.action || '');

    const fields = el('div', { className: 'gesture-fields' });
    // Held in a stable array so the registered validator below always reads
    // the fields currently shown, even after the action type is swapped.
    const fieldValidators = [];

    const buildFields = () => {
      clear(fields);
      fieldValidators.length = 0;
      const action = this.mode[gesture.key];
      if (isNamed(action)) {
        const picker = this._namedActionField(gesture);
        fields.append(picker.el);
        fieldValidators.push(picker.validate);
        return;
      }
      // Looked up in `offered` rather than in the whole table, so an action
      // outside this binding's allow-list reads exactly like an unknown one:
      // the select above already shows "- do nothing -" for it, and fields
      // underneath a control that disowns them would be worse than none.
      const descriptor = action && offered.find((a) => a.type === action.action);
      if (!descriptor) return;
      for (const spec of descriptor.fields) {
        // `rebuild` lets a widget that writes *sibling* keys (the integration
        // picker fills in url + payload) redraw the fields it overwrote.
        // Scoped to this gesture's own field set, so redrawing one action
        // never disturbs another gesture's half-typed input.
        const ctx = { ...this._fieldCtx(), rebuild: buildFields };
        const field = createField(spec, action, () => this._changed(), ctx);
        fields.append(field.el);
        fieldValidators.push(field.validate);
      }
    };

    this._validators.push(() => {
      for (const validate of fieldValidators) {
        const error = validate();
        if (error) return `${gesture.label}: ${error}`;
      }
      return null;
    });

    buildFields();
    const row = el('div', { className: 'gesture-row' }, [
      el('div', { className: 'gesture-head' }, [
        el('span', { className: 'gesture-name', textContent: gesture.label }),
        select,
      ]),
      gesture.hint ? el('span', { className: 'fld-hint', 'data-help': true, textContent: gesture.hint }) : null,
      fields,
    ]);
    // A binding is a config key like any other - `short_press`, `on_exit` -
    // so a warning about one marks this row (TODO 62).
    this._byKey.set(gesture.key, row);
    return row;
  }

  /**
   * The body shown when a gesture is bound by name: a picker over the pool.
   * Returns the widget contract (`{el, validate}`) so `buildFields` treats it
   * exactly like any schema-driven field.
   */
  _namedActionField(gesture) {
    const names = Object.keys(this._actionPool()).sort();
    const current = this.mode[gesture.key];
    const options = [el('option', { value: '', textContent: '- pick one -' })];
    // A name whose pool entry has been deleted stays listed and stays
    // selected, marked: silently repointing this gesture at some other action
    // is exactly the rewrite a dangling name is designed to prevent.
    if (current && !names.includes(current)) {
      options.push(el('option', { value: current, textContent: `${current} (missing)` }));
    }
    options.push(...names.map((n) => el('option', { value: n, textContent: n })));

    const err = el('span', { className: 'fld-err' });
    const pick = el('select', {
      className: 'inp',
      onchange: () => {
        this.mode[gesture.key] = pick.value;
        err.textContent = '';
        this._changed();
      },
    }, options);
    pick.value = current || '';

    const hint = names.length
      ? 'Edited once in the Actions pool - every gesture naming it changes together.'
      : 'No named actions yet - make one below, or find the pool under Tinker at the foot of the page.';
    // TODO 61: this used to be prose describing where the pool was, on a page
    // that already scrolled. One button that makes an entry and picks it,
    // reusing the exact path the pool's own "+ Add" button takes.
    const make = this.handlers.addAction ? el('button', {
      type: 'button', className: 'mini', textContent: 'Make one',
      onclick: () => {
        const name = this.handlers.addAction();
        pick.append(el('option', { value: name, textContent: name }));
        pick.value = name;
        this.mode[gesture.key] = name;
        err.textContent = '';
        this._changed();
      },
    }) : null;
    return {
      el: el('label', { className: 'fld' }, [
        el('span', { className: 'fld-label', textContent: 'Named action' }),
        pick,
        make,
        el('span', { className: 'fld-hint', 'data-help': true, textContent: hint }),
        err,
      ]),
      validate: () => {
        const message = pick.value ? null : 'pick a named action, or choose another action type';
        err.textContent = message || '';
        return message;
      },
    };
  }

  /** Run every field validator; returns an array of error strings (empty = ok). */
  validate() {
    const errors = this._validators.map((v) => v()).filter(Boolean);
    // Validators write their own `.fld-err` as a side effect (widgets.js's
    // `wrap`), so this sweep runs after them rather than duplicating what
    // counts as an error (TODO 85).
    this._openSectionsWithProblems();
    return errors;
  }
}
