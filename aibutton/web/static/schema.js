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

// Mirrors config.py's TRIGGER_TYPES, which mirrors device.py's TriggerType.
// A longer tap is a data change here and on the Python side: the wire has
// carried a tap count since protocol v1, so nothing needs reflashing.
export const GESTURES = [
  { key: 'short_press', label: 'Short press' },
  { key: 'long_press', label: 'Long press' },
  { key: 'double_tap', label: 'Double tap' },
  { key: 'triple_tap', label: 'Triple tap' },
  // Binding this makes the button count to five, which costs the double tap
  // its instant response (see max_taps_for). Worth saying in the UI, because
  // it is the one gesture whose cost is paid by the *other* gestures.
  { key: 'tap_5', label: 'Five taps',
    hint: 'Deliberately awkward - good for an on/off. Binding it slows every '
      + 'shorter tap slightly, because the button has to wait to be sure.' },
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
const TAKEOVER_TEMPLATES = new Set([
  'alarm', 'reminders', 'stopwatch', 'counter', 'pomodoro', 'metronome', 'countdown',
]);

// The default colour walk for a countdown - red while there is plenty of time,
// through to violet as it runs out, then the alarm. Mirrors
// _default_countdown_ramp() in config.py; positions are implied even here, and
// the ramp widget only pins them once you move one.
const COUNTDOWN_RAMP = [
  '#ff0000', '#ff8800', '#ffff00', '#00ff00', '#4b0082', '#8f00ff',
];

// What a gesture can be bound to inside a running Pomodoro. Mirrors
// POMODORO_COMMANDS in config.py; '' means the gesture does nothing.
const POMODORO_COMMANDS = [
  { value: '', label: '- do nothing -' },
  { value: 'toggle', label: 'Start / pause' },
  { value: 'restart', label: 'Restart the block' },
  { value: 'extend', label: 'Add more time' },
  { value: 'skip', label: 'Skip to the next block' },
  { value: 'exit', label: 'Leave the Pomodoro' },
];

// Action primitives - the body of the `actions` template. Two are gone:
// the standalone `alarm` action (alarms are a template now) and `prompt`
// (the on-device AI went with the Pi build - reach an AI through a webhook).
// `enter_mode` starts a takeover mode from a gesture.
export const ACTIONS = [
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
    label: 'Always on',
    custom: false,
    fields: [],
    defaults: () => ({ type: 'always' }),
    describe: () => 'always',
  },
  {
    type: 'window',
    label: 'Only during certain hours',
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
    label: 'At a set time each day',
    custom: true, // at HH:MM + days editor
    defaults: () => ({ type: 'schedule', at: '07:00' }),
    describe: (a) => {
      const days = fmtDays(a.days);
      return `at ${a.at || '--:--'}${days ? ` ${days}` : ''}`;
    },
  },
  {
    type: 'manual',
    label: 'Only when another mode starts it',
    custom: false, // no scope fields - reached only via an enter_mode action
    fields: [],
    defaults: () => ({ type: 'manual' }),
    describe: () => 'started by another mode',
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
//
// Takeover templates also carry the two things a user needs in order not to
// feel trapped, as data rather than as branches in the editor:
//   startedBy  'gesture' (an everyday mode's Enter a mode) | 'schedule'
//   exits(mode) one plain sentence: which press gets you back out
// These mirror the takeover loops in main.py - run_alarm, run_stopwatch,
// run_counter, run_pomodoro. Change a loop, change the sentence.
export const TEMPLATES = [
  {
    type: 'actions',
    ledStates: [],
    label: 'Actions',
    nature: 'ambient',
    allowedActivations: ['always', 'window'],
    body: 'actions', // gesture×ACTIONS sub-editor + unless_logged_today
    // A filled-in event name so a freshly added mode is valid by construction -
    // it parses, round-trips, and won't be dropped as an empty actions mode.
    defaults: () => ({
      short_press: { action: 'log', event: 'button_press' },
    }),
    describe: (mode) => {
      const parts = [];
      for (const g of GESTURES) {
        const action = mode[g.key];
        if (action && action.action) parts.push(`${g.label} → ${describeAction(action)}`);
      }
      let summary = parts.length ? parts.join(' · ') : 'nothing bound to any press yet';
      if (mode.unless_logged_today) summary += ` (skipped once ${mode.unless_logged_today} is logged today)`;
      return summary;
    },
  },
  {
    type: 'alarm',
    ledStates: ['ALERT'],
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
    startedBy: 'schedule',
    exits: (mode) => (Number(mode.snooze_minutes) > 0
      ? `any press; long press snoozes ${mode.snooze_minutes}m`
      : 'any press'),
    describe: (mode) => {
      const snooze = Number(mode.snooze_minutes) > 0 ? `, snooze ${mode.snooze_minutes} min` : '';
      return `Alarm${mode.message ? ` “${mode.message}”` : ''}${snooze}`;
    },
  },
  {
    type: 'reminders',
    ledStates: ['ALERT'],
    label: 'Reminder',
    nature: 'takeover',
    allowedActivations: ['schedule'],
    body: 'fields',
    fields: [
      { key: 'message', label: 'Message', kind: 'text',
        hint: 'Shown while the reminder is up.' },
      { key: 'label', label: 'Short label', kind: 'text',
        hint: 'Optional name for the status line.' },
      { key: 'chime', label: 'Chime once', kind: 'checkbox',
        hint: 'One tone when it fires. Off = the light only.' },
      { key: 'timeout_minutes', label: 'Give up after (minutes)', kind: 'number',
        min: 0, step: 1,
        hint: 'Stops flashing on its own after this long. 0 = waits forever.' },
      { key: 'cleared_event', label: 'Log on clear', kind: 'text',
        hint: 'Optional event name logged when you clear it. A timeout logs nothing.' },
    ],
    defaults: () => ({
      message: '', label: '', chime: true, timeout_minutes: 5, cleared_event: '',
    }),
    startedBy: 'schedule',
    exits: () => 'any press',
    describe: (mode) => {
      const quiet = mode.chime ? '' : ', silent';
      const gives = Number(mode.timeout_minutes) > 0
        ? `, gives up after ${mode.timeout_minutes} min` : '';
      return `Reminder${mode.message ? ` “${mode.message}”` : ''}${quiet}${gives}`;
    },
  },
  {
    type: 'stopwatch',
    ledStates: ['TIMING'],
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
    startedBy: 'gesture',
    exits: () => 'long press (short/double = lap)',
    describe: (mode) => `Stopwatch “${mode.log_as || '…'}”`,
  },
  {
    type: 'counter',
    ledStates: ['COUNTING'],
    label: 'Counter',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      { key: 'event', label: 'Event name', kind: 'text', required: true,
        placeholder: 'water',
        hint: 'Logged once per increment (short press / double tap); long press exits.' },
    ],
    defaults: () => ({ event: '' }),
    startedBy: 'gesture',
    exits: () => 'long press (short/double = +1)',
    describe: (mode) => `Counter “${mode.event || '…'}”`,
  },
  {
    type: 'metronome',
    ledStates: ['METRONOME'],
    label: 'Metronome',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    // The tempo itself is session state and is never stored. Everything here
    // is how the tempo gets read, bounded and shown.
    fields: [
      { key: 'start_bpm', label: 'Starting tempo (BPM)', kind: 'number', min: 1, step: 1,
        hint: 'What the light keeps time at before your first tap lands.' },
      { key: 'max_bpm', label: 'Fastest tempo (BPM)', kind: 'number', min: 1, step: 1,
        hint: 'Ceiling for what taps can register - stops one bounced press '
          + 'reading as a huge tempo. Raise it to go faster; the light stays '
          + 'safe by marking every Nth beat above ~180.' },
      { key: 'tap_history', label: 'Taps to average over', kind: 'number', min: 2, step: 1,
        hint: 'More = steadier but slower to follow you; fewer = twitchier.' },
      { key: 'reset_gap_s', label: 'Silence that restarts it (seconds)', kind: 'number',
        min: 0.1, step: 0.1,
        hint: 'A pause this long starts the average over instead of averaging in the gap.' },
      { key: 'sound_on_tap', label: 'Click on each tap', kind: 'checkbox',
        hint: 'Turn off to practise by light alone.' },
      { key: 'log_as', label: 'Log each session as', kind: 'text', required: true,
        placeholder: 'metronome',
        hint: 'One event per session, carrying the tempo you settled on.' },
    ],
    defaults: () => ({
      start_bpm: 120, max_bpm: 300, tap_history: 8, reset_gap_s: 2,
      sound_on_tap: true, log_as: 'metronome',
    }),
    startedBy: 'gesture',
    exits: () => 'long press (short/double = tap the tempo)',
    describe: (mode) => `Metronome from ${mode.start_bpm ?? 120} BPM`,
  },
];

TEMPLATES.push({
  type: 'countdown',
  ledStates: ['TIMING'],
  label: 'Countdown',
  nature: 'takeover',
  allowedActivations: ['manual'], // a countdown that starts itself is an alarm
  body: 'fields',
  // Colour first: what a mode looks like is how you recognise it going off
  // from across the room, so the ramp sits above the mechanics.
  fields: [
    { key: 'ramp', label: 'Colour as the time runs out', kind: 'ramp',
      hint: 'Left is a full timer, right is zero. Drag a colour to a different '
        + 'percent to hold it for longer.' },
    // A function, not an array: LED_STYLES is declared further down this
    // module, so reading it while TEMPLATES is still being built would hit the
    // temporal dead zone. Deferring to render time also keeps the two lists
    // from drifting. Styles that ignore `color` are filtered out - a rainbow
    // countdown would throw the ramp away.
    { key: 'style', label: 'How the light moves', kind: 'select',
      options: () => LED_STYLES
        .filter((s) => s.uses.includes('color'))
        .map((s) => ({ value: s.type, label: s.label })),
      hint: 'The colour comes from the ramp above; this is only the movement.' },
    { key: 'period_s', label: 'Seconds per flash', kind: 'number',
      min: 0.1, max: 600, step: 0.1,
      hint: 'Held steady the whole way through - the ramp moves, the rate does not.' },
    { key: 'minutes', label: 'Minutes', kind: 'number', min: 0.1, step: 1,
      hint: 'How long the countdown runs for.' },
    { key: 'label', label: 'Short label', kind: 'text',
      hint: 'Optional name for the status line. Defaults to the mode name.' },
    { key: 'ring_on_finish', label: 'Ring at zero', kind: 'checkbox',
      hint: 'Off = it finishes quietly, with just the light.' },
    { key: 'log_as', label: 'Log each finished run as', kind: 'text', required: true,
      placeholder: 'countdown',
      hint: 'Logged with the length it ran for. A cancelled run logs nothing.' },
  ],
  defaults: () => ({
    minutes: 10, label: '', style: 'flash', period_s: 1,
    ramp: COUNTDOWN_RAMP.map((color, index) => ({
      color, at: index / (COUNTDOWN_RAMP.length - 1),
    })),
    ring_on_finish: true, log_as: 'countdown',
  }),
  startedBy: 'gesture',
  exits: (mode) => (mode.ring_on_finish
    ? 'long press; at zero it rings until any press'
    : 'long press (it finishes on its own)'),
  describe: (mode) => `Countdown ${mode.minutes ?? 10} min`,
});

TEMPLATES.push({
  type: 'pomodoro',
  ledStates: ['WORKING', 'RESTING'],
  label: 'Pomodoro',
  nature: 'takeover',
  allowedActivations: ['manual'], // started by an enter_mode gesture only
  body: 'fields',
  fields: [
    { key: 'work_minutes', label: 'Work minutes', kind: 'number', min: 0.1, step: 1,
      hint: 'How long one focus block lasts.' },
    { key: 'break_minutes', label: 'Break minutes', kind: 'number', min: 0.1, step: 1,
      hint: 'The short break after each work block.' },
    { key: 'long_break_minutes', label: 'Long break minutes', kind: 'number', min: 0.1, step: 1,
      hint: 'The longer break you get after the number of blocks set below.' },
    { key: 'blocks_before_long_break', label: 'Blocks before a long break', kind: 'number', min: 1, step: 1,
      hint: 'How many work blocks to finish before the long break.' },
    { key: 'advance', label: 'Between blocks', kind: 'select',
      hint: 'How much the button asks of you when a block ends.',
      options: [
        { value: 'auto', label: 'Start the next block automatically' },
        { value: 'manual', label: 'Wait for a press every time' },
        { value: 'break_only', label: 'Breaks start themselves, work waits for a press' },
      ] },
    { key: 'extend_minutes', label: 'Minutes added by "Add more time"', kind: 'number', min: 0.1, step: 1,
      hint: 'How much time the "Add more time" gesture puts back on the clock.' },
    { key: 'log_as', label: 'Log each finished block as', kind: 'text', required: true,
      placeholder: 'pomodoro',
      hint: 'Counted and streak-tracked like any other event.' },
    { key: 'short_press', label: 'Short press does', kind: 'select', options: POMODORO_COMMANDS,
      hint: 'What this press does while the Pomodoro is running.' },
    { key: 'long_press', label: 'Long press does', kind: 'select', options: POMODORO_COMMANDS,
      hint: 'Leave at least one gesture on "Leave the Pomodoro" or you cannot get out.' },
    { key: 'double_tap', label: 'Double tap does', kind: 'select', options: POMODORO_COMMANDS,
      hint: 'What this press does while the Pomodoro is running.' },
  ],
  defaults: () => ({
    work_minutes: 25, break_minutes: 5, long_break_minutes: 15,
    blocks_before_long_break: 4, extend_minutes: 10, advance: 'auto',
    log_as: 'pomodoro',
    short_press: 'toggle', long_press: 'exit', double_tap: 'extend',
  }),
  startedBy: 'gesture',
  exits: (mode) => {
    const leaving = GESTURES.filter((g) => mode[g.key] === 'exit');
    if (!leaving.length) return 'nothing set - pick a gesture below';
    return leaving.map((g) => g.label).join(' or ');
  },
  describe: (mode) => {
    const advance = { auto: 'auto', manual: 'press to advance', break_only: 'auto breaks' };
    return `Pomodoro ${mode.work_minutes}/${mode.break_minutes}`
      + ` (${advance[mode.advance] || mode.advance})`;
  },
});

export const TEMPLATE_BY_TYPE = Object.fromEntries(TEMPLATES.map((t) => [t.type, t]));

// Ready-made modes, offered next to "+ Add mode". Each is a complete mode
// object the parser accepts as-is - a starting point to edit, not a special
// kind of mode. Names are checked for collisions when one is added.
export const BUILTIN_MODES = [
  {
    id: 'pomodoro',
    label: 'Pomodoro',
    blurb: '25/5, long break every 4th. Tap = pause, double = +10.',
    mode: () => ({
      name: 'Pomodoro', template: 'pomodoro', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.pomodoro.defaults(),
    }),
  },
  {
    id: 'gratitude',
    label: 'Gratitude counter',
    blurb: 'Tap once per thing you’re grateful for.',
    mode: () => ({
      name: 'Gratitude', template: 'counter', activation: { type: 'manual' },
      event: 'gratitude',
    }),
  },
  {
    id: 'stopwatch',
    label: 'Stopwatch',
    blurb: 'Short press = lap, long press = stop & log.',
    mode: () => ({
      name: 'Stopwatch', template: 'stopwatch', activation: { type: 'manual' },
      log_as: 'stopwatch',
    }),
  },
  {
    id: 'countdown',
    label: 'Countdown (10 min)',
    blurb: 'Flashes red, fading through to violet as the time runs out.',
    mode: () => ({
      name: 'Countdown', template: 'countdown', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.countdown.defaults(),
    }),
  },
  {
    id: 'alarm5am',
    label: '5AM alarm',
    blurb: 'Rings 05:00 daily. Long press snoozes 9m.',
    mode: () => ({
      name: 'Wake up', template: 'alarm',
      activation: { type: 'schedule', at: '05:00' },
      message: 'Wake up', label: '', snooze_minutes: 9, dismiss_event: 'woke_up',
    }),
  },
  {
    id: 'metronome',
    label: 'Metronome',
    blurb: 'Tap out a beat to set the tempo; the LED pulses along with it.',
    mode: () => ({
      name: 'Metronome', template: 'metronome', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.metronome.defaults(),
    }),
  },
];

/** One-line human summary of a mode's behaviour, used by the modes list. */
export function describeTemplate(mode) {
  const descriptor = mode && TEMPLATE_BY_TYPE[mode.template];
  return descriptor ? descriptor.describe(mode) : (mode?.template || 'unknown');
}

// --- explaining the two ways a mode comes on -------------------------------
// The single most confusing thing about this config is that "switching modes"
// means two unrelated mechanisms. The editor groups by `nature` and prints
// these blurbs above each group, so the distinction is stated rather than
// left to be inferred from which activations a template happens to allow.

export const MODE_GROUPS = [
  {
    nature: 'ambient',
    title: 'Everyday',
    blurb: 'What a press does normally. The button reads these top to bottom and '
      + 'uses the first one that is switched on right now and has something set for '
      + 'the press you made. Order is priority: move a mode up to let it win. A mode '
      + 'that does not set a gesture passes it down to the next one.',
    emptyText: 'None yet.',
  },
  {
    nature: 'takeover',
    title: 'Takeover',
    blurb: 'While one of these is running it owns every press and your everyday modes '
      + 'are ignored until you leave it. An alarm starts itself at its set time; the '
      + 'others are started by an everyday mode with an “Enter a mode” gesture.',
    emptyText: 'None yet.',
  },
];

/** How you leave a takeover mode, in one sentence. Null for everyday modes,
 *  which are never entered and so never need leaving. */
export function describeExit(mode) {
  const descriptor = mode && TEMPLATE_BY_TYPE[mode.template];
  return descriptor && descriptor.exits ? descriptor.exits(mode) : null;
}

/** Every gesture, in any other mode, that starts `mode` — the answer to "how
 *  do I get into this?". An empty list means nothing can start it, which is a
 *  mode you can configure but never reach. */
export function findEntryPoints(mode, allModes) {
  const entries = [];
  if (!mode || !mode.name) return entries;
  for (const other of allModes || []) {
    if (!other || other === mode) continue;
    for (const gesture of GESTURES) {
      const action = other[gesture.key];
      if (action && action.action === 'enter_mode' && action.target === mode.name) {
        entries.push(`${gesture.label} → ${other.name || '(unnamed)'}`);
      }
    }
  }
  return entries;
}

// --- LED palette -----------------------------------------------------------
// What each device state looks like. Mirrors LedEffect + _default_palette in
// config.py and the style codes in device.py/firmware/protocol.py; the host
// pushes any edit to the ESP32, so these are the real LED, not a preview.
//
// `uses` says which fields a style actually reads, so the editor can hide the
// ones that would do nothing (a rainbow has no colour; a solid has no period)
// rather than inviting edits with no effect. index.html renders the virtual
// device from these same definitions.

export const LED_STYLES = [
  { type: 'solid', label: 'Solid', uses: ['color'],
    describe: () => 'held' },
  { type: 'breathe', label: 'Breathe', uses: ['color', 'period_s'],
    describe: (e) => `fading every ${e.period_s}s` },
  // `strobes` marks the hard on/off styles - the ones the flash floor applies
  // to. Mirrors device.py's STYLE_STROBES; test_webui.py fails if they drift.
  // A property of the style rather than a list in the renderer, so a new style
  // declares whether it strobes instead of the floor having to learn its name.
  { type: 'flash', label: 'Flash', uses: ['color', 'period_s'], strobes: true,
    describe: (e) => `blinking every ${e.period_s}s` },
  { type: 'alternate', label: 'Alternate two colours', uses: ['color', 'color2', 'period_s'],
    strobes: true,
    describe: (e) => `swapping every ${e.period_s}s` },
  { type: 'fade', label: 'Fade between two colours', uses: ['color', 'color2', 'period_s'],
    describe: (e) => `crossfading every ${e.period_s}s` },
  { type: 'rainbow', label: 'Rainbow', uses: ['period_s'],
    describe: (e) => `cycling every ${e.period_s}s` },
];

export const LED_STYLE_BY_TYPE = Object.fromEntries(LED_STYLES.map((s) => [s.type, s]));

// The states the device can be in, in the order they happen to a press, with
// what each one means - the editor doubles as the reference for "what is my
// button telling me?".
export const LED_STATES = [
  { key: 'IDLE', label: 'Idle', meaning: 'waiting, nothing going on' },
  { key: 'LISTENING', label: 'Listening', meaning: 'your press registered' },
  { key: 'THINKING', label: 'Thinking', meaning: 'running the action' },
  { key: 'SUCCESS', label: 'Success', meaning: 'the action worked' },
  { key: 'ERROR', label: 'Error', meaning: 'it failed, or no mode matched' },
  { key: 'ALERT', label: 'Alarm ringing', meaning: 'an alarm is going off' },
  { key: 'TIMING', label: 'Stopwatch running', meaning: 'a stopwatch is open' },
  { key: 'COUNTING', label: 'Counter open', meaning: 'a counter is open' },
  { key: 'WORKING', label: 'Pomodoro working', meaning: 'a work block is running' },
  { key: 'RESTING', label: 'Pomodoro resting', meaning: 'a break is running' },
  { key: 'METRONOME', label: 'Metronome running', meaning: 'pulses at the tapped tempo' },
];

// The split the Lights tab and the mode editor divide on, derived from the
// templates rather than listed again: a state named by some template's
// `ledStates` belongs to whichever mode is running, and the rest belong to the
// button itself. Mirrors MODE_LED_STATES / SYSTEM_LED_STATES in config.py;
// test_webui.py fails if they drift.
export const MODE_LED_STATE_KEYS = new Set(
  TEMPLATES.flatMap((t) => t.ledStates || []),
);
export const SYSTEM_LED_STATES = LED_STATES.filter(
  (s) => !MODE_LED_STATE_KEYS.has(s.key),
);
export const MODE_LED_STATES = LED_STATES.filter(
  (s) => MODE_LED_STATE_KEYS.has(s.key),
);
export const LED_STATE_BY_KEY = Object.fromEntries(LED_STATES.map((s) => [s.key, s]));

export const LED_FIELDS = [
  { key: 'style', label: 'Style', kind: 'select',
    options: LED_STYLES.map((s) => ({ value: s.type, label: s.label })) },
  { key: 'color', label: 'Colour', kind: 'color' },
  { key: 'color2', label: 'Second colour', kind: 'color' },
  // A slider rather than a number box, and its floor is the *configured*
  // flash limit rather than a constant, so it cannot offer a rate the parser
  // has been told to floor. Styles that do not strobe (breathe, fade, rainbow)
  // are not subject to it - `ctx.minFlashPeriod` is resolved per render by
  // whoever builds the row, which is the only place that knows the style.
  { key: 'period_s', label: 'Seconds per cycle', kind: 'range',
    min: (ctx) => ctx?.minFlashPeriod ?? 0.05, max: 10, step: 0.01,
    describe: (v) => `${v.toFixed(2)}s`,
    hint: 'How long one full cycle takes.' },
];

/** One-line summary of an effect, e.g. "Breathe #0000ff, fading every 3s". */
export function describeEffect(effect) {
  const style = effect && LED_STYLE_BY_TYPE[effect.style];
  if (!style) return 'unknown';
  const swatch = style.uses.includes('color') ? ` ${effect.color}` : '';
  return `${style.label}${swatch}, ${style.describe(effect)}`;
}

// Top-level device settings, grouped only for layout. Keys and types mirror
// AppConfig in config.py (ble_device_name is intentionally editable but only
// takes effect on restart - the parser hot-reloads everything else).
export const SETTINGS_GROUPS = [
  {
    title: 'Device',
    fields: [
      { key: 'ble_device_name', label: 'Bluetooth name', kind: 'text',
        hint: 'The name the button advertises; the host connects to it by name.' },
      { key: 'sounds_enabled', label: 'Feedback sounds', kind: 'checkbox' },
      { key: 'database_path', label: 'Event database path', kind: 'text' },
      // The one setting whose default exists for a medical reason rather than
      // a taste one. It is editable because this is one button on one desk and
      // its owner may decide it can go faster; the hint has to say what that
      // costs, because nothing else in the UI will.
      { key: 'min_flash_period_s', label: 'Fastest the light may flash',
        kind: 'range', min: 0.05, max: 2, step: 0.01,
        describe: (v) => `${v.toFixed(2)}s (${(1 / v).toFixed(1)} flashes/sec)`,
        hint: 'Floor for flash + alternate. 0.33s = 3/sec, the recommended '
          + 'photosensitivity limit. Faster is allowed and is a seizure risk.' },
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
