// Declarative description of the whole config surface. This is the menu's
// single extension point: to add an action type, a mode template, an
// activation, or a device setting, add a descriptor here - the mode editor,
// the summaries, and the form widgets are all data-driven from these tables
// and need no other change (Open/Closed). Keep this module DOM-free and
// side-effect-free.
//
// Field `kind`s are rendered by widgets.js: text | textarea | number |
// checkbox | json | select. Each field spec: { key, label, kind, required?,
// hint?, placeholder?, min?, max?, step?, options? }. Action/template
// `defaults()` must mirror the shapes the Python parser accepts in config.py.

export const GESTURES = [
  { key: 'short_press', label: 'Short press' },
  { key: 'long_press', label: 'Long press' },
  { key: 'double_tap', label: 'Double tap' },
];

export const DAYS = [
  { key: 'mon', label: 'Mon' },
  { key: 'tue', label: 'Tue' },
  { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' },
  { key: 'fri', label: 'Fri' },
  { key: 'sat', label: 'Sat' },
  { key: 'sun', label: 'Sun' },
];

// Names of the templates whose modes are takeovers - the only valid targets
// for an `enter_mode` action. Mirrors each template's `nature: 'takeover'`.
const TAKEOVER_TEMPLATES = new Set(['alarm', 'stopwatch', 'counter', 'pomodoro']);

// The assignable Pomodoro gesture commands (mirrors POMODORO_COMMANDS in
// config.py). The empty value leaves a gesture unmapped (does nothing).
const POMODORO_COMMAND_OPTIONS = [
  { value: 'start_pause', label: 'Start / Pause' },
  { value: 'restart', label: 'Restart' },
  { value: 'extend', label: 'Extend (+ minutes)' },
  { value: '', label: '— do nothing —' },
];

// Action primitives - the body of the `actions` template. The standalone
// `alarm` action is gone (alarms are now a template); `enter_mode` is the
// Phase 2 primitive that starts a takeover mode from a gesture.
export const ACTIONS = [
  {
    type: 'prompt',
    label: 'Ask the AI',
    fields: [
      { key: 'prompt', label: 'Prompt', kind: 'textarea', required: true,
        hint: 'Sent to the model; its reply is read back and shown.' },
      { key: 'label', label: 'Short label', kind: 'text',
        hint: 'Optional name shown in the status line and over Bluetooth.' },
    ],
    defaults: () => ({ action: 'prompt', prompt: '', label: '' }),
    describe: (a) => `Ask the AI: “${a.prompt || '…'}”`,
  },
  {
    type: 'log',
    label: 'Log an event',
    fields: [
      { key: 'event', label: 'Event name', kind: 'text', required: true,
        placeholder: 'meds_taken',
        hint: 'Counted and streak-tracked; shows up in Recent events.' },
    ],
    defaults: () => ({ action: 'log', event: '' }),
    describe: (a) => `Log event “${a.event || '…'}”`,
  },
  {
    type: 'timer_toggle',
    label: 'Start / stop a timer',
    fields: [
      { key: 'log_as', label: 'Timer name', kind: 'text', required: true,
        placeholder: 'focus',
        hint: 'First press starts; the next stops and records the elapsed time.' },
    ],
    defaults: () => ({ action: 'timer_toggle', log_as: '' }),
    describe: (a) => `Toggle timer “${a.log_as || '…'}”`,
  },
  {
    type: 'webhook',
    label: 'Call a webhook',
    fields: [
      { key: 'url', label: 'URL', kind: 'text', required: true,
        placeholder: 'https://…',
        hint: 'POSTed to on press - the IFTTT / Make / n8n / Home Assistant hook.' },
      { key: 'payload', label: 'Extra JSON payload', kind: 'json',
        hint: 'Optional object merged into the POST body (trigger, mode, ts are added for you).' },
    ],
    defaults: () => ({ action: 'webhook', url: '', payload: {} }),
    describe: (a) => `Webhook → ${a.url || '…'}`,
  },
  {
    type: 'enter_mode',
    label: 'Enter a mode',
    fields: [
      // Dynamic <select>: the options are the names of the current takeover
      // modes (stopwatch + counter) the user can start by hand. The widget
      // calls this with a context object whose `getModes()` returns the
      // sibling modes (injected by menu.js -> modeEditor -> createField), so
      // the picker stays in sync as modes are added/renamed without this
      // module knowing where the list lives (Dependency Inversion).
      { key: 'target', label: 'Mode to enter', kind: 'select', required: true,
        hint: 'A Stopwatch or Counter mode this gesture starts.',
        options: (ctx) => {
          const modes = (ctx && typeof ctx.getModes === 'function') ? ctx.getModes() : [];
          return (Array.isArray(modes) ? modes : [])
            .filter((m) => m && TAKEOVER_TEMPLATES.has(m.template)
              && m.template !== 'alarm' && typeof m.name === 'string' && m.name)
            .map((m) => ({ value: m.name, label: m.name }));
        } },
    ],
    defaults: () => ({ action: 'enter_mode', target: '' }),
    describe: (a) => `Enter “${a.target || '…'}”`,
  },
];

export const ACTION_BY_TYPE = Object.fromEntries(ACTIONS.map((a) => [a.type, a]));

/** One-line human summary of an action object, used by the mode editor. */
export function describeAction(action) {
  const descriptor = action && ACTION_BY_TYPE[action.action];
  return descriptor ? descriptor.describe(action) : JSON.stringify(action);
}

// --- Activations -----------------------------------------------------------
// What turns a mode on. Tagged by `.type`; fields stored flat on the
// activation object (except `type`). `custom: true` means modeEditor renders
// a bespoke body (the window/schedule day+time editors) rather than plain
// widget fields. `describe()` returns a one-line summary for the collapsed
// card. `defaults()` returns a fresh activation object.

function fmtDays(days) {
  if (!Array.isArray(days) || !days.length) return '';
  const order = DAYS.map((d) => d.key);
  const chosen = order.filter((k) => days.includes(k));
  if (chosen.length === 7) return 'every day';
  const labelOf = (k) => DAYS.find((d) => d.key === k)?.label || k;
  // Detect a single contiguous run for a compact "Mon-Fri" style.
  const idx = chosen.map((k) => order.indexOf(k));
  const contiguous = idx.every((n, i) => i === 0 || n === idx[i - 1] + 1);
  if (contiguous && chosen.length > 2) {
    return `${labelOf(chosen[0])}-${labelOf(chosen[chosen.length - 1])}`;
  }
  return chosen.map(labelOf).join(', ');
}

export const ACTIVATIONS = [
  {
    type: 'always',
    label: 'Always',
    custom: false,
    fields: [],
    defaults: () => ({ type: 'always' }),
    describe: () => 'always',
  },
  {
    type: 'window',
    label: 'Time window',
    custom: true, // between [HH:MM,HH:MM] + days editor
    defaults: () => ({ type: 'window' }),
    describe: (a) => {
      const span = Array.isArray(a.between) && a.between[0] && a.between[1]
        ? `${a.between[0]}-${a.between[1]}` : 'any time';
      const days = fmtDays(a.days);
      return days ? `${span} ${days}` : span;
    },
  },
  {
    type: 'schedule',
    label: 'At a time',
    custom: true, // at HH:MM + days editor
    defaults: () => ({ type: 'schedule', at: '07:00' }),
    describe: (a) => {
      const days = fmtDays(a.days);
      return `at ${a.at || '--:--'}${days ? ` ${days}` : ''}`;
    },
  },
  {
    type: 'manual',
    label: 'Entered from another mode',
    custom: false, // no scope fields - reached only via an enter_mode action
    fields: [],
    defaults: () => ({ type: 'manual' }),
    describe: () => 'entered from another mode',
  },
];

export const ACTIVATION_BY_TYPE = Object.fromEntries(ACTIVATIONS.map((a) => [a.type, a]));

/** One-line human summary of an activation object. */
export function describeActivation(activation) {
  const descriptor = activation && ACTIVATION_BY_TYPE[activation.type];
  return descriptor ? descriptor.describe(activation) : 'always';
}

// --- Templates -------------------------------------------------------------
// What kind of mode it is. The template determines a mode's nature
// (ambient -> always/window, takeover -> schedule) and which fields live
// flat on the mode object. `body: 'actions'` means modeEditor renders the
// gesture×action sub-editor; `fields` means plain widget fields. `defaults()`
// returns the flat template fields (no name/template/activation).
// `describe(mode)` returns a one-line summary of the mode's behaviour.
export const TEMPLATES = [
  {
    type: 'actions',
    label: 'Actions',
    nature: 'ambient',
    allowedActivations: ['always', 'window'],
    body: 'actions', // gesture×ACTIONS sub-editor + unless_logged_today
    // A non-empty prompt so a freshly added mode is valid by construction -
    // it parses, round-trips, and won't be dropped as an empty actions mode.
    defaults: () => ({
      short_press: { action: 'prompt', prompt: 'Tell me something interesting.', label: '' },
    }),
    describe: (mode) => {
      const parts = [];
      for (const g of GESTURES) {
        const action = mode[g.key];
        if (action && action.action) {
          const short = g.label.split(' ')[0].toLowerCase();
          parts.push(`${short}→${describeAction(action)}`);
        }
      }
      let summary = parts.length ? parts.join(' · ') : 'no gestures';
      if (mode.unless_logged_today) summary += ` (unless ${mode.unless_logged_today} logged)`;
      return summary;
    },
  },
  {
    type: 'alarm',
    label: 'Alarm',
    nature: 'takeover',
    allowedActivations: ['schedule'],
    body: 'fields',
    fields: [
      { key: 'message', label: 'Message', kind: 'text',
        hint: 'Shown while the alarm is ringing.' },
      { key: 'label', label: 'Short label', kind: 'text',
        hint: 'Optional name for the status line / Bluetooth.' },
      { key: 'snooze_minutes', label: 'Snooze minutes', kind: 'number', min: 0, step: 1,
        hint: 'Long-press snoozes for this long. 0 = long-press just dismisses.' },
      { key: 'dismiss_event', label: 'Log on dismiss', kind: 'text',
        hint: 'Optional event name logged when the alarm is dismissed.' },
    ],
    defaults: () => ({ message: '', label: '', snooze_minutes: 0, dismiss_event: '' }),
    describe: (mode) => {
      const snooze = Number(mode.snooze_minutes) > 0 ? `, snooze ${mode.snooze_minutes} min` : '';
      return `Alarm${mode.message ? ` “${mode.message}”` : ''}${snooze}`;
    },
  },
  {
    type: 'stopwatch',
    label: 'Stopwatch',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      { key: 'log_as', label: 'Timer name', kind: 'text', required: true,
        placeholder: 'focus',
        hint: 'What the elapsed time is logged as; short press laps, long press stops.' },
    ],
    defaults: () => ({ log_as: '' }),
    describe: (mode) => `Stopwatch “${mode.log_as || '…'}”`,
  },
  {
    type: 'counter',
    label: 'Counter',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      { key: 'event', label: 'Event name', kind: 'text', required: true,
        placeholder: 'gratitude',
        hint: 'Logged by each press’s increment; the 5-tap escape exits.' },
      { key: 'tap_increment', label: 'Short press +', kind: 'number', step: 1,
        hint: 'Amount a short press adds (default +1).' },
      { key: 'long_increment', label: 'Long press +', kind: 'number', step: 1,
        hint: 'Amount a long press adds (default +10).' },
      { key: 'double_increment', label: 'Double tap +', kind: 'number', step: 1,
        hint: 'Amount a double tap adds (default +20).' },
    ],
    defaults: () => ({ event: '', tap_increment: 1, long_increment: 10, double_increment: 20 }),
    describe: (mode) =>
      `Counter “${mode.event || '…'}” (+${mode.tap_increment ?? 1}/+${mode.long_increment ?? 10}/+${mode.double_increment ?? 20})`,
  },
  {
    type: 'pomodoro',
    label: 'Pomodoro',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      { key: 'work_minutes', label: 'Work minutes', kind: 'number', min: 1, step: 1,
        hint: 'Length of a focus interval (default 25). The 5-tap escape exits.' },
      { key: 'break_minutes', label: 'Break minutes', kind: 'number', min: 1, step: 1,
        hint: 'Length of a break interval (default 5). Work and break auto-repeat.' },
      { key: 'extend_minutes', label: 'Extend minutes', kind: 'number', min: 1, step: 1,
        hint: 'How much the “extend” command adds (default 10).' },
      { key: 'log_as', label: 'Log work as', kind: 'text', placeholder: 'pomodoro',
        hint: 'Each completed work block is logged under this name for daily totals.' },
      { key: 'short_press', label: 'Short press', kind: 'select', options: POMODORO_COMMAND_OPTIONS,
        hint: 'Assignable: what a short press does.' },
      { key: 'long_press', label: 'Long press', kind: 'select', options: POMODORO_COMMAND_OPTIONS },
      { key: 'double_tap', label: 'Double tap', kind: 'select', options: POMODORO_COMMAND_OPTIONS },
    ],
    defaults: () => ({
      work_minutes: 25, break_minutes: 5, extend_minutes: 10, log_as: 'pomodoro',
      short_press: 'start_pause', long_press: 'restart', double_tap: 'extend',
    }),
    describe: (mode) => `Pomodoro ${mode.work_minutes ?? 25}/${mode.break_minutes ?? 5} min`,
  },
];

export const TEMPLATE_BY_TYPE = Object.fromEntries(TEMPLATES.map((t) => [t.type, t]));

/** One-line human summary of a mode's behaviour, used by the modes list. */
export function describeTemplate(mode) {
  const descriptor = mode && TEMPLATE_BY_TYPE[mode.template];
  return descriptor ? descriptor.describe(mode) : (mode?.template || 'unknown');
}

// Top-level device settings, grouped only for layout. Keys and types mirror
// AppConfig in config.py (ble_device_name is intentionally editable but only
// takes effect on restart - the parser hot-reloads everything else).
export const SETTINGS_GROUPS = [
  {
    title: 'AI backends',
    fields: [
      { key: 'ollama_host', label: 'Remote Ollama host', kind: 'text' },
      { key: 'remote_model', label: 'Remote model', kind: 'text' },
      { key: 'local_ollama_host', label: 'Local Ollama host', kind: 'text' },
      { key: 'local_model', label: 'Local model', kind: 'text' },
      { key: 'prefer_remote', label: 'Prefer the remote backend', kind: 'checkbox' },
      { key: 'fallback_to_local', label: 'Fall back to local', kind: 'checkbox' },
      { key: 'remote_timeout_s', label: 'Remote timeout (s)', kind: 'number', min: 0, step: 0.5 },
      { key: 'local_timeout_s', label: 'Local timeout (s)', kind: 'number', min: 0, step: 1 },
    ],
  },
  {
    title: 'Device',
    fields: [
      { key: 'ble_device_name', label: 'Bluetooth name', kind: 'text',
        hint: 'Applied on restart (the BLE advertisement registers once at startup).' },
      { key: 'sounds_enabled', label: 'Feedback sounds', kind: 'checkbox' },
      { key: 'database_path', label: 'Event database path', kind: 'text' },
    ],
  },
  {
    title: 'Web server',
    fields: [
      { key: 'web_enabled', label: 'Web UI enabled', kind: 'checkbox',
        hint: 'Takes effect on restart.' },
      { key: 'web_host', label: 'Bind host', kind: 'text' },
      { key: 'web_port', label: 'Port', kind: 'number', min: 1, max: 65535, step: 1 },
    ],
  },
];
