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

// Which actions a lifecycle hook may run - the fire-and-forget primitives.
// Mirrors HOOK_ACTIONS in config.py, which explains why the other three are
// missing: enter_mode, readout and standby each change what the mode *loop*
// does next, and a hook fires beside the loop rather than inside it.
// test_schema_mirror.py fails on drift.
export const HOOK_ACTIONS = ['log', 'timer_toggle', 'webhook', 'osc', 'midi', 'keys'];

// The two lifecycle hooks (config.py's MODE_HOOKS). Shaped exactly like a
// GESTURES entry, and rendered by the same sub-editor, because a hook *is* a
// binding - only what triggers it differs. They live on the mode rather than
// on a template, so one pair serves every takeover and adding an app adds no
// hook of its own.
//
// Tinker-tier: a mode works with neither, and what they are for - telling
// something else on the network that a session started or ended - is a fringe
// edit rather than a first-use one.
export const MODE_HOOKS = [
  { key: 'on_enter', label: 'When it starts', tier: 'tinker', actions: HOOK_ACTIONS,
    hint: 'Fired once as the app takes the button over, before it draws '
      + 'anything - a webhook saying "focus started", a MIDI note arming a '
      + 'DAW. It cannot stop the app starting: a failure is logged and the '
      + 'app runs anyway.' },
  { key: 'on_exit', label: 'When it ends', tier: 'tinker', actions: HOOK_ACTIONS,
    hint: 'Fired once as the app hands the button back, after its own session '
      + 'has been recorded - the other half of a status webhook. A failure is '
      + 'logged and you still leave. Apps that count something send it along: '
      + 'a webhook gets the numbers in its JSON, an OSC message gets them as '
      + 'extra arguments after your own.' },
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
  'hotcold', 'reaction', 'signal', 'control', 'lightshow',
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
    type: 'readout',
    label: 'Show a count on the light',
    fields: [
      // Same reading as `log`'s event field - a readout is a sibling of log,
      // not a mode of it: this one only reads count_today(event), it never
      // writes a row, so it can sit on a gesture that a `log` binding
      // elsewhere already feeds without double-counting anything.
      { key: 'event', label: 'Event name', kind: 'text', required: true,
        placeholder: 'coffee',
        hint: 'Blinks today’s count for this event: tens as slow '
          + 'pulses, units as quick ones - 27 is two slow, then seven '
          + 'quick. 0 is one dim blink, so a real zero reads differently '
          + 'from nothing happening.' },
      { key: 'tens_color', label: 'Tens colour', kind: 'color', tier: 'tinker',
        hint: 'The slow pulses - the coarse digit.' },
      { key: 'units_color', label: 'Units colour', kind: 'color', tier: 'tinker',
        hint: 'The quick pulses - the fine digit.' },
    ],
    defaults: () => ({
      action: 'readout', event: '', tens_color: '#ff8800', units_color: '#3399ff',
    }),
    describe: (a) => `Show “${a.event || '…'}” as a readout`,
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
        // Recognise the command again from the message it wrote, so the
        // dropdown still says "Play" after a save has dropped the transient
        // key. Same reverse lookup `describe()` uses - see widgets.js.
        derive: dawCommandFor,
        hint: 'Fills in the message below - Mackie Control numbers most '
          + 'DAWs already know. Add a "Mackie Control" device pointed at '
          + 'this port and it works unlearned. Teaching by hand instead? '
          + 'Any number here is as good a start as any.' },
      // The DAW-command preset above is the guided path; hand-tuning the raw
      // note/channel/port numbers is exactly the fringe surface Tinker is
      // for - a preset already fills all four correctly.
      { key: 'port', label: 'MIDI port', kind: 'text', tier: 'tinker', suggest: 'midi_out',
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
    type: 'keys',
    label: 'Press keys / click',
    fields: [
      { key: 'combo', label: 'Key combination', kind: 'text',
        placeholder: 'ctrl+shift+p',
        hint: 'Modifiers then one key, joined by "+" - ctrl, shift, alt, win. '
          + 'Media keys (playpause, nexttrack, volumeup, mute) are the ones '
          + 'that work with no window focused; everything else goes to '
          + 'whatever is in front. Leave blank to only click.' },
      { key: 'click', label: 'Mouse click', kind: 'select', tier: 'tinker',
        hint: 'Clicks wherever the pointer already is - the button cannot '
          + 'move it. Blank for none.',
        options: [
          { value: '', label: 'None' },
          { value: 'left', label: 'Left click' },
          { value: 'right', label: 'Right click' },
          { value: 'middle', label: 'Middle click' },
          { value: 'double', label: 'Double click' },
        ] },
    ],
    defaults: () => ({ action: 'keys', combo: '', click: '' }),
    // Says where it lands, because that is the thing people get wrong: this
    // types on the machine running the service, not the machine you are
    // looking at, and those stop being the same one on a portable host.
    describe: (a) => {
      const bits = [];
      if (a.combo) bits.push(a.combo);
      if (a.click) bits.push(a.click === 'double' ? 'double click' : `${a.click} click`);
      return bits.length ? `Press ${bits.join(' then ')}` : 'Press nothing yet';
    },
  },
  {
    type: 'enter_mode',
    label: 'Launch an app',
    fields: [
      // Dynamic <select>: the options are the takeover modes a gesture can
      // actually start - every template whose descriptor says
      // `startedBy: 'gesture'`, which excludes the schedule-started ones
      // (alarm, reminders) that a clock owns instead. The widget
      // calls this with a context object whose `getModes()` returns the
      // sibling modes (injected by menu.js -> modeEditor -> createField), so
      // the picker stays in sync as modes are added/renamed without this
      // module knowing where the list lives (Dependency Inversion).
      { key: 'target', label: 'App to launch', kind: 'modeSelect', required: true,
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
    describe: (a) => `Launch “${a.target || '…'}”`,
  },
  {
    type: 'standby',
    label: 'Sleep / wake the button',
    // No fields, and that is the whole design: which way it goes is session
    // state the running service holds, not a setting, so there is nothing
    // here to configure. Bind it to the five-tap and you have an off switch.
    fields: [],
    defaults: () => ({ action: 'standby' }),
    describe: () => 'Sleep or wake the reflexes',
  },
];

export const ACTION_BY_TYPE = Object.fromEntries(ACTIONS.map((a) => [a.type, a]));

/** One-line human summary of an action, used by the mode editor.
 *
 *  A binding may be a bare string naming one in the pool (config.py's
 *  `NamedAction`) rather than an action object - summarised as the name,
 *  because chasing the pool to render what it currently does would make the
 *  summary of two gestures naming the same action differ from each other for
 *  no reason a reader could see. */
export function describeAction(action) {
  if (typeof action === 'string') return `Named action “${action}”`;
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
 * A configured *length* in seconds, written the way a person would say it -
 * "25m", "90s". Mirrors the `duration` widget's unit inference so a summary
 * and the field you edit it in never disagree about whether something is
 * "25 min" or "1500 sec".
 *
 * **Not the same job as format.js's `fmtDuration`**, which writes elapsed time
 * on a clock face ("8:41") for the event log and an app's readout. Both are
 * "a duration"; one is a setting you typed and the other is a measurement, and
 * they round and abbreviate differently on purpose. They shared a name until
 * the editor bundle refused to hold two - which is the bundler earning its
 * keep, since in the served page they would simply have been two modules
 * quietly disagreeing.
 */
export function fmtLength(seconds) {
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
//   startedBy  'gesture' (a reflex's Launch an app) | 'schedule'
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

/**
 * How an app reads its own history back, on its own page (TODO 51).
 *
 * **Declared, not branched on.** A template says which rows in the event log
 * are its own and what the number on them means; appReadout.js renders anything
 * that answers. So an app gets a history by adding four keys rather than by
 * growing a case in the view - the same rule `fields` and `ledStates` follow.
 *
 * `nameField` is the *config key* holding the event name, never the name
 * itself: two counters log under different names and share this descriptor.
 * An empty one means this copy is configured to log nothing, which the readout
 * says out loud rather than rendering as an empty history.
 *
 * `measure` says what the rows mean, and there are only four of them because
 * pooling unlike numbers onto one axis is how you get a chart that is
 * confidently meaningless - the same trap TODO 53 names about `value`:
 *
 *   duration  `duration_s` on the row. A stopwatch's runs.
 *   value     the `value` column, where it is a magnitude worth comparing -
 *             BPM, milliseconds, minutes, a percentage.
 *   tally     the rows are occurrences and the number is *how many per day*.
 *             A counter's presses, an intervals app's finished blocks.
 *   outcome   the value is one of two states rather than a magnitude. An
 *             alarm's answered/unanswered, and the reason those 0s and 1s
 *             must never be averaged into "0.86 alarms".
 *
 * **A Signal light is the case that proves the split.** It writes a `value`
 * too, and that value is an *index into its position list* - neither a
 * magnitude nor a duration. It is `tally` here, because how often the light
 * changed is a real question and "average position 1.4" is not one.
 *
 * `better` is which end of the range is the good end, and it is null far more
 * often than not: a tempo has no good end and neither does a countdown's
 * length. Set it only where "best" is a fact about the app rather than a guess
 * about the person using it.
 */
export const READOUT_MEASURES = ['duration', 'value', 'tally', 'outcome'];

export const TEMPLATES = [
  {
    type: 'actions',
    ledStates: [],
    label: 'Actions',
    about: 'One action per gesture, answered without taking the button over.',
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
        // A string binding is a pool reference and has no `.action` - see
        // describeAction. Testing the binding itself rather than its shape is
        // what keeps a named gesture from summarising as "nothing bound".
        if (action) parts.push(`${g.label} → ${describeAction(action)}`);
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
    about: 'Rings at a set time until you deal with it.',
    nature: 'takeover',
    allowedActivations: ['schedule'],
    body: 'fields',
    fields: [
      { key: 'message', label: 'Message', kind: 'text',
        hint: "Shown while it's ringing." },
      { key: 'label', label: 'Short label', kind: 'text', tier: 'tinker',
        hint: 'Optional - name for status line / Bluetooth.' },
      // The dead man's switch (TODO 44). Basic tier, not tinker: someone who
      // wants this is looking for it, and burying the thing a preset is named
      // after would be a joke at their expense.
      { key: 'grace_minutes', label: 'Give up after', kind: 'number', min: 0, step: 1,
        hint: 'Minutes to wait for an answer before giving up. 0 = ring until '
          + 'answered, which is an ordinary alarm.' },
      { key: 'snooze_minutes', label: 'Snooze minutes', kind: 'number', min: 0, step: 1,
        hint: 'Long press snoozes this long. 0 = long press just dismisses.' },
      { key: 'dismiss_event', label: 'Log on dismiss', kind: 'text',
        hint: 'Optional - logged when dismissed.' },
    ],
    bindings: [
      { key: 'on_timeout', label: 'If nobody answers', actions: HOOK_ACTIONS,
        hint: 'Runs only when the alarm went unanswered for that long. It '
          + 'needs this PC awake and connected - if the service stops or '
          + 'Bluetooth drops it cannot fire, so treat it as a nudge rather '
          + 'than a safety device.' },
    ],
    // `outcome`, not `value`, and that is the whole reason the measure exists:
    // since 44 a dismissal logs 1 and a timeout logs 0 under the same name, so
    // the honest readout is "answered 6 of the last 7" and the dishonest one
    // is an average. Optional - an alarm with no dismiss_event logs nothing,
    // and the readout says so rather than showing an empty list.
    readout: {
      kind: 'log', nameField: 'dismiss_event', measure: 'outcome',
      noun: 'ring', better: null,
      states: { 1: 'answered', 0: 'no answer' },
    },
    defaults: () => ({
      message: '', label: '', snooze_minutes: 0, dismiss_event: '', grace_minutes: 0,
    }),
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
    about: 'A gentler alarm - shows at a set time, chimes once, gives up on its own.',
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
    // A tally of the times it was actually cleared. A timeout logs nothing
    // here (unlike an alarm since 44), so this counts answers and cannot count
    // misses - which is why it is a tally rather than an outcome.
    readout: {
      kind: 'log', nameField: 'cleared_event', measure: 'tally',
      noun: 'clear', better: null,
    },
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
    about: 'Times something, with laps.',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      LADDER_FIELD,
      { key: 'log_as', label: 'Timer name', kind: 'text', required: true,
        placeholder: 'focus',
        hint: 'Logs elapsed time under this name. Short press laps, long press stops.' },
    ],
    // The app item 51 was actually asked for: a stopwatch's page should be the
    // stopwatch, and its runs are already in the log as timer_stop rows with a
    // duration on them. `timer_stop` rather than `log` matters here - laps are
    // logged as `<log_as>_lap`, and the kind filter is what keeps them out of
    // the run list without a second name to match on.
    readout: {
      kind: 'timer_stop', nameField: 'log_as', measure: 'duration',
      noun: 'run', better: null,
    },
    // Named, like the countdown's and the metronome's: this field is
    // `required` and StopwatchBehavior now defaults to the same word, so a
    // stopwatch added here and one a scene file leaves out agree on what the
    // timer is called instead of one of them being unsaveable.
    defaults: () => ({ log_as: 'stopwatch', ladder: defaultLadder() }),
    startedBy: 'gesture',
    exits: () => 'long press (short/double = lap)',
    describe: (mode) => `Stopwatch “${mode.log_as || '…'}”`,
  },
  {
    type: 'counter',
    ledStates: ['COUNTING'],
    label: 'Counter',
    about: 'A tally you press up.',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      { key: 'event', label: 'Event name', kind: 'text', required: true,
        placeholder: 'water',
        hint: 'Logged per increment (short press / double tap). Long press exits.' },
    ],
    // A tally, not a value: each press is one row and the number worth seeing
    // is how many of them a day held - which is exactly what `count_today`
    // already answers on the button, arrived at the same way.
    readout: {
      kind: 'log', nameField: 'event', measure: 'tally',
      noun: 'press', better: null,
    },
    // Named for the same reason the stopwatch's is: `event` is `required` and
    // run_counter uses it unguarded, so an empty default writes rows called ""
    // and sums every unnamed counter into one bucket.
    defaults: () => ({ event: 'counter' }),
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
    about: 'Steps through your apps, so you need one gesture rather than one each.',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      // Blank already offers everything, which is the right default - editing
      // this list is a narrowing/reordering job for later, not a first-use one.
      { key: 'targets', label: 'Apps to offer', kind: 'textarea', tier: 'tinker',
        placeholder: 'One mode name per line - blank = every app',
        hint: 'Blank = every app you have, and new ones appear automatically. '
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
    // What the `log_as` field above already promises - "so you can see what
    // you actually use" - finally shown somewhere. Optional, like that field.
    readout: {
      kind: 'log', nameField: 'log_as', measure: 'tally',
      noun: 'launch', better: null,
    },
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
    // Which stop-list drives this app can supply a number for. Mirrors
    // `config.DRIVE_TEMPLATES`; the clock drive is bindable everywhere and so
    // is never listed. See DRIVES.
    drives: ['beats'],
    label: 'Metronome',
    about: 'Tap a tempo and the light keeps it, or follow a MIDI clock.',
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
      { key: 'clock_port', label: 'Follow a DAW (MIDI clock in)', kind: 'text', tier: 'tinker', suggest: 'midi_in',
        placeholder: 'leave blank to tap the tempo',
        hint: 'Partial MIDI input port name. Enable Clock Out in your DAW, '
          + 'point it here - tempo follows the project. Tapping then marks '
          + 'a beat, no longer sets it. DAW goes quiet -> last tempo holds.' },
    ],
    // BPM, and `better: null` is the point of that key being nullable: a
    // tempo has no good end, so a readout that crowned a "best" one would be
    // inventing an opinion the app does not have.
    readout: {
      kind: 'log', nameField: 'log_as', measure: 'value',
      noun: 'session', unit: 'BPM', better: null,
    },
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
  // One of the two apps that know how far through they are - a stopwatch
  // shares TIMING but has no end to be a fraction of, which is why this list
  // is keyed by template and not by state. See DRIVES.
  drives: ['progress'],
  label: 'Countdown',
  about: 'Counts minutes down, the colour walking as it goes, then rings.',
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
  // The length that was run, in minutes - and only *finished* runs are here,
  // because a cancelled one logs nothing (the field above says so). So this
  // reads as "runs you saw through", which is the more useful of the two.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'value',
    noun: 'run', unit: 'min', better: null,
  },
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
  // Its progress is through the **current block**, not the session - a classic
  // Pomodoro has no end to be a fraction of. It resets every phase change, and
  // since a look is named per state, WORKING and RESTING can be driven apart.
  // Mirrors `config.DRIVE_TEMPLATES`; test_schema_mirror.py fails on drift.
  drives: ['progress'],
  // "Intervals", because a Pomodoro is one preset of this and Tabata and HIIT
  // are two others. The `type` string stays `pomodoro` on purpose - it is what
  // MODE_LED_STATES, config.py and every saved config key off, and renaming it
  // would be a migration in exchange for a tidier word. See TODO item 20.
  label: 'Intervals',
  about: 'Work and rest blocks - Pomodoro, Tabata or HIIT from the one template.',
  nature: 'takeover',
  allowedActivations: ['manual'], // started by an enter_mode gesture only
  body: 'fields',
  fields: [
    // Empty by default, unlike the countdown's, and the field says so: this
    // template already uses colour to tell work from rest, and a ramp
    // overrides both. Tinker-tier for the same reason - it is a trade, not a
    // starting point.
    { key: 'ramp', label: 'Colour as each block runs', kind: 'ramp', tier: 'tinker',
      hint: 'Left = the block just started, right = it is about to end. Empty '
        + 'leaves work and rest on their own colours, which is how you tell '
        + 'them apart - so this trades that for a progress read.' },
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
  // One row per *completed work block*, so the number worth seeing is how many
  // a day held - the question anyone running Pomodoros is actually asking.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'tally',
    noun: 'block', better: null,
  },
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
    return `${fmtLength(mode.work_s)}/${fmtLength(mode.break_s)}${rounds}`
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
  about: 'A guessing game: stop the spinning wheel on the hidden target.',
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
  // Closeness, 0-100, and one of the two places `better` is a fact rather than
  // a preference: a game has a score and nearer the target is better.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'value',
    noun: 'guess', unit: '%', better: 'high',
  },
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
  about: 'The light goes out at a random moment - press as fast as you can.',
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
  // Milliseconds, and the other place `better` is a fact: faster is the whole
  // game. It is also why `better` exists at all rather than "lower is best"
  // being assumed - a countdown's minutes sit in the same column and mean the
  // opposite of nothing.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'value',
    noun: 'attempt', unit: 'ms', better: 'low',
  },
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
  about: 'Wears one of your positions - Free, Busy, On air - and can send on each change.',
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
  // A tally, though this app does write a `value` - see the note on
  // READOUT_MEASURES. That value is an index into the position list, so "how
  // often did the light change today" is a real question and any average over
  // it is not.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'tally',
    noun: 'change', better: null,
  },
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
  about: 'A remote: one command per gesture, held open so you can send several.',
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
      hint: 'Bind a gesture to "Launch an app" and this becomes a menu page. '
        + 'On: leaving what it opened returns here, so long press always '
        + 'travels one level. Off: drops straight back to your reflexes.' },
  ],
  // Optional, like the field: a control surface logs only if you ask it to.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'tally',
    noun: 'press', better: null,
  },
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
      if (action) parts.push(`${g.label} → ${describeAction(action)}`);
    }
    return parts.length
      ? `Control surface - ${parts.join(' · ')}`
      : 'Control surface - nothing bound yet';
  },
});

// A light show: a playlist of looks, walked on a clock. It owns no LED state -
// each cue is pushed as an ephemeral effect, exactly as a Signal position is,
// so the whole app costs no wire code (TODO 52a).
TEMPLATES.push({
  type: 'lightshow',
  ledStates: [],
  label: 'Light show',
  about: 'Plays a playlist of your looks, one after another.',
  nature: 'takeover',
  allowedActivations: ['manual'],
  body: 'fields',
  fields: [
    { key: 'cues', label: 'Looks to play', kind: 'textarea', required: true,
      placeholder: 'One look name per line',
      hint: 'Named looks from the pool, in order. A stop list is what makes '
        + 'this a show rather than a colour rotation - it can fade, hold and '
        + 'loop inside a single cue.' },
    { key: 'dwell_s', label: 'Seconds per look', kind: 'number', min: 1, step: 0.5,
      hint: 'How long each cue holds before the next one. Floored at 1s: the '
        + 'flash guard watches a look\'s own rate, not how fast they swap.' },
    { key: 'auto', label: 'Advance on its own', kind: 'checkbox',
      hint: 'Off: it only ever moves when you press. Double tap holds and '
        + 'releases it either way.' },
    { key: 'log_as', label: 'Log each cue as', kind: 'text', tier: 'tinker',
      placeholder: 'show',
      hint: 'Optional - one row per cue change.' },
  ],
  // Optional, like the field. One row per cue change, so a tally says how much
  // the show actually ran rather than how it looked.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'tally',
    noun: 'cue', better: null,
  },
  defaults: () => ({ cues: '', dwell_s: 8, auto: true, log_as: '' }),
  startedBy: 'gesture',
  exits: () => 'long press',
  describe: (mode) => {
    const cues = Array.isArray(mode.cues)
      ? mode.cues
      : String(mode.cues || '').split('\n').filter((line) => line.trim());
    const count = cues.length;
    if (!count) return 'Light show - no looks chosen yet';
    return `Light show - ${count} look${count === 1 ? '' : 's'}`
      + `${mode.auto === false ? ', manual' : `, ${mode.dwell_s || 8}s each`}`;
  },
});

export const TEMPLATE_BY_TYPE = Object.fromEntries(TEMPLATES.map((t) => [t.type, t]));

// Ready-made modes, offered next to "+ Add mode". Each is a complete mode
// object the parser accepts as-is - a starting point to edit, not a special
// kind of mode. Names are checked for collisions when one is added.
export const BUILTIN_MODES = [
  // A preset rather than a template, which is the whole point of TODO 44: the
  // alarm already rings and already waits, so the switch is two fields on it.
  // What a preset buys is *findability* - nobody looking for a dead man's
  // switch would think to open an alarm and read its fields.
  {
    id: 'deadman',
    label: "Dead man's switch",
    blurb: 'Rings to check in; runs an action if you do not answer.',
    mode: () => ({
      name: 'Check in', template: 'alarm',
      activation: { type: 'schedule', at: '09:00' },
      ...TEMPLATE_BY_TYPE.alarm.defaults(),
      message: 'Still there?',
      grace_minutes: 15,
      dismiss_event: 'checkin',
      on_timeout: { action: 'webhook', url: '', method: 'POST' },
    }),
  },
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
      ...TEMPLATE_BY_TYPE.alarm.defaults(),
      message: 'Wake up', snooze_minutes: 9, dismiss_event: 'woke_up',
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
    title: 'Reflexes',
    blurb: 'Always live, and they fire without thinking. Read top to bottom: '
      + "the first reflex that's awake now and sets this press, wins. Order "
      + 'is priority - move one up to win. Unset gesture -> falls through to '
      + 'the next. Below them sit the ones a clock sets off instead, where '
      + 'position means nothing.',
    emptyText: 'None yet.',
  },
  {
    nature: 'takeover',
    title: 'Apps',
    blurb: 'One at a time, and while it runs it owns the button - every '
      + 'reflex is muted until you leave. An alarm launches itself at its '
      + 'set time; the rest are launched by a reflex bound to “Launch an '
      + 'app”.',
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


/**
 * The colour a mode runs in, or null if it has none of its own.
 *
 * **Mirrors `main.app_look`** - the template's first LED state, the mode's
 * named look for it, falling back to that state's palette entry. Same answer
 * as the button gives, which is the whole point of showing it.
 *
 * Null for a template that owns no LED state (a reflex, a launcher, hot/cold,
 * a signal): those wear the button's own vocabulary or compute every frame, so
 * there is no one colour and inventing one would be worse than the gap.
 */
export function modeLook(mode, looks = {}, palette = {}) {
  const states = TEMPLATE_BY_TYPE[mode?.template]?.ledStates || [];
  if (!states.length) return null;
  const named = mode.looks && mode.looks[states[0]];
  return (named && looks[named]) || palette[states[0]] || null;
}

// --- can anything actually get to this? ------------------------------------
// The one question a config cannot answer by looking at any single mode, which
// is why the App page exists (TODO 49). Pure over data - no DOM, no fetch - so
// it is the same kind of function as rules.py host-side.

/** Resolve a gesture binding: an inline action, or a bare string naming one in
 *  the pool. Mirrors `config.resolve_action`; a name with no entry stays
 *  dangling on purpose, and reads here as "goes nowhere". */
function resolveBinding(binding, actions) {
  if (typeof binding === 'string') return (actions && actions[binding]) || null;
  return binding || null;
}

/** Every mode `mode` can hand the button to. */
function exitsOf(mode, byName, actions, allModes) {
  const out = [];
  const descriptor = TEMPLATE_BY_TYPE[mode?.template];
  for (const gesture of GESTURES) {
    const action = resolveBinding(mode[gesture.key], actions);
    if (action && action.action === 'enter_mode' && action.target) {
      const target = byName.get(action.target);
      if (target) out.push(target);
    }
  }
  if (descriptor?.type === 'launcher' || mode?.template === 'launcher') {
    // A launcher with no list offers everything a gesture can start, and new
    // apps join it without anyone editing it - which is exactly what makes it
    // the cheap way to keep an app reachable. Mirrors launcher_targets in
    // main.py, including its exclusion of other launchers.
    const named = Array.isArray(mode.targets)
      ? mode.targets
      : String(mode.targets || '').split('\n');
    const listed = named.map((n) => n.trim()).filter(Boolean);
    if (listed.length) {
      for (const name of listed) {
        const target = byName.get(name);
        if (target) out.push(target);
      }
    } else {
      for (const other of allModes) {
        if (other === mode || other?.template === 'launcher') continue;
        if (TEMPLATE_BY_TYPE[other?.template]?.nature === 'takeover') out.push(other);
      }
    }
  }
  return out;
}

/**
 * The set of modes something can reach, given the whole config.
 *
 * **Roots are the things nobody has to start.** A gesture map is live by
 * definition, and a clock starts its own apps. Everything else is reachable
 * only by being pointed at - by a gesture bound to "Launch an app", or by
 * sitting in a launcher's list - and reachability is transitive, because a
 * launcher you cannot open cannot open anything either. That transitivity is
 * the reason this is a walk rather than a filter, and the reason a per-mode
 * card could never answer the question on its own.
 */
export function reachableModes(modes, actions = {}) {
  const all = (modes || []).filter(Boolean);
  const byName = new Map(all.filter((m) => m.name).map((m) => [m.name, m]));
  const reached = new Set();
  const queue = [];
  const push = (mode) => {
    if (!mode || reached.has(mode)) return;
    reached.add(mode);
    queue.push(mode);
  };

  for (const mode of all) {
    const descriptor = TEMPLATE_BY_TYPE[mode.template];
    // An unknown template reads as a gesture map, the same harmless default
    // the nav takes - better to call something reachable and be wrong than to
    // report a working button as broken.
    if (!descriptor || descriptor.nature === 'ambient' || descriptor.startedBy === 'schedule') {
      push(mode);
    }
  }
  while (queue.length) {
    for (const target of exitsOf(queue.pop(), byName, actions, all)) push(target);
  }
  return reached;
}

/** Names an `enter_mode` points at that no mode answers to. Dangling on
 *  purpose (the parser warns, the editor says "(missing)"), so the page says
 *  it out loud rather than quietly repointing anything. */
export function danglingTargets(modes, actions = {}) {
  const all = (modes || []).filter(Boolean);
  const names = new Set(all.map((m) => m.name).filter(Boolean));
  const missing = new Map(); // target name -> [mode name that points at it]
  for (const mode of all) {
    for (const gesture of GESTURES) {
      const action = resolveBinding(mode[gesture.key], actions);
      if (!action || action.action !== 'enter_mode' || !action.target) continue;
      if (names.has(action.target)) continue;
      const from = missing.get(action.target) || [];
      from.push(`${gesture.label} on ${mode.name || '(unnamed)'}`);
      missing.set(action.target, from);
    }
  }
  return missing;
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

/** A percentage, 1-100, read off a colour's brightest channel. Two of a
 *  rainbow's fields ride this way - brightness in `color`, saturation in
 *  `color2` - because neither is a hue and the bytes were going spare.
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

/** The grey that stores `percent` as a level or a saturation. */
export function levelHex(percent) {
  const byte = Math.max(1, Math.min(255, Math.round((percent / 100) * 255)));
  const pair = byte.toString(16).padStart(2, '0');
  return `#${pair}${pair}${pair}`;
}

// How a stop's fade is shaped between its two colours (TODO 36b). Mirrors
// `sequencer.CURVES`; a curve the parser does not know falls back to linear
// rather than erroring, so drift here costs a shape and never a look.
//
// The synth reading is the useful one, and it is what these are *for*: a fade
// is a segment of an envelope, so "hold red a while then run fast up to
// yellow" is a long hold, a short fade, and `ease_in`. Asymmetric *periodic*
// motion - a breathe whose peak is narrower than its valley - is deliberately
// not a style here: that would be a firmware change against a frozen protocol,
// and a stop list approximates it with no wire cost at all.
// What moves a stop list along (TODO 36d). Mirrors `sequencer.DRIVES`, and
// `templates` mirrors `config.DRIVE_TEMPLATES` - which templates can supply
// each drive's number. An empty `templates` means "needs nothing", which is
// what makes `clock` bindable anywhere.
//
// The distinction is walked versus sampled, not the unit. A clock-driven list
// owns its own position; the other two are parameterised from outside
// themselves - a countdown owns its progress, a metronome owns its beat - so
// nothing can render one without an app underneath supplying the number.
// Binding one where nothing does is warned about, not refused: it plays on
// the clock instead, which is the same fail-soft rule a dangling look follows.
export const DRIVES = [
  { value: 'clock', label: 'Seconds', templates: [],
    hint: 'Plays on its own clock. Holds and fades are seconds.' },
  { value: 'progress', label: 'How far through', templates: ['countdown'],
    hint: 'Spread across the whole run, so the last stop lands as it finishes. '
      + 'Holds and fades are relative weights, not seconds. Countdown only - '
      + 'nothing else here knows how far through it is.' },
  { value: 'beats', label: 'Beats', templates: ['metronome'],
    hint: 'One cycle spread over that many beats, so it accents rather than '
      + 'drifts against the tempo. Metronome only.' },
];

export const CURVES = [
  { value: 'linear', label: 'Linear', hint: 'Even the whole way.' },
  { value: 'ease_in', label: 'Slow start', hint: 'Lingers, then runs - a build.' },
  { value: 'ease_out', label: 'Slow finish', hint: 'Moves at once, then settles - a landing.' },
  { value: 'ease_in_out', label: 'Slow both ends', hint: 'Eases out and back in - the gentlest.' },
  { value: 'exponential', label: 'Exponential', hint: 'Barely moves, then rushes. The steepest one.' },
];

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
  // `level` and `saturation` rather than `color`/`color2`: a rainbow generates
  // its own hues and reads the two colour fields as brightness and colour
  // strength. Mirrors device.py's STYLE_USES_LEVEL / STYLE_USES_SATURATION;
  // test_schema_mirror.py fails on drift.
  { type: 'rainbow', label: 'Rainbow', uses: ['period_s', 'level', 'saturation'],
    describe: (e) => `cycling every ${e.period_s}s at ${levelPercent(e.color)}%`
      + `, ${levelPercent(e.color2)}% colour` },
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
// **An entry carries an `effect` or a `sequence`, never both** (TODO 36a). A
// sequence is only offered where `allowSequence` says so - the system palette
// rows refuse them, because a palette entry ships to the device and renders
// unattended while a sequence is a schedule only the host can walk. Same rule
// `_parse_palette` enforces, applied one step earlier so the picker never
// shows you something the Save would drop.
//
// **A starting point, never a stored thing.** Picking one copies its body into
// whatever you are editing; nothing here reaches config.json unless you save it
// as a named look. That is why there can be a hundred of them without anybody's
// config growing, and why deleting a look never disturbs the library.
//
// The groups are the useful axis: nobody wants "all the blues", they want the
// one that means *resting*. Countdown presets are `progress`-driven and Tempo
// presets `beats`-driven, so those two only say anything under an app that can
// supply their number (see DRIVES); everything else runs on the clock.
//
// Two hardware facts shaped the colours, both from README's gotchas:
//   - This build's ring measures R:G:B at roughly 1.00 : 0.54 : 0.44 on a 3V3
//     rail (TODO 0c), so pure blues read dim and anything fading through white
//     reads warm. Anything that has to be *seen* leans red/amber; the blues are
//     for calm states where dim is the point. The presets are written to the
//     numbers, which is the only stable target - judge them on the onboard LED.
//   - Only `flash` and `alternate` strobe, and those are floored at 3 Hz (WCAG
//     2.3.1). Every strobing preset here sits at 0.45 s or slower, so the floor
//     never rewrites one. **A sequence has to clear two floors**: a stop that
//     strobes obeys that rule, and every stop's dwell (hold + fade) clears half
//     the floor once the sequence repeats or runs past three stops
//     (`config.sequence_safe`). 0.2 s is the shortest dwell used below.
//
// The array is deliberately **strict JSON**: test_look_presets.py slices it out
// and feeds every entry through the real Python parser, so a preset cannot ship
// a colour the config would reject or a rate it would clamp, and it fails if
// the two claims above stop being true. Keep comments outside the brackets.
export const LOOK_PRESETS = [
  { "id": "deep-water", "label": "Deep Water", "group": "Calm", "effect": { "style": "breathe", "color": "#0044ff", "color2": "#000000", "period_s": 4.5 } },
  { "id": "moss", "label": "Moss", "group": "Calm", "effect": { "style": "breathe", "color": "#1e8c46", "color2": "#000000", "period_s": 5 } },
  { "id": "ember", "label": "Ember", "group": "Calm", "effect": { "style": "breathe", "color": "#ff4400", "color2": "#000000", "period_s": 3.5 } },
  { "id": "candle", "label": "Candle", "group": "Calm", "effect": { "style": "breathe", "color": "#ff7a1a", "color2": "#000000", "period_s": 2.5 } },
  { "id": "slow-tide", "label": "Slow Tide", "group": "Calm", "effect": { "style": "fade", "color": "#002a55", "color2": "#00a0c0", "period_s": 6 } },
  { "id": "nightlight", "label": "Nightlight", "group": "Calm", "effect": { "style": "solid", "color": "#180600", "color2": "#000000", "period_s": 1 } },
  { "id": "dusk", "label": "Dusk", "group": "Calm", "effect": { "style": "fade", "color": "#2a0a40", "color2": "#ff5500", "period_s": 7 } },

  { "id": "deep-work", "label": "Deep Work", "group": "Focus", "effect": { "style": "solid", "color": "#00a866", "color2": "#000000", "period_s": 1 } },
  { "id": "flow", "label": "Flow", "group": "Focus", "effect": { "style": "breathe", "color": "#00d488", "color2": "#000000", "period_s": 6 } },
  { "id": "amber-desk", "label": "Amber Desk", "group": "Focus", "effect": { "style": "solid", "color": "#ffa000", "color2": "#000000", "period_s": 1 } },
  { "id": "tunnel", "label": "Tunnel", "group": "Focus", "effect": { "style": "fade", "color": "#001a0d", "color2": "#00ff77", "period_s": 4 } },
  { "id": "lantern", "label": "Lantern", "group": "Focus", "effect": { "style": "breathe", "color": "#ffc040", "color2": "#000000", "period_s": 4 } },

  { "id": "cooldown", "label": "Cooldown", "group": "Rest", "effect": { "style": "breathe", "color": "#00a8ff", "color2": "#000000", "period_s": 4 } },
  { "id": "meadow", "label": "Meadow", "group": "Rest", "effect": { "style": "fade", "color": "#6ac432", "color2": "#ffe95c", "period_s": 5 } },
  { "id": "warm-down", "label": "Warm Down", "group": "Rest", "effect": { "style": "fade", "color": "#ff8a00", "color2": "#3a1a00", "period_s": 5 } },
  { "id": "tea", "label": "Tea", "group": "Rest", "effect": { "style": "breathe", "color": "#b25a1e", "color2": "#000000", "period_s": 3 } },

  { "id": "klaxon", "label": "Klaxon", "group": "Alert", "effect": { "style": "flash", "color": "#ff0000", "color2": "#000000", "period_s": 0.5 } },
  { "id": "beacon", "label": "Beacon", "group": "Alert", "effect": { "style": "flash", "color": "#ff6a00", "color2": "#000000", "period_s": 0.9 } },
  { "id": "hazard", "label": "Hazard", "group": "Alert", "effect": { "style": "alternate", "color": "#ffc400", "color2": "#000000", "period_s": 0.6 } },
  { "id": "siren", "label": "Siren", "group": "Alert", "effect": { "style": "alternate", "color": "#ff0000", "color2": "#0033ff", "period_s": 0.45 } },
  { "id": "red-alert", "label": "Red Alert", "group": "Alert", "effect": { "style": "breathe", "color": "#ff0000", "color2": "#000000", "period_s": 1.2 } },
  { "id": "last-call", "label": "Last Call", "group": "Alert", "effect": { "style": "flash", "color": "#ff0044", "color2": "#000000", "period_s": 0.6 } },

  { "id": "green-light", "label": "Green Light", "group": "Done", "effect": { "style": "solid", "color": "#00ff2a", "color2": "#000000", "period_s": 1 } },
  { "id": "applause", "label": "Applause", "group": "Done", "effect": { "style": "rainbow", "color": "#ffffff", "color2": "#000000", "period_s": 0.7 } },
  { "id": "confetti", "label": "Confetti", "group": "Done", "effect": { "style": "rainbow", "color": "#ffffff", "color2": "#000000", "period_s": 1.4 } },
  { "id": "sunrise", "label": "Sunrise", "group": "Done", "effect": { "style": "fade", "color": "#ff1a00", "color2": "#ffd400", "period_s": 4.5 } },

  { "id": "on-air", "label": "On Air", "group": "Status", "effect": { "style": "solid", "color": "#ff0000", "color2": "#000000", "period_s": 1 } },
  { "id": "standby", "label": "Standby", "group": "Status", "effect": { "style": "solid", "color": "#ffa000", "color2": "#000000", "period_s": 1 } },
  { "id": "clear", "label": "Clear", "group": "Status", "effect": { "style": "solid", "color": "#00e04a", "color2": "#000000", "period_s": 1 } },
  { "id": "do-not-disturb", "label": "Do Not Disturb", "group": "Status", "effect": { "style": "breathe", "color": "#ff0033", "color2": "#000000", "period_s": 3 } },

  { "id": "downbeat", "label": "Downbeat", "group": "Time", "effect": { "style": "flash", "color": "#ffffff", "color2": "#000000", "period_s": 0.5 } },
  { "id": "tick", "label": "Tick", "group": "Time", "effect": { "style": "flash", "color": "#00e5ff", "color2": "#000000", "period_s": 0.5 } },
  { "id": "pulse", "label": "Pulse", "group": "Time", "effect": { "style": "breathe", "color": "#ff00aa", "color2": "#000000", "period_s": 1 } },

  { "id": "disco", "label": "Disco", "group": "Play", "effect": { "style": "rainbow", "color": "#ffffff", "color2": "#000000", "period_s": 0.5 } },
  { "id": "lava-lamp", "label": "Lava Lamp", "group": "Play", "effect": { "style": "fade", "color": "#ff0066", "color2": "#ffb400", "period_s": 7 } },
  { "id": "cyberpunk", "label": "Cyberpunk", "group": "Play", "effect": { "style": "alternate", "color": "#ff00ff", "color2": "#00ffff", "period_s": 0.7 } },
  { "id": "firefly", "label": "Firefly", "group": "Play", "effect": { "style": "breathe", "color": "#b6ff00", "color2": "#000000", "period_s": 2.2 } },

  { "id": "three-cheers", "label": "Three Cheers", "group": "Patterns", "sequence": { "repeat": false, "stops": [
    { "color": "#00ff2a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.22, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.22, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.46, "fade_s": 0 } ] } },
  { "id": "sunrise-run", "label": "Sunrise Run", "group": "Patterns", "sequence": { "repeat": false, "stops": [
    { "color": "#ff1a00", "hold_s": 1.1, "fade_s": 0 }, { "color": "#ffd400", "hold_s": 0.4, "fade_s": 0.7, "curve": "exponential" },
    { "color": "#00ff2a", "hold_s": 0.6, "fade_s": 0.9, "curve": "linear" } ] } },
  { "id": "heartbeat", "label": "Heartbeat", "group": "Patterns", "sequence": { "repeat": true, "stops": [
    { "color": "#ff0033", "hold_s": 0.17, "fade_s": 0 }, { "color": "#2a0008", "hold_s": 0.17, "fade_s": 0.17, "curve": "ease_out" },
    { "color": "#ff0033", "hold_s": 0.17, "fade_s": 0 }, { "color": "#0a0002", "hold_s": 0.75, "fade_s": 0.34, "curve": "ease_out" } ] } },
  { "id": "nope", "label": "Nope", "group": "Patterns", "sequence": { "repeat": false, "stops": [
    { "color": "#ff0000", "hold_s": 0.2, "fade_s": 0 }, { "color": "#200000", "hold_s": 0.18, "fade_s": 0 },
    { "color": "#ff0000", "hold_s": 0.55, "fade_s": 0 } ] } },
  { "id": "wake-up", "label": "Wake Up", "group": "Patterns", "sequence": { "repeat": true, "stops": [
    { "color": "#100800", "hold_s": 0.4, "fade_s": 1.8, "curve": "ease_in" },
    { "color": "#ffb400", "hold_s": 0.6, "fade_s": 1.2, "curve": "ease_in_out" },
    { "color": "#100800", "hold_s": 0.4, "fade_s": 1.6, "curve": "ease_out" } ] } },

  { "id": "yes-tick", "label": "Yes", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#00ff2a", "hold_s": 0.1, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.08, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.5, "fade_s": 0 } ] } },
  { "id": "no-buzz", "label": "No", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#ff0000", "hold_s": 0.14, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.1, "fade_s": 0 },
    { "color": "#ff0000", "hold_s": 0.45, "fade_s": 0 } ] } },
  { "id": "maybe", "label": "Maybe", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#ffb400", "hold_s": 0.25, "fade_s": 0.25, "curve": "ease_out" }, { "color": "#ffb400", "hold_s": 0.6, "fade_s": 0 } ] } },
  { "id": "got-it", "label": "Got It", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#ffffff", "hold_s": 0.07, "fade_s": 0 }, { "color": "#00ff2a", "hold_s": 0.7, "fade_s": 0.18, "curve": "ease_out" } ] } },
  { "id": "saved", "label": "Saved", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#00331a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#00e05a", "hold_s": 0.8, "fade_s": 0.5, "curve": "ease_out" } ] } },
  { "id": "sent", "label": "Sent", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#00e5ff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#003844", "hold_s": 0.25, "fade_s": 0.5, "curve": "ease_in" },
    { "color": "#000000", "hold_s": 0.2, "fade_s": 0 } ] } },
  { "id": "undone", "label": "Undone", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#ffb400", "hold_s": 0.5, "fade_s": 0.3, "curve": "ease_in" },
    { "color": "#241400", "hold_s": 0.3, "fade_s": 0.4, "curve": "ease_out" } ] } },
  { "id": "denied", "label": "Denied", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#ff0022", "hold_s": 0.22, "fade_s": 0 }, { "color": "#2a0006", "hold_s": 0.22, "fade_s": 0 },
    { "color": "#ff0022", "hold_s": 0.46, "fade_s": 0 } ] } },
  { "id": "queued", "label": "Queued", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#3a6bff", "hold_s": 0.3, "fade_s": 0.35, "curve": "ease_in_out" },
    { "color": "#08122e", "hold_s": 0.3, "fade_s": 0.35, "curve": "ease_in_out" } ] } },
  { "id": "copied", "label": "Copied", "group": "Confirm", "sequence": { "repeat": false, "stops": [
    { "color": "#ffffff", "hold_s": 0.09, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.09, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.3, "fade_s": 0 } ] } },

  { "id": "burn-down", "label": "Burn Down", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#00ff2a", "hold_s": 3, "fade_s": 0 }, { "color": "#ffcc00", "hold_s": 1, "fade_s": 2, "curve": "ease_in" },
    { "color": "#ff0000", "hold_s": 1, "fade_s": 2, "curve": "exponential" } ] } },
  { "id": "last-minute", "label": "Last Minute", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#0a3a1a", "hold_s": 5, "fade_s": 0 }, { "color": "#ffb400", "hold_s": 1, "fade_s": 1, "curve": "ease_in" },
    { "color": "#ff0000", "hold_s": 0.4, "fade_s": 0.8, "curve": "exponential" },
    { "color": "#2b0000", "hold_s": 0.4, "fade_s": 0 }, { "color": "#ff0000", "hold_s": 0.4, "fade_s": 0 } ] } },
  { "id": "tea-steep", "label": "Tea Steep", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#f2e0b0", "hold_s": 1, "fade_s": 0 }, { "color": "#b2711e", "hold_s": 3, "fade_s": 4 },
    { "color": "#5a2c00", "hold_s": 1, "fade_s": 1, "curve": "ease_out" } ] } },
  { "id": "fuse", "label": "Fuse", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#2a1400", "hold_s": 4, "fade_s": 0 }, { "color": "#ff6a00", "hold_s": 2, "fade_s": 2, "curve": "exponential" },
    { "color": "#ffffff", "hold_s": 0.6, "fade_s": 0.4, "curve": "exponential" } ] } },
  { "id": "thaw", "label": "Thaw", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#0044ff", "hold_s": 2, "fade_s": 0 }, { "color": "#66ccff", "hold_s": 2, "fade_s": 3, "curve": "ease_in_out" },
    { "color": "#ffffff", "hold_s": 1, "fade_s": 2, "curve": "ease_out" } ] } },
  { "id": "traffic", "label": "Traffic Light", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#00c832", "hold_s": 4, "fade_s": 0 }, { "color": "#ffb400", "hold_s": 2, "fade_s": 0 },
    { "color": "#ff0000", "hold_s": 3, "fade_s": 0 } ] } },
  { "id": "pressure", "label": "Pressure", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#140000", "hold_s": 3, "fade_s": 0 }, { "color": "#ff0000", "hold_s": 4, "fade_s": 5, "curve": "exponential" } ] } },
  { "id": "tide-out", "label": "Tide Out", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#00a0c0", "hold_s": 2, "fade_s": 0 }, { "color": "#00506a", "hold_s": 3, "fade_s": 4, "curve": "ease_in_out" },
    { "color": "#001824", "hold_s": 2, "fade_s": 2, "curve": "ease_out" } ] } },
  { "id": "oven", "label": "Oven", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#2a0000", "hold_s": 2, "fade_s": 0 }, { "color": "#ff3300", "hold_s": 3, "fade_s": 4, "curve": "ease_in" },
    { "color": "#ffb400", "hold_s": 2, "fade_s": 2, "curve": "ease_out" } ] } },
  { "id": "runway-lights", "label": "Runway", "group": "Countdown", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#0a1400", "hold_s": 3, "fade_s": 0 }, { "color": "#7cff00", "hold_s": 2, "fade_s": 1 },
    { "color": "#ffffff", "hold_s": 1.5, "fade_s": 1, "curve": "ease_in" } ] } },

  { "id": "downbeat-4", "label": "Downbeat (4)", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#ffffff", "hold_s": 1, "fade_s": 0 }, { "color": "#1a1a1a", "hold_s": 3, "fade_s": 0 } ] } },
  { "id": "waltz-3", "label": "Waltz (3)", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#ff66aa", "hold_s": 1, "fade_s": 0 }, { "color": "#2a0d1a", "hold_s": 2, "fade_s": 0 } ] } },
  { "id": "six-eight", "label": "Six Eight", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#ffd400", "hold_s": 1, "fade_s": 0 }, { "color": "#241d00", "hold_s": 2, "fade_s": 0 },
    { "color": "#ff8a00", "hold_s": 1, "fade_s": 0 }, { "color": "#241000", "hold_s": 2, "fade_s": 0 } ] } },
  { "id": "clave", "label": "Clave (3-2)", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#00e5ff", "hold_s": 0.25, "fade_s": 0 }, { "color": "#001a1e", "hold_s": 1.25, "fade_s": 0 },
    { "color": "#00e5ff", "hold_s": 0.25, "fade_s": 0 }, { "color": "#001a1e", "hold_s": 1.25, "fade_s": 0 },
    { "color": "#00e5ff", "hold_s": 0.25, "fade_s": 0 }, { "color": "#001a1e", "hold_s": 1.75, "fade_s": 0 },
    { "color": "#00e5ff", "hold_s": 0.25, "fade_s": 0 }, { "color": "#001a1e", "hold_s": 0.75, "fade_s": 0 },
    { "color": "#00e5ff", "hold_s": 0.25, "fade_s": 0 }, { "color": "#001a1e", "hold_s": 1.75, "fade_s": 0 } ] } },
  { "id": "backbeat", "label": "Backbeat (2 & 4)", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#140a00", "hold_s": 1, "fade_s": 0 }, { "color": "#ff6a00", "hold_s": 1, "fade_s": 0 },
    { "color": "#140a00", "hold_s": 1, "fade_s": 0 }, { "color": "#ff6a00", "hold_s": 1, "fade_s": 0 } ] } },
  { "id": "bar-colour", "label": "Bar Colours", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#ff0044", "hold_s": 1, "fade_s": 0 }, { "color": "#ffb400", "hold_s": 1, "fade_s": 0 },
    { "color": "#00e05a", "hold_s": 1, "fade_s": 0 }, { "color": "#3a6bff", "hold_s": 1, "fade_s": 0 } ] } },
  { "id": "count-in", "label": "Count In", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#ffffff", "hold_s": 1, "fade_s": 0 }, { "color": "#3a3a3a", "hold_s": 1, "fade_s": 0 },
    { "color": "#3a3a3a", "hold_s": 1, "fade_s": 0 }, { "color": "#3a3a3a", "hold_s": 1, "fade_s": 0 } ] } },
  { "id": "swing", "label": "Swing", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#ffb400", "hold_s": 0.66, "fade_s": 0 }, { "color": "#1a1200", "hold_s": 1.34, "fade_s": 0 } ] } },
  { "id": "two-bar", "label": "Two Bar Phrase", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#00ff88", "hold_s": 1, "fade_s": 0 }, { "color": "#04241a", "hold_s": 3, "fade_s": 0 },
    { "color": "#0a2a1e", "hold_s": 1, "fade_s": 0 }, { "color": "#04241a", "hold_s": 3, "fade_s": 0 } ] } },
  { "id": "vu-pump", "label": "VU Pump", "group": "Tempo", "sequence": { "drive": "beats", "repeat": true, "stops": [
    { "color": "#00e05a", "hold_s": 0.5, "fade_s": 0 }, { "color": "#ffb400", "hold_s": 0.5, "fade_s": 0 },
    { "color": "#ff0022", "hold_s": 0.5, "fade_s": 0 }, { "color": "#0a0500", "hold_s": 2.5, "fade_s": 0 } ] } },

  { "id": "sunrise-slow", "label": "Daybreak", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#050010", "hold_s": 1.5, "fade_s": 0 }, { "color": "#4a1050", "hold_s": 1, "fade_s": 2.5, "curve": "ease_in" },
    { "color": "#ff5a00", "hold_s": 1, "fade_s": 2.5, "curve": "ease_in_out" },
    { "color": "#ffd48a", "hold_s": 2, "fade_s": 2.5, "curve": "ease_out" } ] } },
  { "id": "sunset-slow", "label": "Last Light", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#ffc46a", "hold_s": 2, "fade_s": 0 }, { "color": "#ff4a00", "hold_s": 1, "fade_s": 2.5, "curve": "ease_in_out" },
    { "color": "#5a0d33", "hold_s": 1, "fade_s": 2.5, "curve": "ease_in" }, { "color": "#05000f", "hold_s": 2, "fade_s": 2, "curve": "ease_out" } ] } },
  { "id": "campfire", "label": "Campfire", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#ff5a00", "hold_s": 0.35, "fade_s": 0.25, "curve": "ease_out" }, { "color": "#ffa030", "hold_s": 0.25, "fade_s": 0.2 },
    { "color": "#c02800", "hold_s": 0.3, "fade_s": 0.3, "curve": "ease_in" }, { "color": "#ff7a10", "hold_s": 0.2, "fade_s": 0.25 } ] } },
  { "id": "lightning-storm", "label": "Lightning Storm", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#050812", "hold_s": 2.4, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#0a1020", "hold_s": 0.25, "fade_s": 0 }, { "color": "#e8f0ff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#050812", "hold_s": 3.2, "fade_s": 0 } ] } },
  { "id": "ocean-swell", "label": "Ocean Swell", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#00243a", "hold_s": 1, "fade_s": 2.5, "curve": "ease_in_out" },
    { "color": "#00a0c0", "hold_s": 0.6, "fade_s": 1.6, "curve": "ease_out" },
    { "color": "#004a66", "hold_s": 1, "fade_s": 2.2, "curve": "ease_in_out" } ] } },
  { "id": "aurora", "label": "Aurora", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#00ff9a", "hold_s": 1, "fade_s": 2.4, "curve": "ease_in_out" },
    { "color": "#00c8ff", "hold_s": 0.8, "fade_s": 2.2, "curve": "ease_in_out" },
    { "color": "#8a4aff", "hold_s": 0.8, "fade_s": 2.4, "curve": "ease_in_out" }, { "color": "#004a3a", "hold_s": 1, "fade_s": 2, "curve": "ease_in" } ] } },
  { "id": "forest-canopy", "label": "Forest Canopy", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#0d3a12", "hold_s": 1.4, "fade_s": 1.8, "curve": "ease_in_out" },
    { "color": "#6ac432", "hold_s": 0.8, "fade_s": 1.6, "curve": "ease_out" },
    { "color": "#173f18", "hold_s": 1.2, "fade_s": 1.8, "curve": "ease_in_out" } ] } },
  { "id": "moonrise", "label": "Moonrise", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#02030a", "hold_s": 2, "fade_s": 0 }, { "color": "#1a2a5a", "hold_s": 1, "fade_s": 2.5, "curve": "ease_in" },
    { "color": "#c8d8ff", "hold_s": 1.6, "fade_s": 2, "curve": "ease_out" } ] } },
  { "id": "tidepool", "label": "Tidepool", "group": "Nature", "sequence": { "repeat": true, "stops": [
    { "color": "#00404a", "hold_s": 1.2, "fade_s": 1.4, "curve": "ease_in_out" },
    { "color": "#00b4a0", "hold_s": 0.6, "fade_s": 1.2, "curve": "ease_out" },
    { "color": "#1e6a4a", "hold_s": 0.8, "fade_s": 1.4, "curve": "ease_in_out" },
    { "color": "#00303a", "hold_s": 1, "fade_s": 1.2, "curve": "ease_in" } ] } },

  { "id": "police", "label": "Police", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#0033ff", "hold_s": 0.45, "fade_s": 0 }, { "color": "#ff0000", "hold_s": 0.45, "fade_s": 0 } ] } },
  { "id": "ambulance", "label": "Ambulance", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#ff0022", "hold_s": 0.3, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.3, "fade_s": 0 },
    { "color": "#ff0022", "hold_s": 0.3, "fade_s": 0 }, { "color": "#0a0000", "hold_s": 0.6, "fade_s": 0 } ] } },
  { "id": "fire-truck", "label": "Fire Truck", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#ff0000", "hold_s": 0.25, "fade_s": 0 }, { "color": "#1a0000", "hold_s": 0.25, "fade_s": 0 },
    { "color": "#ff0000", "hold_s": 0.25, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.5, "fade_s": 0 } ] } },
  { "id": "lighthouse", "label": "Lighthouse", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#ffffff", "hold_s": 0.35, "fade_s": 0.35, "curve": "ease_in_out" },
    { "color": "#02040a", "hold_s": 2.4, "fade_s": 0.5, "curve": "ease_out" } ] } },
  { "id": "hazard-beacon", "label": "Hazard Beacon", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#ffb400", "hold_s": 0.25, "fade_s": 0 }, { "color": "#1a1000", "hold_s": 0.45, "fade_s": 0 },
    { "color": "#ffb400", "hold_s": 0.25, "fade_s": 0 }, { "color": "#1a1000", "hold_s": 1.1, "fade_s": 0 } ] } },
  { "id": "air-raid", "label": "Air Raid", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#ff2200", "hold_s": 1, "fade_s": 1.4, "curve": "ease_in" }, { "color": "#3a0500", "hold_s": 0.6, "fade_s": 1.4, "curve": "ease_out" } ] } },
  { "id": "sos", "label": "SOS", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.55, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.6, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.6, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.6, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.55, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 1.4, "fade_s": 0 } ] } },
  { "id": "channel-buoy", "label": "Channel Buoy", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#00ff2a", "hold_s": 0.3, "fade_s": 0 }, { "color": "#001a06", "hold_s": 1.7, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.3, "fade_s": 0 }, { "color": "#001a06", "hold_s": 3, "fade_s": 0 } ] } },
  { "id": "beacon-sweep", "label": "Beacon Sweep", "group": "Signals", "sequence": { "repeat": true, "stops": [
    { "color": "#ff6a00", "hold_s": 0.2, "fade_s": 0.8, "curve": "ease_in" }, { "color": "#ff6a00", "hold_s": 0.3, "fade_s": 0 },
    { "color": "#140800", "hold_s": 0.4, "fade_s": 0.9, "curve": "ease_out" } ] } },

  { "id": "crt-warmup", "label": "CRT Warm-up", "group": "Retro", "sequence": { "repeat": false, "stops": [
    { "color": "#000000", "hold_s": 0.4, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0.2, "curve": "exponential" },
    { "color": "#0a2a1a", "hold_s": 0.3, "fade_s": 0.3, "curve": "ease_out" },
    { "color": "#00ff66", "hold_s": 1.6, "fade_s": 0.6, "curve": "ease_in" } ] } },
  { "id": "loading-bar", "label": "Loading Bar", "group": "Retro", "sequence": { "drive": "progress", "repeat": false, "stops": [
    { "color": "#0a1a2a", "hold_s": 1, "fade_s": 0 }, { "color": "#1e5aa8", "hold_s": 2, "fade_s": 1 },
    { "color": "#3a9bff", "hold_s": 2, "fade_s": 1 }, { "color": "#9fd8ff", "hold_s": 2, "fade_s": 1 } ] } },
  { "id": "arcade-attract", "label": "Arcade Attract", "group": "Retro", "sequence": { "repeat": true, "stops": [
    { "color": "#ff00ff", "hold_s": 0.3, "fade_s": 0 }, { "color": "#00ffff", "hold_s": 0.3, "fade_s": 0 },
    { "color": "#ffff00", "hold_s": 0.3, "fade_s": 0 }, { "color": "#00ff00", "hold_s": 0.3, "fade_s": 0 } ] } },
  { "id": "dial-up", "label": "Dial-up", "group": "Retro", "sequence": { "repeat": true, "stops": [
    { "color": "#00ff66", "hold_s": 0.2, "fade_s": 0 }, { "color": "#0a1400", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff66", "hold_s": 0.2, "fade_s": 0 }, { "color": "#0a1400", "hold_s": 0.55, "fade_s": 0 },
    { "color": "#ffb400", "hold_s": 0.8, "fade_s": 0.3, "curve": "ease_in" }, { "color": "#0a0a00", "hold_s": 0.4, "fade_s": 0 } ] } },
  { "id": "tape-rewind", "label": "Tape Rewind", "group": "Retro", "sequence": { "repeat": true, "stops": [
    { "color": "#8a4a1e", "hold_s": 0.2, "fade_s": 0 }, { "color": "#2a1200", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#8a4a1e", "hold_s": 0.2, "fade_s": 0 }, { "color": "#2a1200", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#8a4a1e", "hold_s": 0.2, "fade_s": 0 }, { "color": "#2a1200", "hold_s": 0.6, "fade_s": 0 } ] } },
  { "id": "floppy-seek", "label": "Floppy Seek", "group": "Retro", "sequence": { "repeat": true, "stops": [
    { "color": "#ff2200", "hold_s": 0.25, "fade_s": 0 }, { "color": "#140000", "hold_s": 0.3, "fade_s": 0 },
    { "color": "#ff2200", "hold_s": 0.25, "fade_s": 0 }, { "color": "#140000", "hold_s": 1.2, "fade_s": 0 } ] } },
  { "id": "pinball-bonus", "label": "Pinball Bonus", "group": "Retro", "sequence": { "repeat": false, "stops": [
    { "color": "#ffff00", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ff0088", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffff00", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ff0088", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.9, "fade_s": 0 } ] } },
  { "id": "game-over", "label": "Game Over", "group": "Retro", "sequence": { "repeat": false, "stops": [
    { "color": "#ff0000", "hold_s": 0.45, "fade_s": 0 }, { "color": "#3a0000", "hold_s": 0.45, "fade_s": 0 },
    { "color": "#ff0000", "hold_s": 0.45, "fade_s": 0 }, { "color": "#3a0000", "hold_s": 0.45, "fade_s": 0 },
    { "color": "#1a0000", "hold_s": 1.4, "fade_s": 0.8, "curve": "ease_out" } ] } },
  { "id": "one-up", "label": "1-Up", "group": "Retro", "sequence": { "repeat": false, "stops": [
    { "color": "#00ff2a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.8, "fade_s": 0 } ] } },

  { "id": "deep-dive", "label": "Deep Dive", "group": "Focus", "sequence": { "repeat": true, "stops": [
    { "color": "#00304a", "hold_s": 2, "fade_s": 3, "curve": "ease_in_out" }, { "color": "#0a1a2a", "hold_s": 2, "fade_s": 3, "curve": "ease_in_out" } ] } },
  { "id": "flow-state", "label": "In The Zone", "group": "Focus", "sequence": { "repeat": true, "stops": [
    { "color": "#00d488", "hold_s": 2.5, "fade_s": 2.5, "curve": "ease_in_out" },
    { "color": "#00543a", "hold_s": 1.5, "fade_s": 2.5, "curve": "ease_in_out" } ] } },
  { "id": "work-block", "label": "Work Block", "group": "Focus", "sequence": { "repeat": true, "stops": [
    { "color": "#00a866", "hold_s": 0.4, "fade_s": 2.6, "curve": "ease_in_out" },
    { "color": "#00170e", "hold_s": 0.4, "fade_s": 2.6, "curve": "ease_in_out" } ] } },
  { "id": "break-block", "label": "Break Block", "group": "Focus", "sequence": { "repeat": true, "stops": [
    { "color": "#00a8ff", "hold_s": 0.3, "fade_s": 1.7, "curve": "ease_in_out" },
    { "color": "#001a29", "hold_s": 0.3, "fade_s": 1.7, "curve": "ease_in_out" } ] } },
  { "id": "dnd-pulse", "label": "Busy Pulse", "group": "Focus", "sequence": { "repeat": true, "stops": [
    { "color": "#ff0033", "hold_s": 0.8, "fade_s": 1.4, "curve": "ease_in_out" },
    { "color": "#2a0008", "hold_s": 1, "fade_s": 1.4, "curve": "ease_in_out" } ] } },
  { "id": "warm-up", "label": "Warm Up", "group": "Focus", "sequence": { "repeat": false, "stops": [
    { "color": "#241400", "hold_s": 1, "fade_s": 0 }, { "color": "#ffa000", "hold_s": 2, "fade_s": 3, "curve": "ease_in" } ] } },
  { "id": "cool-down", "label": "Taper", "group": "Focus", "sequence": { "repeat": false, "stops": [
    { "color": "#ff8a00", "hold_s": 1, "fade_s": 0 }, { "color": "#3a1a00", "hold_s": 2, "fade_s": 4, "curve": "ease_out" } ] } },
  { "id": "crunch", "label": "Crunch", "group": "Focus", "sequence": { "repeat": true, "stops": [
    { "color": "#ff3300", "hold_s": 0.5, "fade_s": 0.5, "curve": "ease_in" },
    { "color": "#ffb400", "hold_s": 0.3, "fade_s": 0.4, "curve": "ease_out" },
    { "color": "#2a0800", "hold_s": 0.5, "fade_s": 0.5, "curve": "ease_in" } ] } },

  { "id": "anxious", "label": "Anxious", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#ffb400", "hold_s": 0.25, "fade_s": 0.2, "curve": "ease_in" },
    { "color": "#2a1800", "hold_s": 0.2, "fade_s": 0.25, "curve": "ease_out" }, { "color": "#ffb400", "hold_s": 0.2, "fade_s": 0.2 },
    { "color": "#2a1800", "hold_s": 0.8, "fade_s": 0.3, "curve": "ease_out" } ] } },
  { "id": "content", "label": "Content", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#ffb46a", "hold_s": 2.5, "fade_s": 2.5, "curve": "ease_in_out" },
    { "color": "#6a3a1a", "hold_s": 1.5, "fade_s": 2.5, "curve": "ease_in_out" } ] } },
  { "id": "restless", "label": "Restless", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#8a4aff", "hold_s": 0.4, "fade_s": 0.3 }, { "color": "#1a0a2a", "hold_s": 0.3, "fade_s": 0.3 },
    { "color": "#4a8aff", "hold_s": 0.35, "fade_s": 0.3 }, { "color": "#0a0a2a", "hold_s": 0.5, "fade_s": 0.4 } ] } },
  { "id": "melancholy", "label": "Melancholy", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#1e3a6a", "hold_s": 2, "fade_s": 3, "curve": "ease_in_out" },
    { "color": "#050a1a", "hold_s": 2.5, "fade_s": 3, "curve": "ease_in_out" } ] } },
  { "id": "elated", "label": "Elated", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#ffff00", "hold_s": 0.3, "fade_s": 0.25, "curve": "ease_out" }, { "color": "#ff8a00", "hold_s": 0.25, "fade_s": 0.25 },
    { "color": "#ffffff", "hold_s": 0.3, "fade_s": 0.25, "curve": "ease_out" }, { "color": "#ffcc00", "hold_s": 0.4, "fade_s": 0.3 } ] } },
  { "id": "simmer", "label": "Simmer", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#ff3300", "hold_s": 1, "fade_s": 1.6, "curve": "ease_in_out" },
    { "color": "#5a0d00", "hold_s": 1.2, "fade_s": 1.6, "curve": "ease_in_out" } ] } },
  { "id": "drift", "label": "Drift", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#4a8aff", "hold_s": 1.5, "fade_s": 3, "curve": "ease_in_out" },
    { "color": "#8a4aff", "hold_s": 1.5, "fade_s": 3, "curve": "ease_in_out" },
    { "color": "#0a1a3a", "hold_s": 1.5, "fade_s": 3, "curve": "ease_in_out" } ] } },
  { "id": "brace", "label": "Brace", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#140000", "hold_s": 1.6, "fade_s": 0 }, { "color": "#ff0000", "hold_s": 0.4, "fade_s": 0.9, "curve": "exponential" },
    { "color": "#3a0000", "hold_s": 0.5, "fade_s": 0.5, "curve": "ease_out" } ] } },
  { "id": "unwind", "label": "Unwind", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#ff8a00", "hold_s": 1.5, "fade_s": 2.5, "curve": "ease_out" },
    { "color": "#8a2a4a", "hold_s": 1.5, "fade_s": 2.5, "curve": "ease_in_out" },
    { "color": "#0a0518", "hold_s": 2, "fade_s": 2.5, "curve": "ease_in" } ] } },
  { "id": "spark", "label": "Spark", "group": "Mood", "sequence": { "repeat": true, "stops": [
    { "color": "#0a0a00", "hold_s": 1.4, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffcc00", "hold_s": 0.5, "fade_s": 0.5, "curve": "ease_out" } ] } },

  { "id": "disco-floor", "label": "Disco Floor", "group": "Play", "sequence": { "repeat": true, "stops": [
    { "color": "#ff00ff", "hold_s": 0.25, "fade_s": 0 }, { "color": "#00ffff", "hold_s": 0.25, "fade_s": 0 },
    { "color": "#ffff00", "hold_s": 0.25, "fade_s": 0 } ] } },
  { "id": "rainbow-chase", "label": "Rainbow Chase", "group": "Play", "sequence": { "repeat": true, "stops": [
    { "color": "#ff0000", "hold_s": 0.2, "fade_s": 0.3 }, { "color": "#ffaa00", "hold_s": 0.2, "fade_s": 0.3 },
    { "color": "#00ff2a", "hold_s": 0.2, "fade_s": 0.3 }, { "color": "#00d5ff", "hold_s": 0.2, "fade_s": 0.3 },
    { "color": "#3a2bff", "hold_s": 0.2, "fade_s": 0.3 }, { "color": "#ff00c8", "hold_s": 0.2, "fade_s": 0.3 } ] } },
  { "id": "candy", "label": "Candy", "group": "Play", "sequence": { "repeat": true, "stops": [
    { "color": "#ff69b4", "hold_s": 0.5, "fade_s": 0.3, "curve": "ease_in_out" },
    { "color": "#7cf0ff", "hold_s": 0.5, "fade_s": 0.3, "curve": "ease_in_out" },
    { "color": "#fff36a", "hold_s": 0.5, "fade_s": 0.3, "curve": "ease_in_out" } ] } },
  { "id": "neon-sign", "label": "Neon Sign", "group": "Play", "sequence": { "repeat": true, "stops": [
    { "color": "#ff00aa", "hold_s": 1.4, "fade_s": 0 }, { "color": "#3a0022", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ff00aa", "hold_s": 0.25, "fade_s": 0 }, { "color": "#3a0022", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ff00aa", "hold_s": 2, "fade_s": 0 } ] } },
  { "id": "slot-machine", "label": "Slot Machine", "group": "Play", "sequence": { "repeat": false, "stops": [
    { "color": "#ffcc00", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ff0044", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00e5ff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffcc00", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ff0044", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 1.2, "fade_s": 0 } ] } },
  { "id": "carnival", "label": "Carnival", "group": "Play", "sequence": { "repeat": true, "stops": [
    { "color": "#ff0044", "hold_s": 0.3, "fade_s": 0 }, { "color": "#ffcc00", "hold_s": 0.3, "fade_s": 0 },
    { "color": "#00e05a", "hold_s": 0.3, "fade_s": 0 }, { "color": "#3a6bff", "hold_s": 0.3, "fade_s": 0 } ] } },
  { "id": "laser-tag", "label": "Laser Tag", "group": "Play", "sequence": { "repeat": true, "stops": [
    { "color": "#00ff88", "hold_s": 0.2, "fade_s": 0 }, { "color": "#020a06", "hold_s": 0.3, "fade_s": 0 },
    { "color": "#ff0088", "hold_s": 0.2, "fade_s": 0 }, { "color": "#0a0206", "hold_s": 0.3, "fade_s": 0 },
    { "color": "#00e5ff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#02080a", "hold_s": 0.8, "fade_s": 0 } ] } },
  { "id": "bubble", "label": "Bubble", "group": "Play", "sequence": { "repeat": true, "stops": [
    { "color": "#7cf0ff", "hold_s": 0.3, "fade_s": 0.8, "curve": "ease_out" },
    { "color": "#0a2a30", "hold_s": 0.4, "fade_s": 0.9, "curve": "ease_in" } ] } },
  { "id": "confetti-burst", "label": "Confetti Burst", "group": "Play", "sequence": { "repeat": false, "stops": [
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ff0088", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00e5ff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffcc00", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff66", "hold_s": 0.2, "fade_s": 0 }, { "color": "#1a1a1a", "hold_s": 0.9, "fade_s": 0 } ] } },
  { "id": "jackpot", "label": "Jackpot", "group": "Play", "sequence": { "repeat": false, "stops": [
    { "color": "#ffd400", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffd400", "hold_s": 0.2, "fade_s": 0 }, { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ff0059", "hold_s": 0.2, "fade_s": 0.2 }, { "color": "#00ff2a", "hold_s": 0.2, "fade_s": 0.2 },
    { "color": "#00d5ff", "hold_s": 0.2, "fade_s": 0.2 }, { "color": "#ffd400", "hold_s": 0.4, "fade_s": 0.2 } ] } },

  { "id": "lava-flow", "label": "Lava Flow", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#ff2200", "hold_s": 2, "fade_s": 3.5, "curve": "ease_in_out" },
    { "color": "#ffb400", "hold_s": 1.5, "fade_s": 3, "curve": "ease_in_out" },
    { "color": "#5a0d00", "hold_s": 2, "fade_s": 3.5, "curve": "ease_in_out" } ] } },
  { "id": "breathing-room", "label": "Breathing Room", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#1e8c46", "hold_s": 1.5, "fade_s": 3, "curve": "ease_in_out" },
    { "color": "#02180c", "hold_s": 2, "fade_s": 3, "curve": "ease_in_out" } ] } },
  { "id": "embers", "label": "Embers", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#5a1400", "hold_s": 1.5, "fade_s": 2, "curve": "ease_in_out" },
    { "color": "#ff4400", "hold_s": 0.6, "fade_s": 1.4, "curve": "ease_out" }, { "color": "#2a0800", "hold_s": 1.6, "fade_s": 2, "curve": "ease_in" } ] } },
  { "id": "starlight", "label": "Starlight", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#02040f", "hold_s": 2.5, "fade_s": 0 }, { "color": "#c8d8ff", "hold_s": 0.25, "fade_s": 0 },
    { "color": "#02040f", "hold_s": 1.8, "fade_s": 0 }, { "color": "#8aa8ff", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#02040f", "hold_s": 3, "fade_s": 0 } ] } },
  { "id": "fog", "label": "Fog", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#3a4450", "hold_s": 2.5, "fade_s": 3.5, "curve": "ease_in_out" },
    { "color": "#0a0e14", "hold_s": 2.5, "fade_s": 3.5, "curve": "ease_in_out" } ] } },
  { "id": "glacier", "label": "Glacier", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#0a2a3a", "hold_s": 3, "fade_s": 4, "curve": "ease_in_out" },
    { "color": "#7cd8ff", "hold_s": 1.5, "fade_s": 4, "curve": "ease_in_out" } ] } },
  { "id": "dusk-to-dawn", "label": "Dusk to Dawn", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#ff5500", "hold_s": 1.5, "fade_s": 2, "curve": "ease_in" },
    { "color": "#2a0a40", "hold_s": 2, "fade_s": 3.5, "curve": "ease_in_out" }, { "color": "#02030a", "hold_s": 3, "fade_s": 3, "curve": "ease_in" },
    { "color": "#4a3a6a", "hold_s": 1.5, "fade_s": 3, "curve": "ease_out" } ] } },
  { "id": "resting-heart", "label": "Resting Heart", "group": "Ambient", "sequence": { "repeat": true, "stops": [
    { "color": "#8a1e2a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#2a0008", "hold_s": 0.25, "fade_s": 0.2, "curve": "ease_out" },
    { "color": "#8a1e2a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#12000a", "hold_s": 1.4, "fade_s": 0.4, "curve": "ease_out" } ] } },

  { "id": "morse-ok", "label": "Morse OK", "group": "Patterns", "sequence": { "repeat": true, "stops": [
    { "color": "#00ff2a", "hold_s": 0.55, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#00ff2a", "hold_s": 0.55, "fade_s": 0 }, { "color": "#000000", "hold_s": 1.2, "fade_s": 0 } ] } },
  { "id": "triple-echo", "label": "Triple Echo", "group": "Patterns", "sequence": { "repeat": false, "stops": [
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#4a4a4a", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#2a2a2a", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffffff", "hold_s": 0.2, "fade_s": 0 }, { "color": "#0a0a0a", "hold_s": 1.2, "fade_s": 0 } ] } },
  { "id": "staircase", "label": "Staircase", "group": "Patterns", "sequence": { "repeat": false, "stops": [
    { "color": "#1a0a00", "hold_s": 0.4, "fade_s": 0 }, { "color": "#5a2a00", "hold_s": 0.4, "fade_s": 0 },
    { "color": "#a85a00", "hold_s": 0.4, "fade_s": 0 }, { "color": "#ff9a00", "hold_s": 0.4, "fade_s": 0 },
    { "color": "#ffd48a", "hold_s": 0.8, "fade_s": 0 } ] } },
  { "id": "double-blink-hold", "label": "Double Blink & Hold", "group": "Patterns", "sequence": { "repeat": false, "stops": [
    { "color": "#ffcc00", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffcc00", "hold_s": 0.2, "fade_s": 0 }, { "color": "#000000", "hold_s": 0.2, "fade_s": 0 },
    { "color": "#ffcc00", "hold_s": 1.6, "fade_s": 0 } ] } },
  { "id": "ramp-and-drop", "label": "Ramp & Drop", "group": "Patterns", "sequence": { "repeat": true, "stops": [
    { "color": "#0a1400", "hold_s": 0.3, "fade_s": 0 }, { "color": "#7cff00", "hold_s": 0.3, "fade_s": 1.6, "curve": "ease_in" },
    { "color": "#0a1400", "hold_s": 0.3, "fade_s": 0.25, "curve": "ease_in" } ] } },
  { "id": "swell-and-cut", "label": "Swell & Cut", "group": "Patterns", "sequence": { "repeat": true, "stops": [
    { "color": "#00ff9a", "hold_s": 0.25, "fade_s": 2.2, "curve": "ease_in" }, { "color": "#000000", "hold_s": 0.8, "fade_s": 0 } ] } },
  { "id": "wind-up", "label": "Wind Up", "group": "Patterns", "sequence": { "repeat": false, "stops": [
    { "color": "#2a2a00", "hold_s": 0.5, "fade_s": 0 }, { "color": "#8a8a00", "hold_s": 0.4, "fade_s": 0.5, "curve": "ease_in" },
    { "color": "#ffff00", "hold_s": 0.3, "fade_s": 0.4, "curve": "ease_in" },
    { "color": "#ffffff", "hold_s": 0.8, "fade_s": 0.3, "curve": "exponential" } ] } }
];

/** True if `preset` is a stop list rather than a device-rendered effect. */
export function presetIsSequence(preset) {
  return Boolean(preset && preset.sequence);
}

/** The look a preset drops in, whichever shape it is. Copied, never shared -
 *  a preset is a starting point and editing what you picked must not edit the
 *  library you picked it from. */
export function presetLook(preset) {
  const source = preset.sequence || preset.effect;
  return JSON.parse(JSON.stringify(source));
}

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
  // And the same trick one field over: a rainbow has no second hue either, so
  // `color2` carries how *saturated* the cycle is. Low is a wash of white with
  // a hint of hue in it; 100% is the full-strength rainbow this style has
  // always been.
  { key: 'color2', shows: 'saturation', label: 'Colour strength', kind: 'level',
    hint: 'Lower washes the whole cycle towards white; higher makes the hues '
      + 'the loudest thing about it.' },
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
    const drive = DRIVES.find((d) => d.value === (effect.drive || 'clock'));
    // The drive is named before the repeat, because it changes what "looping"
    // *means* - wrapping across a run is a different thing from replaying on
    // a clock, and a summary that omitted it would read identically for both.
    const by = drive && drive.value !== 'clock' ? `by ${drive.label.toLowerCase()}, ` : '';
    return `Sequence, ${n} stop${n === 1 ? '' : 's'}, ${by}`
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
        describe: (v) => `Floor: ${v.toFixed(2)}s (${(1 / v).toFixed(1)} flashes/sec)`,
        hint: 'Floor for flash + alternate. 0.33s = 3/sec, the photosensitivity '
          + 'limit. Faster is allowed - and a seizure risk.' },
    ],
  },
  {
    title: 'Web server',
    // Zero links to /api/ anywhere in the UI meant the REST API a script or a
    // Shortcut needs was undiscoverable except by reading webui.py (TODO 64).
    // Always shown, not tinker-gated - a developer looking for this is not
    // the audience "hidden until asked" protects.
    note: 'Everything this page can do is also a REST API at /api/ - webhooks, '
      + 'MIDI, scripts and Shortcuts all drive the button through it. The '
      + 'endpoint list is the docstring at the top of webui.py.',
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
