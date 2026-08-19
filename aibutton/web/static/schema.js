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
  'hotcold', 'reaction', 'signal',
  // A launcher is a takeover, so a gesture can reach it - but it is never a
  // valid `enter_mode` *target* offered by another launcher (see
  // launcher_targets in main.py). That exclusion lives host-side because it
  // is a runtime rule, not a shape rule.
  'launcher',
]);

// The default colour walk for a countdown - red while there is plenty of time,
// through to violet as it runs out, then the alarm. Mirrors
// _default_countdown_ramp() in config.py; positions are implied even here, and
// the ramp widget only pins them once you move one.
const COUNTDOWN_RAMP = [
  '#ff0000', '#ff8800', '#ffff00', '#00ff00', '#4b0082', '#8f00ff',
];

// Cold to hot, for Hot/Cold's "how close were you" flash. Mirrors
// _default_hotcold_ramp() in config.py. Five stops rather than two because the
// blend is a straight RGB lerp, and blue straight to red goes through a grey
// that reads as the light having given up.
const HOTCOLD_RAMP = [
  '#0000ff', '#00ffff', '#00ff00', '#ffff00', '#ff0000',
];

// Sluggish to sharp, for the reaction timer. Mirrors
// _default_reaction_ramp() in config.py. Walked by how *well* you did rather
// than by how long you took, which is why green is at the far end here and
// red is at the far end of the countdown's.
const REACTION_RAMP = ['#ff0000', '#ff8800', '#ffff00', '#00ff00'];

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

// Named services the webhook action can be pointed at, offered as a
// "start from" picker above the URL field.
//
// **They are all the same action.** Every entry here is a `webhook` with its
// URL shape and payload pre-filled - there is no per-brand code, no SDK and no
// dependency, which is exactly why a list like this is affordable at all. The
// button gets to look like it integrates with eight services because the
// services all agreed on HTTP POST years ago.
//
// Two honest caveats, both stated in the hints rather than hidden:
//
//   - Hosts drift. Make has regional subdomains, n8n and Home Assistant are
//     wherever you put them. Every template carries obvious YOUR_ tokens and
//     none of them is a working URL until you paste yours in.
//   - This is the one place the button talks to the outside world on purpose.
//     ROADMAP's "nothing is extracted from the user" is a promise about the
//     *product* not phoning home; a webhook you configured is your own call,
//     and it is worth knowing it leaves the machine.
//
// **MCP is deliberately not here.** It is not webhook-shaped: an MCP server is
// something a model calls *into*, so it would mean the button exposing a
// server over its own event log and config, not making a request. That is the
// parked "second control surface" item in TODO.md's parking lot, and putting a
// broken entry in this list would be worse than leaving it out.
export const INTEGRATIONS = [
  {
    id: 'ifttt',
    label: 'IFTTT',
    blurb: 'Webhooks applet - one event name per applet.',
    url: 'https://maker.ifttt.com/trigger/EVENT_NAME/with/key/YOUR_KEY',
    payload: { value1: '', value2: '', value3: '' },
    hint: 'From IFTTT: Create -> Webhooks -> "Receive a web request". The '
      + 'three value1/2/3 fields are the only ones applets can read.',
  },
  {
    id: 'make',
    label: 'Make',
    blurb: 'Custom webhook trigger (was Integromat).',
    url: 'https://hook.REGION.make.com/YOUR_WEBHOOK_ID',
    payload: {},
    hint: 'Copy the whole URL from the Custom Webhook module - the region '
      + 'part differs per account, so do not hand-type it.',
  },
  {
    id: 'zapier',
    label: 'Zapier',
    blurb: 'Catch Hook trigger.',
    url: 'https://hooks.zapier.com/hooks/catch/YOUR_ID/YOUR_HOOK/',
    payload: {},
    hint: 'Zapier reads whatever JSON arrives, so the trigger/mode/ts fields '
      + 'the button adds are usable as Zap fields with no extra payload.',
  },
  {
    id: 'home_assistant',
    label: 'Home Assistant',
    blurb: 'Webhook trigger on a local automation.',
    url: 'http://homeassistant.local:8123/api/webhook/YOUR_WEBHOOK_ID',
    payload: {},
    hint: 'Local and needs no token - a webhook trigger is deliberately '
      + 'unauthenticated, so treat the ID as the secret.',
  },
  {
    id: 'n8n',
    label: 'n8n',
    blurb: 'Webhook node, self-hosted or cloud.',
    url: 'https://YOUR_HOST/webhook/YOUR_PATH',
    payload: {},
    hint: 'Use the Production URL, not the Test URL - the test one only '
      + 'listens while you have the editor open.',
  },
  {
    id: 'slack',
    label: 'Slack',
    blurb: 'Incoming webhook, posts a message.',
    url: 'https://hooks.slack.com/services/YOUR_TEAM/YOUR_CHANNEL/YOUR_TOKEN',
    payload: { text: 'Button pressed' },
    hint: 'Slack only reads "text" here; the other fields ride along and are '
      + 'ignored.',
  },
  {
    id: 'discord',
    label: 'Discord',
    blurb: 'Channel webhook, posts a message.',
    url: 'https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN',
    payload: { content: 'Button pressed' },
    hint: 'Discord only reads "content" here. Server Settings -> Integrations '
      + '-> Webhooks.',
  },
  {
    id: 'node_red',
    label: 'Node-RED',
    blurb: 'http in node on your own flow.',
    url: 'http://YOUR_HOST:1880/YOUR_ENDPOINT',
    payload: {},
    hint: 'Pair the http in node with an http response node or the request '
      + 'hangs until it times out.',
  },
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
      // An inserter, not a setting: it writes the two fields below and stores
      // nothing of its own, which is why it needs no place in WebhookAction
      // and no round-trip. Picking one twice is idempotent; editing the URL
      // afterwards is the normal case.
      { key: 'integration', label: 'Start from a service', kind: 'preset',
        presets: () => INTEGRATIONS,
        hint: 'Fills in the URL shape and payload below. Every template has '
          + 'YOUR_ placeholders to replace - none is a working URL as-is.' },
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
    type: 'osc',
    label: 'Send an OSC message',
    fields: [
      { key: 'address', label: 'OSC address', kind: 'text', required: true,
        placeholder: '/transport/play',
        hint: 'The path your software listens on. Must start with a slash - '
          + 'a typo here reaches the wrong handler rather than failing.' },
      { key: 'host', label: 'Host', kind: 'text', required: true,
        placeholder: '127.0.0.1',
        hint: 'An IP is best. A hostname works and costs a lookup on the '
          + 'first press.' },
      { key: 'port', label: 'Port', kind: 'number', min: 1, max: 65535, step: 1,
        hint: 'Whatever the receiving end is listening on - Reaper, TouchOSC, '
          + 'QLab, Resolume, VCV Rack.' },
      { key: 'args', label: 'Arguments', kind: 'json',
        hint: 'A JSON list. Types are inferred: true/false go as OSC T/F, '
          + 'whole numbers as int, decimals as float, anything else as text. '
          + 'Most receivers want [1] to mean "pressed".' },
    ],
    defaults: () => ({
      action: 'osc', host: '127.0.0.1', port: 8000, address: '', args: [1],
    }),
    // No delivery to report: OSC is UDP, so the arrow means "sent at".
    describe: (a) => `OSC ${a.address || '…'} → ${a.host || '…'}:${a.port ?? '…'}`,
  },
  {
    type: 'enter_mode',
    label: 'Enter a mode',
    fields: [
      // Dynamic <select>: the options are the takeover modes a gesture can
      // actually start - every template whose descriptor says
      // `startedBy: 'gesture'`, which excludes the schedule-started ones
      // (alarm, reminders) that a clock owns instead. The widget
      // calls this with a context object whose `getModes()` returns the
      // sibling modes (injected by menu.js -> modeEditor -> createField), so
      // the picker stays in sync as modes are added/renamed without this
      // module knowing where the list lives (Dependency Inversion).
      { key: 'target', label: 'Mode to enter', kind: 'select', required: true,
        hint: 'Which app this gesture opens. Schedule-started modes '
          + '(alarm, reminder) are not listed - a clock starts those.',
        options: (ctx) => {
          const modes = (ctx && typeof ctx.getModes === 'function') ? ctx.getModes() : [];
          return (Array.isArray(modes) ? modes : [])
            .filter((m) => m && TAKEOVER_TEMPLATES.has(m.template)
              && TEMPLATE_BY_TYPE[m.template]?.startedBy === 'gesture'
              && typeof m.name === 'string' && m.name)
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

/**
 * A duration in seconds, written the way a person would say it. Mirrors the
 * `duration` widget's unit inference so a summary and the field you edit it in
 * never disagree about whether something is "25 min" or "1500 sec".
 */
export function fmtDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return '0s';
  if (value >= 60 && value % 60 === 0) return `${value / 60}m`;
  return `${value}s`;
}

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
// A subdivision ladder: the light as a clock. Mirrors config.py's LadderSpec
// and _default_rungs - the intervals and colours have to match, because the
// editor seeding different defaults from the parser is how a "new mode" and a
// "saved mode" end up looking different for no visible reason.
//
// Why these colours: the *rate* tells you the unit before you know the code,
// and the two most frequent ones are a light/dark pair rather than two hues,
// which survives both this build's warm ring cast and a colourblind reader.
export function defaultLadder() {
  return {
    enabled: false,
    tick_s: 0.5,
    base: '#000000',
    rungs: [
      { every_s: 10, color: '#ffffff' },
      { every_s: 5, color: '#ffff00' },
      { every_s: 2, color: '#66ccff' },
      { every_s: 1, color: '#0033aa' },
    ],
  };
}

// Shared by every template with a time reference, so turning the light into a
// clock is one descriptor rather than one per mode.
//
// `unit` is why this is a descriptor and not a hard-coded widget: the ladder
// itself just counts, and what it counts is the consumer's business. Timers
// count seconds; the metronome counts *beats*, because a tempo already decides
// the timing and what a colour adds there is an accent.
const LADDER_FIELD = {
  key: 'ladder', label: 'Tell the time with the light', kind: 'ladder',
  unit: 's', showTick: true,
  hint: 'Each tick takes the colour of the longest interval that divides it: '
    + '10s white, 5s yellow, even seconds light blue, odd dark. Off-beat ticks '
    + 'get the off-beat colour.',
};

const LADDER_BEATS_FIELD = {
  key: 'ladder', label: 'Colour the beats', kind: 'ladder',
  unit: ' beats', showTick: false,
  hint: 'Accents by beat number: every 4th beat one colour, every 2nd another. '
    + 'The tempo you tap supplies the timing, so there is no tick to set.',
};

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
      LADDER_FIELD,
      { key: 'log_as', label: 'Timer name', kind: 'text', required: true,
        placeholder: 'focus',
        hint: 'What the elapsed time is logged as; short press laps, long press stops.' },
    ],
    defaults: () => ({ log_as: '', ladder: defaultLadder() }),
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
    // ledStates is none, deliberately: the launcher wears whichever app is
    // selected, in that app's own colour, so a look of its own would only ever
    // hide the thing you are reading. (The comment sits above `type` because
    // test_webui.py's drift guard reads the two lines as a pair.)
    type: 'launcher',
    ledStates: [],
    label: 'App launcher',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      { key: 'targets', label: 'Apps to offer', kind: 'textarea',
        placeholder: 'One mode name per line - blank = every app',
        hint: 'Blank offers every takeover mode, so a new app appears here on '
          + 'its own. List names to shorten or reorder the menu.' },
      { key: 'return_after', label: 'Return here when an app exits',
        kind: 'checkbox',
        hint: 'On = long press means "up one level" everywhere: out of an app '
          + 'lands here, out of here goes home. Off skips this menu.' },
      { key: 'log_as', label: 'Log each launch as', kind: 'text',
        placeholder: 'launched',
        hint: 'Optional. One event per launch, so you can see which apps you '
          + 'actually use.' },
    ],
    defaults: () => ({ targets: '', return_after: true, log_as: '' }),
    startedBy: 'gesture',
    exits: () => 'long press (short = next app, double tap = launch)',
    describe: (mode) => {
      const listed = String(mode.targets || '').trim();
      const count = listed ? listed.split(/\n+/).filter(Boolean).length : 0;
      return count ? `Launcher over ${count} chosen app(s)` : 'Launcher over every app';
    },
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
      LADDER_BEATS_FIELD,
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
      // Beats, not seconds: bar-ish accents rather than a clock.
      ladder: { ...defaultLadder(), tick_s: 1, rungs: [
        { every_s: 4, color: '#ffffff' },
        { every_s: 2, color: '#66ccff' },
        { every_s: 1, color: '#0033aa' },
      ] },
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
    // The ladder and the ramp both decide *which* colour, so only one runs -
    // the ladder wins when it is on. It sits after the ramp for that reason:
    // turning it on is what makes the fields above it stop mattering.
    LADDER_FIELD,
    { key: 'log_as', label: 'Log each finished run as', kind: 'text', required: true,
      placeholder: 'countdown',
      hint: 'Logged with the length it ran for. A cancelled run logs nothing.' },
  ],
  defaults: () => ({
    minutes: 10, label: '', style: 'flash', period_s: 1,
    ramp: COUNTDOWN_RAMP.map((color, index) => ({
      color, at: index / (COUNTDOWN_RAMP.length - 1),
    })),
    ladder: defaultLadder(),
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
  // "Intervals", because a Pomodoro is one preset of this and Tabata and HIIT
  // are two others. The `type` string stays `pomodoro` on purpose - it is what
  // MODE_LED_STATES, config.py and every saved config key off, and renaming it
  // would be a migration in exchange for a tidier word. See TODO item 20.
  label: 'Intervals',
  nature: 'takeover',
  allowedActivations: ['manual'], // started by an enter_mode gesture only
  body: 'fields',
  fields: [
    { key: 'work_s', label: 'Work block', kind: 'duration', min: 1,
      hint: 'How long one work interval lasts. 25 min for a Pomodoro, '
        + '20 sec for Tabata.' },
    { key: 'break_s', label: 'Rest', kind: 'duration', min: 1,
      hint: 'The short rest after each work interval.' },
    { key: 'long_break_s', label: 'Long rest', kind: 'duration', min: 1,
      hint: 'The longer rest you get after the number of blocks set below.' },
    { key: 'blocks_before_long_break', label: 'Blocks before a long rest', kind: 'number', min: 1, step: 1,
      hint: 'How many work blocks to finish before the long rest.' },
    { key: 'rounds', label: 'Rounds (0 = no end)', kind: 'number', min: 0, step: 1,
      hint: 'Stops itself after this many work blocks. 0 keeps alternating '
        + 'until you leave, which is what a Pomodoro does.' },
    { key: 'lead_in_s', label: 'Get-ready countdown', kind: 'duration', min: 0,
      hint: 'A pause before the first block, for anything you have to put the '
        + 'phone down for. 0 starts immediately.' },
    { key: 'advance', label: 'Between blocks', kind: 'select',
      hint: 'How much the button asks of you when a block ends.',
      options: [
        { value: 'auto', label: 'Start the next block automatically' },
        { value: 'manual', label: 'Wait for a press every time' },
        { value: 'break_only', label: 'Breaks start themselves, work waits for a press' },
      ] },
    // A function, not an array: LED_STYLES is declared further down this
    // module - see the countdown template's identical comment above its own
    // style field.
    { key: 'waiting_style', label: 'While paused or waiting for a press', kind: 'select',
      options: () => LED_STYLES.map((s) => ({ value: s.type, label: s.label })),
      hint: 'Shown instead of the usual animation whenever the timer is not '
        + 'actually running. Colour still comes from Work/Break above - '
        + '"Solid" is a good default because breathing or flashing already '
        + 'means "still counting".' },
    { key: 'extend_s', label: 'Added by "Add more time"', kind: 'duration', min: 1,
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
    work_s: 25 * 60, break_s: 5 * 60, long_break_s: 15 * 60,
    blocks_before_long_break: 4, extend_s: 10 * 60, advance: 'auto',
    rounds: 0, lead_in_s: 0,
    log_as: 'pomodoro', waiting_style: 'solid',
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
    const rounds = Number(mode.rounds) > 0 ? `, ${mode.rounds} rounds` : '';
    return `${fmtDuration(mode.work_s)}/${fmtDuration(mode.break_s)}${rounds}`
      + ` (${advance[mode.advance] || mode.advance})`;
  },
});

// ledStates is none, deliberately, and for the launcher's reason one step
// along: every frame this game shows is a colour it worked out for itself, so
// a named look would only ever be one wrong frame before the game paints over
// it. (The comment sits above `type` because the drift test in test_webui.py
// reads the two keys as adjacent lines.)
TEMPLATES.push({
  type: 'hotcold',
  ledStates: [],
  label: 'Hot / Cold',
  nature: 'takeover',
  allowedActivations: ['manual'], // a game that started itself would interrupt you
  body: 'fields',
  fields: [
    { key: 'ramp', label: 'Colour for how close you got', kind: 'ramp',
      hint: 'Left is as wrong as the wheel allows, right is dead on.' },
    { key: 'sweep_s', label: 'Seconds per turn of the wheel', kind: 'number',
      min: 0.5, max: 60, step: 0.5,
      hint: 'Slower is easier. Under about 2s the press delay starts to '
        + 'matter more than your aim does.' },
    { key: 'segments', label: 'Places on the wheel', kind: 'number',
      min: 0, max: 60, step: 1,
      hint: 'Snaps the target and your guess to the same grid, so landing '
        + 'anywhere in the right place counts. 0 = a smooth wheel, which is '
        + 'far harder than it sounds.' },
    { key: 'tolerance', label: 'How close counts as a hit', kind: 'number',
      min: 0.01, max: 1, step: 0.01,
      hint: '0.08 = within 8% of the wheel. Below about 0.03 the radio, not '
        + 'you, decides whether you win.' },
    { key: 'rounds', label: 'Rounds per game', kind: 'number', min: 0, step: 1,
      hint: '0 = keep dealing until you long-press out.' },
    { key: 'reveal_s', label: 'Seconds the answer stays up', kind: 'number',
      min: 0.1, max: 30, step: 0.1,
      hint: 'Presses during this are ignored - the wheel has already stopped.' },
    { key: 'log_as', label: 'Log each guess as', kind: 'text', required: true,
      placeholder: 'hotcold',
      hint: 'Logged with how close you got (0-100) as its value, so a run of '
        + 'games is something the events table can plot.' },
  ],
  defaults: () => ({
    sweep_s: 4, rounds: 5, segments: 12, tolerance: 0.08, reveal_s: 1.5,
    log_as: 'hotcold',
    ramp: HOTCOLD_RAMP.map((color, index) => ({
      color, at: index / (HOTCOLD_RAMP.length - 1),
    })),
  }),
  startedBy: 'gesture',
  exits: () => 'long press (short = stop the wheel)',
  describe: (mode) => {
    const rounds = Number(mode.rounds) > 0 ? `${mode.rounds} rounds` : 'endless';
    return `Hot/Cold - ${rounds}, ${mode.sweep_s ?? 4}s wheel`;
  },
});

// ledStates is none for the reason Hot/Cold's is - every frame is computed.
// (Comment above `type` so the drift test reads the two keys as adjacent.)
TEMPLATES.push({
  type: 'reaction',
  ledStates: [],
  label: 'Reaction timer',
  nature: 'takeover',
  allowedActivations: ['manual'],
  body: 'fields',
  fields: [
    { key: 'ramp', label: 'Colour for how sharp you were', kind: 'ramp',
      hint: 'Left is the slow end, right is instant.' },
    { key: 'min_delay_s', label: 'Shortest wait (seconds)', kind: 'number',
      min: 0.2, max: 60, step: 0.5,
      hint: 'The light goes out for somewhere between this and the longest '
        + 'wait, so the go signal cannot be anticipated.' },
    { key: 'max_delay_s', label: 'Longest wait (seconds)', kind: 'number',
      min: 0.2, max: 60, step: 0.5,
      hint: 'Set below the shortest wait and the two are swapped for you.' },
    { key: 'slowest_ms', label: 'Slow end of the colour (ms)', kind: 'number',
      min: 50, max: 5000, step: 50,
      hint: 'Only where the ramp bottoms out. A slower press is still logged '
        + 'honestly, it just cannot look any worse.' },
    { key: 'rounds', label: 'Attempts per game', kind: 'number', min: 0, step: 1,
      hint: '0 = keep going until you long-press out.' },
    { key: 'reveal_s', label: 'Seconds the time stays up', kind: 'number',
      min: 0.1, max: 30, step: 0.1,
      hint: 'Presses during this are ignored.' },
    { key: 'log_as', label: 'Log each attempt as', kind: 'text', required: true,
      placeholder: 'reaction',
      hint: 'Logged with the milliseconds as its value. A false start logs '
        + 'nothing - there is no time to record.' },
  ],
  defaults: () => ({
    min_delay_s: 2, max_delay_s: 6, rounds: 5, slowest_ms: 600, reveal_s: 1.2,
    log_as: 'reaction',
    ramp: REACTION_RAMP.map((color, index) => ({
      color, at: index / (REACTION_RAMP.length - 1),
    })),
  }),
  startedBy: 'gesture',
  exits: () => 'long press (short = press when it lights up)',
  describe: (mode) => {
    const rounds = Number(mode.rounds) > 0 ? `${mode.rounds} attempts` : 'endless';
    return `Reaction timer - ${rounds}`;
  },
});

// ledStates is none: a Signal wears whichever position it is on, and those
// are the app's own colours rather than the button's vocabulary.
// (Comment above `type` so the drift test reads the two keys as adjacent.)
TEMPLATES.push({
  type: 'signal',
  ledStates: [],
  label: 'Signal light',
  nature: 'takeover',
  allowedActivations: ['manual'],
  body: 'fields',
  fields: [
    // A JSON field rather than a bespoke repeating sub-form, and that is a
    // known rough edge rather than a preference - `webhook`'s payload made the
    // same call. What makes it acceptable is that the two presets below are
    // complete, so nobody has to write one of these to use the app; editing
    // the list is a tinker-tier job (TODO 14). A proper widget is the follow-up.
    { key: 'states', label: 'Positions', kind: 'json',
      hint: 'A list of {name, color} - add "action" to send something when you '
        + 'land on it. Short press moves to the next and stays there.' },
    { key: 'start_at', label: 'Opens on position', kind: 'number', min: 0, step: 1,
      hint: 'Counting from 0. Opening on a position does not send its message '
        + '- only pressing does.' },
    { key: 'log_as', label: 'Log each change as', kind: 'text',
      placeholder: 'status',
      hint: 'Optional. One row per change, with the position number as its value.' },
  ],
  defaults: () => ({
    states: [
      { name: 'Free', color: '#00ff00', style: 'solid' },
      { name: 'Busy', color: '#ff0000', style: 'solid' },
    ],
    start_at: 0, log_as: '',
  }),
  startedBy: 'gesture',
  exits: () => 'long press (short = next, double tap = send again)',
  describe: (mode) => {
    const states = Array.isArray(mode.states) ? mode.states : [];
    const names = states.map((s) => s && s.name).filter(Boolean);
    if (!names.length) return 'Signal light - no positions yet';
    return `Signal light - ${names.join(' / ')}`;
  },
});

export const TEMPLATE_BY_TYPE = Object.fromEntries(TEMPLATES.map((t) => [t.type, t]));

// Ready-made modes, offered next to "+ Add mode". Each is a complete mode
// object the parser accepts as-is - a starting point to edit, not a special
// kind of mode. Names are checked for collisions when one is added.
export const BUILTIN_MODES = [
  // Three presets over the one interval template, which is the whole point of
  // TODO 20: none of these costs a line of Python, and a fourth (60/10 study
  // blocks, 90-minute deep work, stand up every hour) costs nothing either.
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
    id: 'tabata',
    label: 'Tabata',
    blurb: '20s on, 10s off, 8 rounds. 10s to get ready first.',
    mode: () => ({
      name: 'Tabata', template: 'pomodoro', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.pomodoro.defaults(),
      work_s: 20, break_s: 10, long_break_s: 60,
      blocks_before_long_break: 8, rounds: 8, lead_in_s: 10,
      extend_s: 10, log_as: 'tabata',
      // Auto, and it has to be: nobody presses a button mid-burpee.
      advance: 'auto',
    }),
  },
  {
    id: 'hiit',
    label: 'HIIT intervals',
    blurb: '40s work, 20s rest, 8 rounds, 60s rest every 4th.',
    mode: () => ({
      name: 'HIIT', template: 'pomodoro', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.pomodoro.defaults(),
      work_s: 40, break_s: 20, long_break_s: 60,
      blocks_before_long_break: 4, rounds: 8, lead_in_s: 10,
      extend_s: 20, log_as: 'hiit', advance: 'auto',
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
  {
    id: 'hotcold',
    label: 'Hot / Cold',
    blurb: 'Stop the spinning colour wheel on a target only the button knows.',
    mode: () => ({
      name: 'Hot / Cold', template: 'hotcold', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.hotcold.defaults(),
    }),
  },
  {
    id: 'reaction',
    label: 'Reaction timer',
    blurb: 'Press the moment it lights up. Logs your milliseconds.',
    mode: () => ({
      name: 'Reaction', template: 'reaction', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.reaction.defaults(),
    }),
  },
  // The two faces of the Signal template. Both are complete as they stand,
  // which is what lets its positions live in a JSON field without that being
  // the first thing a new user meets.
  {
    id: 'status_light',
    label: 'Status light',
    blurb: 'Free / heads-down / on air. Press to change, and it stays.',
    mode: () => ({
      name: 'Status', template: 'signal', activation: { type: 'manual' },
      states: [
        { name: 'Free', color: '#00ff00', style: 'solid' },
        { name: 'Heads-down', color: '#ff8800', style: 'solid' },
        { name: 'On air', color: '#ff0000', style: 'solid' },
      ],
      start_at: 0, log_as: 'status',
    }),
  },
  {
    id: 'footswitch',
    label: 'Footswitch (OSC)',
    blurb: 'Stop / play / record, sent to your DAW over OSC. Edit the port.',
    mode: () => ({
      name: 'Footswitch', template: 'signal', activation: { type: 'manual' },
      states: [
        { name: 'Stop', color: '#ff0000', style: 'solid',
          action: { action: 'osc', host: '127.0.0.1', port: 8000,
                    address: '/stop', args: [1] } },
        { name: 'Play', color: '#00ff00', style: 'solid',
          action: { action: 'osc', host: '127.0.0.1', port: 8000,
                    address: '/play', args: [1] } },
        { name: 'Record', color: '#ff00ff', style: 'breathe',
          action: { action: 'osc', host: '127.0.0.1', port: 8000,
                    address: '/record', args: [1] } },
      ],
      start_at: 0, log_as: '',
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

/** A rainbow's brightness, 1-100, read off the colour's brightest channel.
 *  0 is what "never set" looks like in an old config, and the firmware renders
 *  that as full - so the editor shows it as full too rather than as off. */
export function levelPercent(hex) {
  const text = String(hex || '').replace('#', '');
  if (text.length !== 6) return 100;
  const top = Math.max(
    parseInt(text.slice(0, 2), 16),
    parseInt(text.slice(2, 4), 16),
    parseInt(text.slice(4, 6), 16),
  );
  if (!Number.isFinite(top) || top <= 0) return 100;
  return Math.round((top / 255) * 100);
}

/** The grey that stores `percent` as a level. */
export function levelHex(percent) {
  const byte = Math.max(1, Math.min(255, Math.round((percent / 100) * 255)));
  const pair = byte.toString(16).padStart(2, '0');
  return `#${pair}${pair}${pair}`;
}

export const LED_STYLES = [
  { type: 'solid', label: 'Solid', uses: ['color'],
    describe: () => 'held' },
  { type: 'breathe', label: 'Breathe', uses: ['color', 'period_s'],
    describe: (e) => `fading every ${e.period_s}s` },
  // `strobes` marks the hard on/off styles - the ones the flash floor applies
  // to. Mirrors device.py's STYLE_STROBES; test_schema_mirror.py fails on drift.
  // A property of the style rather than a list in the renderer, so a new style
  // declares whether it strobes instead of the floor having to learn its name.
  { type: 'flash', label: 'Flash', uses: ['color', 'period_s'], strobes: true,
    describe: (e) => `blinking every ${e.period_s}s` },
  { type: 'alternate', label: 'Alternate two colours', uses: ['color', 'color2', 'period_s'],
    strobes: true,
    describe: (e) => `swapping every ${e.period_s}s` },
  { type: 'fade', label: 'Fade between two colours', uses: ['color', 'color2', 'period_s'],
    describe: (e) => `crossfading every ${e.period_s}s` },
  // `level` rather than `color`: a rainbow generates its own hues and reads
  // the colour's brightest channel as brightness. Mirrors device.py's
  // STYLE_USES_LEVEL; test_schema_mirror.py fails on drift.
  { type: 'rainbow', label: 'Rainbow', uses: ['period_s', 'level'],
    describe: (e) => `cycling every ${e.period_s}s at ${levelPercent(e.color)}%` },
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

// Built-in looks, offered wherever a colour is chosen.
//
// **A starting point, never a stored thing.** Picking one copies its effect
// into whatever you are editing; nothing here lands in config.json unless you
// save it as a named look. That is why there can be forty of them without
// anybody's config growing, and why deleting a look you made never disturbs
// the library it came from.
//
// The groups are the useful axis. Nobody wants "all the blues"; they want the
// one that means *resting*, and the difference between Cooldown and Deep Water
// is what they are for rather than what hue they are.
//
// Two hardware facts shaped the choices, both from README's gotchas:
//   - This build's ring measures R > G > B, so pure blues read dim and white
//     reads warm. Anything that has to be *seen* leans red/amber; the blues
//     are here for calm states where dim is the point.
//   - Only `flash` and `alternate` strobe, and those are floored at 3 Hz
//     (WCAG 2.3.1). Every strobing preset below sits at 0.45 s or slower, so
//     the floor never has to rewrite one - test_look_presets.py fails if that
//     stops being true.
//
// The array is deliberately **strict JSON**: test_look_presets.py slices it
// out and feeds every effect through the real Python parser, so a preset
// cannot ship a colour the config would reject or a rate it would clamp.
// Keep comments outside the brackets.
export const LOOK_PRESETS = [
  { "id": "deep-water", "label": "Deep Water", "group": "Calm",
    "effect": { "style": "breathe", "color": "#0044ff", "color2": "#000000", "period_s": 4.5 } },
  { "id": "moss", "label": "Moss", "group": "Calm",
    "effect": { "style": "breathe", "color": "#1e8c46", "color2": "#000000", "period_s": 5 } },
  { "id": "ember", "label": "Ember", "group": "Calm",
    "effect": { "style": "breathe", "color": "#ff4400", "color2": "#000000", "period_s": 3.5 } },
  { "id": "candle", "label": "Candle", "group": "Calm",
    "effect": { "style": "breathe", "color": "#ff7a1a", "color2": "#000000", "period_s": 2.5 } },
  { "id": "slow-tide", "label": "Slow Tide", "group": "Calm",
    "effect": { "style": "fade", "color": "#002a55", "color2": "#00a0c0", "period_s": 6 } },
  { "id": "nightlight", "label": "Nightlight", "group": "Calm",
    "effect": { "style": "solid", "color": "#180600", "color2": "#000000", "period_s": 1 } },
  { "id": "dusk", "label": "Dusk", "group": "Calm",
    "effect": { "style": "fade", "color": "#2a0a40", "color2": "#ff5500", "period_s": 7 } },

  { "id": "deep-work", "label": "Deep Work", "group": "Focus",
    "effect": { "style": "solid", "color": "#00a866", "color2": "#000000", "period_s": 1 } },
  { "id": "flow", "label": "Flow", "group": "Focus",
    "effect": { "style": "breathe", "color": "#00d488", "color2": "#000000", "period_s": 6 } },
  { "id": "amber-desk", "label": "Amber Desk", "group": "Focus",
    "effect": { "style": "solid", "color": "#ffa000", "color2": "#000000", "period_s": 1 } },
  { "id": "tunnel", "label": "Tunnel", "group": "Focus",
    "effect": { "style": "fade", "color": "#001a0d", "color2": "#00ff77", "period_s": 4 } },
  { "id": "lantern", "label": "Lantern", "group": "Focus",
    "effect": { "style": "breathe", "color": "#ffc040", "color2": "#000000", "period_s": 4 } },

  { "id": "cooldown", "label": "Cooldown", "group": "Rest",
    "effect": { "style": "breathe", "color": "#00a8ff", "color2": "#000000", "period_s": 4 } },
  { "id": "meadow", "label": "Meadow", "group": "Rest",
    "effect": { "style": "fade", "color": "#6ac432", "color2": "#ffe95c", "period_s": 5 } },
  { "id": "warm-down", "label": "Warm Down", "group": "Rest",
    "effect": { "style": "fade", "color": "#ff8a00", "color2": "#3a1a00", "period_s": 5 } },
  { "id": "tea", "label": "Tea", "group": "Rest",
    "effect": { "style": "breathe", "color": "#b25a1e", "color2": "#000000", "period_s": 3 } },

  { "id": "klaxon", "label": "Klaxon", "group": "Alert",
    "effect": { "style": "flash", "color": "#ff0000", "color2": "#000000", "period_s": 0.5 } },
  { "id": "beacon", "label": "Beacon", "group": "Alert",
    "effect": { "style": "flash", "color": "#ff6a00", "color2": "#000000", "period_s": 0.9 } },
  { "id": "hazard", "label": "Hazard", "group": "Alert",
    "effect": { "style": "alternate", "color": "#ffc400", "color2": "#000000", "period_s": 0.6 } },
  { "id": "siren", "label": "Siren", "group": "Alert",
    "effect": { "style": "alternate", "color": "#ff0000", "color2": "#0033ff", "period_s": 0.45 } },
  { "id": "red-alert", "label": "Red Alert", "group": "Alert",
    "effect": { "style": "breathe", "color": "#ff0000", "color2": "#000000", "period_s": 1.2 } },
  { "id": "last-call", "label": "Last Call", "group": "Alert",
    "effect": { "style": "flash", "color": "#ff0044", "color2": "#000000", "period_s": 0.6 } },

  { "id": "green-light", "label": "Green Light", "group": "Done",
    "effect": { "style": "solid", "color": "#00ff2a", "color2": "#000000", "period_s": 1 } },
  { "id": "applause", "label": "Applause", "group": "Done",
    "effect": { "style": "rainbow", "color": "#ffffff", "color2": "#000000", "period_s": 0.7 } },
  { "id": "confetti", "label": "Confetti", "group": "Done",
    "effect": { "style": "rainbow", "color": "#ffffff", "color2": "#000000", "period_s": 1.4 } },
  { "id": "sunrise", "label": "Sunrise", "group": "Done",
    "effect": { "style": "fade", "color": "#ff1a00", "color2": "#ffd400", "period_s": 4.5 } },

  { "id": "on-air", "label": "On Air", "group": "Status",
    "effect": { "style": "solid", "color": "#ff0000", "color2": "#000000", "period_s": 1 } },
  { "id": "standby", "label": "Standby", "group": "Status",
    "effect": { "style": "solid", "color": "#ffa000", "color2": "#000000", "period_s": 1 } },
  { "id": "clear", "label": "Clear", "group": "Status",
    "effect": { "style": "solid", "color": "#00e04a", "color2": "#000000", "period_s": 1 } },
  { "id": "do-not-disturb", "label": "Do Not Disturb", "group": "Status",
    "effect": { "style": "breathe", "color": "#ff0033", "color2": "#000000", "period_s": 3 } },

  { "id": "downbeat", "label": "Downbeat", "group": "Time",
    "effect": { "style": "flash", "color": "#ffffff", "color2": "#000000", "period_s": 0.5 } },
  { "id": "tick", "label": "Tick", "group": "Time",
    "effect": { "style": "flash", "color": "#00e5ff", "color2": "#000000", "period_s": 0.5 } },
  { "id": "pulse", "label": "Pulse", "group": "Time",
    "effect": { "style": "breathe", "color": "#ff00aa", "color2": "#000000", "period_s": 1 } },

  { "id": "disco", "label": "Disco", "group": "Play",
    "effect": { "style": "rainbow", "color": "#ffffff", "color2": "#000000", "period_s": 0.5 } },
  { "id": "lava-lamp", "label": "Lava Lamp", "group": "Play",
    "effect": { "style": "fade", "color": "#ff0066", "color2": "#ffb400", "period_s": 7 } },
  { "id": "cyberpunk", "label": "Cyberpunk", "group": "Play",
    "effect": { "style": "alternate", "color": "#ff00ff", "color2": "#00ffff", "period_s": 0.7 } },
  { "id": "firefly", "label": "Firefly", "group": "Play",
    "effect": { "style": "breathe", "color": "#b6ff00", "color2": "#000000", "period_s": 2.2 } }
];

/** The preset groups, in the order they should be offered. */
export const LOOK_PRESET_GROUPS = [...new Set(LOOK_PRESETS.map((p) => p.group))];

export const LED_FIELDS = [
  { key: 'style', label: 'Style', kind: 'select',
    options: LED_STYLES.map((s) => ({ value: s.type, label: s.label })) },
  { key: 'color', label: 'Colour', kind: 'color' },
  // Same key as above, different reading of it. Which one renders is decided
  // by the style's `uses` list - a rainbow lists 'level', everything that
  // shows a hue lists 'color' - so this is a data choice, not a branch.
  { key: 'color', shows: 'level', label: 'Brightness', kind: 'level' },
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
