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
  // Binding this makes the button count to four, which costs the double tap
  // and triple tap their instant response (see max_taps_for) - the same cost
  // tap_5's hint explains below, paid one gesture earlier.
  { key: 'tap_4', label: 'Four taps',
    hint: 'Slows every shorter tap slightly - the button must wait to rule '
      + 'out a 4th.' },
  // Binding this makes the button count to five, which costs the double tap
  // its instant response (see max_taps_for). Worth saying in the UI, because
  // it is the one gesture whose cost is paid by the *other* gestures.
  { key: 'tap_5', label: 'Five taps',
    hint: 'Deliberately awkward - good for an on/off. Slows shorter taps '
      + 'too, same wait.' },
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
  'hotcold', 'reaction', 'signal', 'control',
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
// The Mackie Control transport and utility buttons, as note numbers.
//
// **Why a fixed table beats "type a number".** MCU is a de-facto standard that
// Studio One, Cubase, Live, Reaper, Logic and Pro Tools all implement, so a
// DAW told it has a Mackie Control already knows what note 94 means. Picking
// "Play" here and adding that device is the whole setup - no Control Link, no
// learning, nothing to look up. A DAW being taught by hand does not care what
// the numbers are, so these are a fine starting point either way.
//
// **This table is deliberately JS-only and creates no mirror.** The action
// stores a note number and nothing else; the name is editor sugar that
// `describe` reads back off the number. Putting a copy in config.py would be a
// second place to drift for no gain - Python never needs to know that 94 is
// called Play. Contrast MODE_LED_STATES, which is mirrored precisely because
// the parser enforces it.
//
// Velocity is 127 on every one: an MCU button is a switch, and 127 is what a
// pressed switch sends.
const _mcu = (number) => ({ kind: 'note_on', channel: 1, number, value: 127 });

// **A DAW has to be told it has a Mackie Control for any of this to work.**
// Point a "New Keyboard" at the port instead and every one of these arrives as
// a *note*, which the DAW will happily record into a track - the exact symptom
// that sent someone looking here. Nothing in this table can fix that; it is a
// device-type setting at the far end.
export const DAW_COMMANDS = [
  { id: 'play', label: 'Play (94)', group: 'Transport', set: _mcu(94),
    hint: 'Toggles in most DAWs - press again to stop. Best on a short press.' },
  { id: 'stop', label: 'Stop (93)', group: 'Transport', set: _mcu(93),
    hint: 'A real stop - not the same as pausing via Play again.' },
  { id: 'record', label: 'Record (95)', group: 'Transport', set: _mcu(95),
    hint: 'Tape-deck logic: Record arms, Play rolls. Nothing happening? Try '
      + 'Record then Play, and check a track is armed.' },
  { id: 'rewind', label: 'Rewind (91)', group: 'Transport', set: _mcu(91),
    hint: 'One press jumps back. Holding may or may not scrub - depends on '
      + 'the DAW.' },
  { id: 'forward', label: 'Fast-forward (92)', group: 'Transport', set: _mcu(92) },
  { id: 'loop', label: 'Loop / cycle (86)', group: 'Transport', set: _mcu(86),
    hint: 'Toggles loop over the selected range.' },
  { id: 'punch', label: 'Punch in/out (87)', group: 'Transport', set: _mcu(87) },
  { id: 'replace', label: 'Replace (88)', group: 'Transport', set: _mcu(88) },
  { id: 'click', label: 'Metronome / click (89)', group: 'Transport', set: _mcu(89),
    hint: 'Toggles the click - good one to hit blind.' },
  { id: 'marker', label: 'Drop a marker (84)', group: 'Transport', set: _mcu(84),
    hint: 'Worth a blind-reach button: mark a good take mid-playback.' },
  { id: 'nudge', label: 'Nudge (85)', group: 'Transport', set: _mcu(85) },
  { id: 'clear_solo', label: 'Clear all solos (90)', group: 'Transport', set: _mcu(90) },

  { id: 'cursor_up', label: 'Cursor up (96)', group: 'Navigation', set: _mcu(96) },
  { id: 'cursor_down', label: 'Cursor down (97)', group: 'Navigation', set: _mcu(97) },
  { id: 'cursor_left', label: 'Cursor left (98)', group: 'Navigation', set: _mcu(98) },
  { id: 'cursor_right', label: 'Cursor right (99)', group: 'Navigation', set: _mcu(99) },
  { id: 'zoom', label: 'Zoom (100)', group: 'Navigation', set: _mcu(100),
    hint: 'On real hardware, cursor keys zoom instead of move.' },
  { id: 'scrub', label: 'Scrub (101)', group: 'Navigation', set: _mcu(101) },

  { id: 'bank_left', label: 'Bank left - 8 tracks (46)', group: 'Tracks', set: _mcu(46) },
  { id: 'bank_right', label: 'Bank right - 8 tracks (47)', group: 'Tracks', set: _mcu(47) },
  { id: 'track_left', label: 'Previous track (48)', group: 'Tracks', set: _mcu(48) },
  { id: 'track_right', label: 'Next track (49)', group: 'Tracks', set: _mcu(49) },
  { id: 'flip', label: 'Flip faders/pots (50)', group: 'Tracks', set: _mcu(50) },
  { id: 'global_view', label: 'Global view (51)', group: 'Tracks', set: _mcu(51) },

  // Channel-strip buttons are one note per channel, eight of each in a block.
  // Only the first of each is listed: the pattern is worth knowing once rather
  // than reading thirty-two near-identical menu entries.
  { id: 'arm_1', label: 'Arm track 1 (0)', group: 'Channel strip', set: _mcu(0),
    hint: 'Add 1 per track across the bank: track 2 = 1, track 8 = 7. Same '
      + 'pattern for solo/mute/select below.' },
  { id: 'solo_1', label: 'Solo track 1 (8)', group: 'Channel strip', set: _mcu(8) },
  { id: 'mute_1', label: 'Mute track 1 (16)', group: 'Channel strip', set: _mcu(16) },
  { id: 'select_1', label: 'Select track 1 (24)', group: 'Channel strip', set: _mcu(24) },

  { id: 'save', label: 'Save (80)', group: 'Utility', set: _mcu(80) },
  { id: 'undo', label: 'Undo (81)', group: 'Utility', set: _mcu(81) },
  { id: 'cancel', label: 'Cancel (82)', group: 'Utility', set: _mcu(82) },
  { id: 'enter', label: 'Enter (83)', group: 'Utility', set: _mcu(83) },

  { id: 'auto_read', label: 'Read / off (74)', group: 'Automation', set: _mcu(74) },
  { id: 'auto_write', label: 'Write (75)', group: 'Automation', set: _mcu(75) },
  { id: 'auto_trim', label: 'Trim (76)', group: 'Automation', set: _mcu(76) },
  { id: 'auto_touch', label: 'Touch (77)', group: 'Automation', set: _mcu(77) },
  { id: 'auto_latch', label: 'Latch (78)', group: 'Automation', set: _mcu(78) },
  { id: 'auto_group', label: 'Group (79)', group: 'Automation', set: _mcu(79) },

  { id: 'assign_track', label: 'Pots: track (40)', group: 'Pot assignment', set: _mcu(40) },
  { id: 'assign_send', label: 'Pots: send (41)', group: 'Pot assignment', set: _mcu(41) },
  { id: 'assign_pan', label: 'Pots: pan (42)', group: 'Pot assignment', set: _mcu(42) },
  { id: 'assign_plugin', label: 'Pots: plug-in (43)', group: 'Pot assignment', set: _mcu(43) },
  { id: 'assign_eq', label: 'Pots: EQ (44)', group: 'Pot assignment', set: _mcu(44) },
  { id: 'assign_instrument', label: 'Pots: instrument (45)', group: 'Pot assignment', set: _mcu(45) },

  // F1-F8 are the useful ones for anything the rest of this table misses:
  // Studio One lets a Mackie function key be reassigned to a command, so these
  // are the escape hatch that does not need Control Link.
  { id: 'f1', label: 'F1 (54)', group: 'Function keys', set: _mcu(54),
    hint: 'Escape hatch: assignable to any DAW command - covers what is not '
      + 'listed here.' },
  { id: 'f2', label: 'F2 (55)', group: 'Function keys', set: _mcu(55) },
  { id: 'f3', label: 'F3 (56)', group: 'Function keys', set: _mcu(56) },
  { id: 'f4', label: 'F4 (57)', group: 'Function keys', set: _mcu(57) },
  { id: 'f5', label: 'F5 (58)', group: 'Function keys', set: _mcu(58) },
  { id: 'f6', label: 'F6 (59)', group: 'Function keys', set: _mcu(59) },
  { id: 'f7', label: 'F7 (60)', group: 'Function keys', set: _mcu(60) },
  { id: 'f8', label: 'F8 (61)', group: 'Function keys', set: _mcu(61) },

  // Modifiers are momentary on real hardware - held down while another button
  // is pressed. One button cannot hold one, so they are here for completeness
  // and are the least useful entries in the table.
  { id: 'shift', label: 'Shift (70)', group: 'Modifiers', set: _mcu(70),
    hint: 'Momentary on real hardware - held while pressing another button. '
      + "One button can't hold it, so rarely useful here." },
  { id: 'option', label: 'Option (71)', group: 'Modifiers', set: _mcu(71) },
  { id: 'control', label: 'Control (72)', group: 'Modifiers', set: _mcu(72) },
  { id: 'alt', label: 'Alt / Cmd (73)', group: 'Modifiers', set: _mcu(73) },
];

/** The DAW command a message matches, or null. Reverse lookup, so nothing
 *  has to be stored to show "Play" beside note 94. */
export function dawCommandFor(action) {
  if (!action || action.kind !== 'note_on' || action.channel !== 1) return null;
  return DAW_COMMANDS.find((c) => c.set.number === action.number) || null;
}

export const INTEGRATIONS = [
  {
    id: 'ifttt',
    label: 'IFTTT',
    blurb: 'Webhooks applet - one event name per applet.',
    set: {
      url: 'https://maker.ifttt.com/trigger/EVENT_NAME/with/key/YOUR_KEY',
      payload: { value1: '', value2: '', value3: '' },
    },
    hint: 'IFTTT: Create -> Webhooks -> "Receive a web request". Applets '
      + 'read only value1/2/3.',
  },
  {
    id: 'make',
    label: 'Make',
    blurb: 'Custom webhook trigger (was Integromat).',
    set: {
      url: 'https://hook.REGION.make.com/YOUR_WEBHOOK_ID',
      payload: {},
    },
    hint: 'Copy the full URL from the Custom Webhook module - region varies '
      + "per account, don't hand-type it.",
  },
  {
    id: 'zapier',
    label: 'Zapier',
    blurb: 'Catch Hook trigger.',
    set: {
      url: 'https://hooks.zapier.com/hooks/catch/YOUR_ID/YOUR_HOOK/',
      payload: {},
    },
    hint: 'Zapier reads any JSON that arrives - trigger/mode/ts are usable '
      + 'as Zap fields with no extra payload.',
  },
  {
    id: 'home_assistant',
    label: 'Home Assistant',
    blurb: 'Webhook trigger on a local automation.',
    set: {
      url: 'http://homeassistant.local:8123/api/webhook/YOUR_WEBHOOK_ID',
      payload: {},
    },
    hint: 'Local, no token needed - the webhook is unauthenticated by '
      + 'design, so treat the ID as the secret.',
  },
  {
    id: 'n8n',
    label: 'n8n',
    blurb: 'Webhook node, self-hosted or cloud.',
    set: {
      url: 'https://YOUR_HOST/webhook/YOUR_PATH',
      payload: {},
    },
    hint: 'Use the Production URL, not Test - Test only listens while the '
      + 'editor is open.',
  },
  {
    id: 'slack',
    label: 'Slack',
    blurb: 'Incoming webhook, posts a message.',
    set: {
      url: 'https://hooks.slack.com/services/YOUR_TEAM/YOUR_CHANNEL/YOUR_TOKEN',
      payload: { text: 'Button pressed' },
    },
    hint: 'Slack reads only "text" - other fields ride along, ignored.',
  },
  {
    id: 'discord',
    label: 'Discord',
    blurb: 'Channel webhook, posts a message.',
    set: {
      url: 'https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN',
      payload: { content: 'Button pressed' },
    },
    hint: 'Discord reads only "content". Server Settings -> Integrations -> '
      + 'Webhooks.',
  },
  {
    id: 'node_red',
    label: 'Node-RED',
    blurb: 'http in node on your own flow.',
    set: {
      url: 'http://YOUR_HOST:1880/YOUR_ENDPOINT',
      payload: {},
    },
    hint: 'Pair http in with an http response node, or the request hangs '
      + 'till it times out.',
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
        hint: 'Counted, streak-tracked, shows in Recent events.' },
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
        hint: 'First press starts, next stops - records elapsed time.' },
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
        hint: 'Fills in URL + payload below. Every template has YOUR_ '
          + 'placeholders - none works as-is.' },
      { key: 'url', label: 'URL', kind: 'text', required: true,
        placeholder: 'https://…',
        hint: 'POSTed on press - your IFTTT/Make/n8n/Home Assistant hook.' },
      // Optional and JSON-shaped: exactly the kind of fringe surface Tinker
      // exists for, and the webhook already works with none of it.
      { key: 'payload', label: 'Extra JSON payload', kind: 'json', tier: 'tinker',
        hint: 'Optional - merged into the POST body (trigger/mode/ts added '
          + 'for you).' },
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
        hint: 'Path your software listens on. Must start with / - a typo '
          + 'hits the wrong handler, not a failure.' },
      { key: 'host', label: 'Host', kind: 'text', required: true,
        placeholder: '127.0.0.1',
        hint: 'IP is best - a hostname works too, costs one lookup on first '
          + 'press.' },
      { key: 'port', label: 'Port', kind: 'number', min: 1, max: 65535, step: 1,
        hint: 'Whatever the receiver listens on - Reaper, TouchOSC, QLab, '
          + 'Resolume, VCV Rack.' },
      // The default ([1], "pressed") already works for most receivers -
      // fine-tuning the argument list is a fringe edit, not a first-use one.
      { key: 'args', label: 'Arguments', kind: 'json', tier: 'tinker',
        hint: 'JSON list. Types inferred: true/false -> T/F, whole numbers '
          + '-> int, decimals -> float, else text. [1] usually means '
          + '"pressed".' },
    ],
    defaults: () => ({
      action: 'osc', host: '127.0.0.1', port: 8000, address: '', args: [1],
    }),
    // No delivery to report: OSC is UDP, so the arrow means "sent at".
    describe: (a) => `OSC ${a.address || '…'} → ${a.host || '…'}:${a.port ?? '…'}`,
  },
  {
    type: 'midi',
    label: 'Send a MIDI message',
    fields: [
      { key: 'daw_command', label: 'Start from a DAW command', kind: 'preset',
        presets: () => DAW_COMMANDS,
        hint: 'Fills in the message below - Mackie Control numbers most '
          + 'DAWs already know. Add a "Mackie Control" device pointed at '
          + 'this port and it works unlearned. Teaching by hand instead? '
          + 'Any number here is as good a start as any.' },
      // The DAW-command preset above is the guided path; hand-tuning the raw
      // note/channel/port numbers is exactly the fringe surface Tinker is
      // for - a preset already fills all four correctly.
      { key: 'port', label: 'MIDI port', kind: 'text', tier: 'tinker',
        placeholder: 'Button',
        hint: 'Partial name is enough - Windows appends a number that '
          + 'changes per session, so "Button" matches "Button 2". Windows '
          + 'needs loopMIDI to create the port. Blank = first port found.' },
      { key: 'kind', label: 'Message', kind: 'select', tier: 'tinker',
        hint: 'Note on is what a DAW learns fastest. Driving an instrument, '
          + 'not a control? Send note off too, or the note hangs.',
        options: [
          { value: 'note_on', label: 'Note on' },
          { value: 'note_off', label: 'Note off' },
          { value: 'cc', label: 'Control change (CC)' },
        ] },
      { key: 'channel', label: 'Channel', kind: 'number', min: 1, max: 16, step: 1, tier: 'tinker',
        hint: '1-16, same numbering as your DAW.' },
      { key: 'number', label: 'Note / CC number', kind: 'number', min: 0, max: 127, step: 1, tier: 'tinker',
        hint: 'Which note/controller. Any value works if each gesture uses '
          + 'a different one.' },
      { key: 'value', label: 'Velocity / value', kind: 'number', min: 0, max: 127, step: 1, tier: 'tinker',
        hint: '127 = "full". Rarely matters for a button; for a CC it is '
          + 'the value sent.' },
    ],
    defaults: () => ({
      action: 'midi', port: '', kind: 'note_on', channel: 1, number: 60, value: 127,
    }),
    // Named where the numbers say so. Derived rather than stored, which is why
    // the picker can stay an inserter: "Play" is a fact about note 94, not a
    // fact about how this action got filled in.
    describe: (a) => {
      const command = dawCommandFor(a);
      if (command) return `MIDI ${command.label} (note ${a.number})`;
      if (a.kind === 'cc') return `MIDI CC ${a.number ?? '…'}=${a.value ?? '…'} ch${a.channel ?? '…'}`;
      const what = a.kind === 'note_off' ? 'note off' : 'note on';
      return `MIDI ${what} ${a.number ?? '…'} ch${a.channel ?? '…'}`;
    },
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
        hint: 'Which app this opens. Alarm/reminder are not listed - a '
          + 'clock starts those, not a gesture.',
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
  hint: 'Each tick shows its longest dividing interval: 10s white, 5s '
    + 'yellow, even sec light blue, odd dark. Off-beat gets the off-beat '
    + 'colour.',
};

const LADDER_BEATS_FIELD = {
  key: 'ladder', label: 'Colour the beats', kind: 'ladder',
  unit: ' beats', showTick: false,
  hint: 'Accents by beat: every 4th one colour, every 2nd another. Your '
    + 'tapped tempo supplies timing - no tick to set.',
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
        hint: "Shown while it's ringing." },
      { key: 'label', label: 'Short label', kind: 'text', tier: 'tinker',
        hint: 'Optional - name for status line / Bluetooth.' },
      { key: 'snooze_minutes', label: 'Snooze minutes', kind: 'number', min: 0, step: 1,
        hint: 'Long press snoozes this long. 0 = long press just dismisses.' },
      { key: 'dismiss_event', label: 'Log on dismiss', kind: 'text',
        hint: 'Optional - logged when dismissed.' },
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
        hint: "Shown while it's up." },
      { key: 'label', label: 'Short label', kind: 'text', tier: 'tinker',
        hint: 'Optional - name for the status line.' },
      { key: 'chime', label: 'Chime once', kind: 'checkbox',
        hint: 'One tone when it fires. Off = light only.' },
      { key: 'timeout_minutes', label: 'Give up after (minutes)', kind: 'number',
        min: 0, step: 1,
        hint: 'Stops flashing after this long. 0 = waits forever.' },
      { key: 'cleared_event', label: 'Log on clear', kind: 'text',
        hint: 'Optional - logged when cleared. A timeout logs nothing.' },
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
        hint: 'Logs elapsed time under this name. Short press laps, long press stops.' },
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
        hint: 'Logged per increment (short press / double tap). Long press exits.' },
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
      // Blank already offers everything, which is the right default - editing
      // this list is a narrowing/reordering job for later, not a first-use one.
      { key: 'targets', label: 'Apps to offer', kind: 'textarea', tier: 'tinker',
        placeholder: 'One mode name per line - blank = every app',
        hint: 'Blank = every takeover mode, new apps appear automatically. '
          + 'List names to shorten/reorder the menu.' },
      { key: 'return_after', label: 'Return here when an app exits',
        kind: 'checkbox', tier: 'tinker',
        hint: 'On: long press = up one level everywhere - out of an app '
          + 'lands here, out of here goes home. Off skips this menu.' },
      { key: 'log_as', label: 'Log each launch as', kind: 'text',
        placeholder: 'launched',
        hint: 'Optional - one event per launch, so you can see what you '
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
        hint: 'Tempo the light keeps before your first tap.' },
      { key: 'max_bpm', label: 'Fastest tempo (BPM)', kind: 'number', min: 1, step: 1, tier: 'tinker',
        hint: 'Ceiling for tap tempo - stops a bounced press reading as '
          + 'huge. Raise to go faster; above ~180 the light marks every Nth '
          + 'beat to stay safe.' },
      { key: 'tap_history', label: 'Taps to average over', kind: 'number', min: 2, step: 1, tier: 'tinker',
        hint: 'More = steadier, slower to follow. Fewer = twitchier.' },
      { key: 'reset_gap_s', label: 'Silence that restarts it (seconds)', kind: 'number',
        min: 0.1, step: 0.1, tier: 'tinker',
        hint: 'A pause this long restarts the average instead of averaging '
          + 'through the gap.' },
      { key: 'sound_on_tap', label: 'Click on each tap', kind: 'checkbox',
        hint: 'Turn off to practise by light alone.' },
      { key: 'log_as', label: 'Log each session as', kind: 'text', required: true,
        placeholder: 'metronome',
        hint: 'One event per session, carries the tempo you settled on.' },
      { key: 'clock_port', label: 'Follow a DAW (MIDI clock in)', kind: 'text', tier: 'tinker',
        placeholder: 'leave blank to tap the tempo',
        hint: 'Partial MIDI input port name. Enable Clock Out in your DAW, '
          + 'point it here - tempo follows the project. Tapping then marks '
          + 'a beat, no longer sets it. DAW goes quiet -> last tempo holds.' },
    ],
    defaults: () => ({
      start_bpm: 120, max_bpm: 300, tap_history: 8, reset_gap_s: 2,
      sound_on_tap: true, log_as: 'metronome', clock_port: '',
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
      hint: 'Left = full timer, right = zero. Drag a stop to hold its '
        + 'colour longer.' },
    // A function, not an array: LED_STYLES is declared further down this
    // module, so reading it while TEMPLATES is still being built would hit the
    // temporal dead zone. Deferring to render time also keeps the two lists
    // from drifting. Styles that ignore `color` are filtered out - a rainbow
    // countdown would throw the ramp away.
    { key: 'style', label: 'How the light moves', kind: 'select', tier: 'tinker',
      options: () => LED_STYLES
        .filter((s) => s.uses.includes('color'))
        .map((s) => ({ value: s.type, label: s.label })),
      hint: 'Colour comes from the ramp above - this is only the movement.' },
    { key: 'period_s', label: 'Seconds per flash', kind: 'number',
      min: 0.1, max: 600, step: 0.1, tier: 'tinker',
      hint: "Steady throughout - the ramp moves, the rate doesn't." },
    { key: 'minutes', label: 'Minutes', kind: 'number', min: 0.1, step: 1,
      hint: 'How long the countdown runs for.' },
    { key: 'label', label: 'Short label', kind: 'text', tier: 'tinker',
      hint: 'Optional - defaults to the mode name.' },
    { key: 'ring_on_finish', label: 'Ring at zero', kind: 'checkbox',
      hint: 'Off = finishes quietly, light only.' },
    // The ladder and the ramp both decide *which* colour, so only one runs -
    // the ladder wins when it is on. It sits after the ramp for that reason:
    // turning it on is what makes the fields above it stop mattering.
    LADDER_FIELD,
    { key: 'log_as', label: 'Log each finished run as', kind: 'text', required: true,
      placeholder: 'countdown',
      hint: 'Logs the length run. A cancelled run logs nothing.' },
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
      hint: "One work interval's length. 25 min for Pomodoro, 20 sec for "
        + 'Tabata.' },
    { key: 'break_s', label: 'Rest', kind: 'duration', min: 1,
      hint: 'Short rest after each work interval.' },
    { key: 'long_break_s', label: 'Long rest', kind: 'duration', min: 1,
      hint: 'Longer rest after the block count set below.' },
    { key: 'blocks_before_long_break', label: 'Blocks before a long rest', kind: 'number', min: 1, step: 1,
      hint: 'Work blocks before the long rest.' },
    // Session length is a stop condition, not the technique itself - 0 (the
    // default) already reproduces classic Pomodoro; picking a number is the
    // fringe edit the built-in Tabata/HIIT presets make for you.
    { key: 'rounds', label: 'Rounds (0 = no end)', kind: 'number', min: 0, step: 1, tier: 'tinker',
      hint: 'Stops after this many work blocks. 0 = alternates until you '
        + 'leave (classic Pomodoro).' },
    { key: 'lead_in_s', label: 'Get-ready countdown', kind: 'duration', min: 0, tier: 'tinker',
      hint: 'Pause before block 1, for setup time. 0 = starts immediately.' },
    { key: 'advance', label: 'Between blocks', kind: 'select',
      hint: 'What happens when a block ends.',
      options: [
        { value: 'auto', label: 'Start the next block automatically' },
        { value: 'manual', label: 'Wait for a press every time' },
        { value: 'break_only', label: 'Breaks start themselves, work waits for a press' },
      ] },
    // A function, not an array: LED_STYLES is declared further down this
    // module - see the countdown template's identical comment above its own
    // style field.
    { key: 'waiting_style', label: 'While paused or waiting for a press', kind: 'select', tier: 'tinker',
      options: () => LED_STYLES.map((s) => ({ value: s.type, label: s.label })),
      hint: "Shown when the timer isn't running. Colour still comes from "
        + 'Work/Break above - "Solid" is a good default, since '
        + 'breathe/flash already mean "still counting".' },
    { key: 'extend_s', label: 'Added by "Add more time"', kind: 'duration', min: 1, tier: 'tinker',
      hint: 'Time added by the "Add more time" gesture.' },
    { key: 'log_as', label: 'Log each finished block as', kind: 'text', required: true,
      placeholder: 'pomodoro',
      hint: 'Counted and streak-tracked like any other event.' },
    // The command bindings, tinker-tier by design: the defaults (pause,
    // leave, add time) already cover the mode, and hiding the remap surface
    // is what stops a first-time user from reassigning their own way out.
    { key: 'short_press', label: 'Short press does', kind: 'select', options: POMODORO_COMMANDS, tier: 'tinker',
      hint: 'What this does while running.' },
    { key: 'long_press', label: 'Long press does', kind: 'select', options: POMODORO_COMMANDS, tier: 'tinker',
      hint: 'Leave one gesture on "Leave the Pomodoro" - or you cannot get out.' },
    { key: 'double_tap', label: 'Double tap does', kind: 'select', options: POMODORO_COMMANDS, tier: 'tinker',
      hint: 'What this does while running.' },
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
      hint: 'Left = as wrong as it gets, right = dead on.' },
    { key: 'sweep_s', label: 'Seconds per turn of the wheel', kind: 'number',
      min: 0.5, max: 60, step: 0.5,
      hint: 'Slower = easier. Under ~2s, press delay matters more than aim.' },
    { key: 'segments', label: 'Places on the wheel', kind: 'number',
      min: 0, max: 60, step: 1,
      hint: 'Snaps target + guess to the same grid - land anywhere in the '
        + 'right slot. 0 = smooth wheel, harder than it sounds.' },
    { key: 'tolerance', label: 'How close counts as a hit', kind: 'number',
      min: 0.01, max: 1, step: 0.01,
      hint: '0.08 = within 8% of the wheel. Below ~0.03, the radio decides, '
        + 'not you.' },
    { key: 'rounds', label: 'Rounds per game', kind: 'number', min: 0, step: 1, tier: 'tinker',
      hint: '0 = keep dealing until you long-press out.' },
    { key: 'reveal_s', label: 'Seconds the answer stays up', kind: 'number',
      min: 0.1, max: 30, step: 0.1, tier: 'tinker',
      hint: "Presses ignored here - the wheel's already stopped." },
    { key: 'log_as', label: 'Log each guess as', kind: 'text', required: true,
      placeholder: 'hotcold',
      hint: 'Logs how close you got (0-100), so a run of games plots in '
        + 'the events table.' },
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
      hint: 'Left = slow end, right = instant.' },
    { key: 'min_delay_s', label: 'Shortest wait (seconds)', kind: 'number',
      min: 0.2, max: 60, step: 0.5,
      hint: 'Light goes out somewhere between this and the longest wait - '
        + 'keeps the go signal unpredictable.' },
    { key: 'max_delay_s', label: 'Longest wait (seconds)', kind: 'number',
      min: 0.2, max: 60, step: 0.5,
      hint: 'Set below the shortest wait and the two swap automatically.' },
    { key: 'slowest_ms', label: 'Slow end of the colour (ms)', kind: 'number',
      min: 50, max: 5000, step: 50, tier: 'tinker',
      hint: "Only the ramp's floor - a slower press still logs honestly, "
        + "just can't look worse." },
    { key: 'rounds', label: 'Attempts per game', kind: 'number', min: 0, step: 1, tier: 'tinker',
      hint: '0 = keep going until you long-press out.' },
    { key: 'reveal_s', label: 'Seconds the time stays up', kind: 'number',
      min: 0.1, max: 30, step: 0.1, tier: 'tinker',
      hint: 'Presses ignored here.' },
    { key: 'log_as', label: 'Log each attempt as', kind: 'text', required: true,
      placeholder: 'reaction',
      hint: 'Logs the milliseconds. A false start logs nothing - no time '
        + 'to record.' },
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
    { key: 'states', label: 'Positions', kind: 'json', tier: 'tinker',
      hint: 'List of {name, color} - add "action" to send something on '
        + 'landing. Short press moves to next, stays there.' },
    { key: 'start_at', label: 'Opens on position', kind: 'number', min: 0, step: 1, tier: 'tinker',
      hint: "From 0. Opening here doesn't send the message - only pressing "
        + 'does.' },
    { key: 'log_as', label: 'Log each change as', kind: 'text',
      placeholder: 'status',
      hint: 'Optional - one row per change, position number as its value.' },
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

// ledStates owns LISTENING - the state a control surface actually sits in
// between actions (SUCCESS/ERROR are transient flashes, not something a
// page can wear). A remote's page can be a menu too: bind enter_mode and
// you get a tree of pages, and knowing which one you are on is the whole
// job. Naming a look for LISTENING here wears it the whole time the page
// is open and swaps it on every sub-page transition, at zero wire cost -
// a page that names nothing still falls back to the palette's LISTENING
// colour, exactly as before this existed.
// (Comment above `type` so the drift test reads the two keys as adjacent.)
TEMPLATES.push({
  type: 'control',
  ledStates: ['LISTENING'],
  label: 'Control surface',
  nature: 'takeover',
  allowedActivations: ['manual'],
  body: 'actions',
  // Five, not six. Long press is how you leave every app, so a control
  // surface cannot have it - the parser drops a binding on it too, which is
  // what makes this a real constraint rather than a UI suggestion.
  gestures: ['short_press', 'double_tap', 'triple_tap', 'tap_4', 'tap_5'],
  // No daily stand-down: `unless_logged_today` answers "has this already
  // happened today", which is a question about an ambient mode that fires
  // whether or not you were thinking about it. An app you opened on purpose
  // has already answered it.
  unlessLogged: false,
  fields: [
    { key: 'log_as', label: 'Log each command as', kind: 'text',
      placeholder: 'daw',
      hint: 'Optional - one row per command sent. A failed send logs '
        + 'nothing, so counts stay honest.' },
    { key: 'return_after', label: 'Come back here after a branch',
      kind: 'checkbox', tier: 'tinker',
      hint: 'Bind a gesture to "Enter a mode" and this becomes a menu page. '
        + 'On: leaving what it opened returns here, so long press always '
        + 'travels one level. Off: drops straight to the everyday layer.' },
  ],
  defaults: () => ({
    short_press: { action: 'log', event: 'control_press' },
    log_as: '', return_after: true,
  }),
  startedBy: 'gesture',
  exits: () => 'long press',
  describe: (mode) => {
    const parts = [];
    for (const g of GESTURES) {
      if (g.key === 'long_press') continue;
      const action = mode[g.key];
      if (action && action.action) parts.push(`${g.label} → ${describeAction(action)}`);
    }
    return parts.length
      ? `Control surface - ${parts.join(' · ')}`
      : 'Control surface - nothing bound yet';
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
  {
    id: 'daw_transport',
    label: 'DAW transport (MIDI)',
    blurb: 'An app you open from the launcher: play, record, stop and marker on '
      + 'four gestures. Set the MIDI port, add a Mackie Control device in your '
      + 'DAW, and nothing needs learning.',
    mode: () => ({
      // A control surface rather than a signal light, because transport wants
      // one gesture per command: a cycle would pass through Play to reach
      // Record. Record is on the double tap for the same reason - it is the one
      // command whose accidental firing costs you a take.
      //
      // Marker is on five taps rather than long press: the long press is how
      // you leave, everywhere, and this is exactly the app where you are least
      // likely to be looking at the button.
      name: 'DAW', template: 'control', activation: { type: 'manual' },
      short_press: { action: 'midi', port: '', kind: 'note_on',
                     channel: 1, number: 94, value: 127 },   // Play
      double_tap: { action: 'midi', port: '', kind: 'note_on',
                    channel: 1, number: 95, value: 127 },    // Record
      triple_tap: { action: 'midi', port: '', kind: 'note_on',
                    channel: 1, number: 93, value: 127 },    // Stop
      tap_5: { action: 'midi', port: '', kind: 'note_on',
               channel: 1, number: 84, value: 127 },         // Marker
      log_as: '',
    }),
  },
  {
    id: 'footswitch_midi',
    label: 'Footswitch (MIDI)',
    blurb: 'Cycles loop → metronome → marker in a DAW over MIDI. Set the port, '
      + 'add a Mackie Control device in the DAW, and it works unlearned.',
    mode: () => ({
      // Toggles and one-shots, deliberately - *not* transport. A signal light
      // advances on each press, so a Stop/Play/Record cycle would pass through
      // Play on its way to Record and start playback you did not ask for.
      // Transport wants one gesture per command, which is an actions mode.
      name: 'Footswitch', template: 'signal', activation: { type: 'manual' },
      states: [
        { name: 'Loop', color: '#00b0ff', style: 'solid',
          action: { action: 'midi', port: '', kind: 'note_on',
                    channel: 1, number: 86, value: 127 } },
        { name: 'Metronome', color: '#ffb000', style: 'solid',
          action: { action: 'midi', port: '', kind: 'note_on',
                    channel: 1, number: 89, value: 127 } },
        { name: 'Marker', color: '#ff00ff', style: 'flash',
          action: { action: 'midi', port: '', kind: 'note_on',
                    channel: 1, number: 84, value: 127 } },
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
    blurb: 'What a press does normally. Read top to bottom: the first mode '
      + "that's on now and sets this press, wins. Order is priority - move "
      + 'a mode up to win. Unset gesture -> passes to the next mode.',
    emptyText: 'None yet.',
  },
  {
    nature: 'takeover',
    title: 'Takeover',
    blurb: 'While running, one of these owns every press - everyday modes '
      + 'are ignored until you leave. An alarm starts itself at its set '
      + 'time; others start via an everyday mode with an “Enter a mode” '
      + 'gesture.',
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
// LISTENING is the one dual citizen: the ambient layer wears it while an
// action runs - no mode involved - so its global default stays on the Lights
// tab even though a control page may also name a look for it (TODO 26).
export const SYSTEM_LED_STATES = LED_STATES.filter(
  (s) => s.key === 'LISTENING' || !MODE_LED_STATE_KEYS.has(s.key),
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
  // A stop list (TODO 19b) is a look but not a style, so it summarises
  // before the style table gets a say.
  if (effect && Array.isArray(effect.stops)) {
    const n = effect.stops.length;
    return `Sequence, ${n} stop${n === 1 ? '' : 's'}, `
      + (effect.repeat === false ? 'plays once' : 'looping');
  }
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
    // Tinker-tier throughout except `sounds_enabled` (TODO 14): a rename, a
    // database path or the flash floor are all one-per-button decisions a
    // first-time setup never needs, not a thing to stumble into. The floor
    // stays enforced (config.flash_safe) whether or not this field is on
    // screen - hiding it by default only hides who can *lower* it.
    fields: [
      { key: 'ble_device_name', label: 'Bluetooth name', kind: 'text', tier: 'tinker',
        hint: 'Name the button advertises - host connects by name.' },
      { key: 'sounds_enabled', label: 'Feedback sounds', kind: 'checkbox' },
      { key: 'database_path', label: 'Event database path', kind: 'text', tier: 'tinker' },
      // The one setting whose default exists for a medical reason rather than
      // a taste one. It is editable because this is one button on one desk and
      // its owner may decide it can go faster; the hint has to say what that
      // costs, because nothing else in the UI will.
      { key: 'min_flash_period_s', label: 'Fastest the light may flash', tier: 'tinker',
        kind: 'range', min: 0.05, max: 2, step: 0.01,
        describe: (v) => `${v.toFixed(2)}s (${(1 / v).toFixed(1)} flashes/sec)`,
        hint: 'Floor for flash + alternate. 0.33s = 3/sec, the photosensitivity '
          + 'limit. Faster is allowed - and a seizure risk.' },
    ],
  },
  {
    title: 'Web server',
    // Also tinker-tier throughout: this is how you reach the page at all, so
    // an unsupervised toggle or a mistyped port is a lockout, not a tweak.
    fields: [
      { key: 'web_enabled', label: 'Web UI enabled', kind: 'checkbox', tier: 'tinker',
        hint: 'Takes effect on restart.' },
      { key: 'web_host', label: 'Bind host', kind: 'text', tier: 'tinker' },
      { key: 'web_port', label: 'Port', kind: 'number', min: 1, max: 65535, step: 1, tier: 'tinker' },
    ],
  },
];
