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

// The fire-and-forget primitives, and therefore what a *step* of a sequence
// may be - deliberately not a sequence, which is where "no nesting" stops
// being a promise and becomes a fact about the data (config.py's
// SEQUENCE_ACTIONS). The three that are missing from all of this - enter_mode,
// readout and standby - each change what the mode *loop* does next, and none
// of these run inside the loop. test_schema_mirror.py fails on drift.
export const SEQUENCE_ACTIONS = [
  'log', 'timer_toggle', 'webhook', 'osc', 'artnet', 'midi', 'keys', 'set_value',
  'load_theme',
];

// What a sequence may *end* with, and only end with (TODO 117). A readout owns
// the light for as long as it counts, and `set_led` cancels a running sequence
// on every call - so a step after one would cut it off mid-digit. "Last only"
// is a fact about the light rather than a nicety, which is why `standby` and
// `enter_mode` are not here and will not be. Mirrors SEQUENCE_TAIL_ACTIONS in
// config.py; test_schema_mirror.py fails on drift.
export const SEQUENCE_TAIL_ACTIONS = ['readout'];

// What `set_value` may do to a slot: a delta and an absolute, and nothing
// else. Anything more is arithmetic, which belongs to the app runtime's
// expression language rather than to an action. Mirrors SET_VALUE_OPS in
// config.py; test_documents.py fails on drift.
export const SET_VALUE_OPS = ['add', 'set'];

// The two edges of a sequence, mirrored from config.py so the editor stops you
// at the same place the parser would - a limit the UI enforces and the parser
// does not is a limit that a hand-edited file walks straight past, and one the
// parser enforces and the UI does not is a save that silently loses steps.
export const MAX_SEQUENCE_STEPS = 8;
export const MAX_SEQUENCE_S = 10;

// A hook may do several things in order (TODO 33), which is the one addition
// to the fire-and-forget set: a sequence *is* fire-and-forget, it just takes
// longer. Mirrors HOOK_ACTIONS in config.py.
export const HOOK_ACTIONS = [...SEQUENCE_ACTIONS, 'sequence'];

// Which actions a reflex may run: the hook set plus `enter_mode`. Mirrors
// REFLEX_ACTIONS in config.py, where the one difference is explained - a hook
// fires beside the run loop, a reflex is dispatched by it, so starting an app
// is exactly what a reflex is for. test_schema_mirror.py fails on drift.
export const REFLEX_ACTIONS = [...HOOK_ACTIONS, 'enter_mode', 'set_position'];

// Which actions may be named in the action pool: the hook set only. The three
// missing from here — `enter_mode`, `readout`, and `standby` — each change
// what the mode *loop* does next, and that is ambient-only state that does not
// belong in a shared library of "do this and hand the button back". An action
// in the pool must be truly fire-and-forget (primitives or sequences), because
// it may be dispatched from any context — a gesture, a hook, a reflex — and
// any of the loop-changing actions would break one or more of those paths.
export const POOL_ACTIONS = HOOK_ACTIONS;

// Where a reflex can hear from, besides its own address (TODO 73, 99). A
// descriptor table rather than a branch per source in the panel: adding one is
// an entry here plus its parser in config.py, which is the same open/closed
// shape ACTIONS and TEMPLATES follow.
//
// **A source never removes the endpoint.** Every reflex is always firable by
// POSTing to its own URL, so a MIDI or a polled reflex is still testable with
// curl - which is why the "no source" option reads as its address *only*
// rather than as nothing at all.
//
// **A source builds a payload and stops there.** None of these adds an
// operator, a consequence or a second condition; what arrives is judged by the
// same one-field `when` test (REFLEX_OPS below), which is the property that
// keeps all of this evaluable on the device one day.
//
// `keys` mirror REFLEX_SOURCES in config.py and `readers` mirror READERS in
// poll.py; test_url_reflex.py fails on drift.
export const REFLEX_SOURCES = [
  {
    key: 'midi', label: 'a MIDI message', tier: 'tinker',
    hint: 'A note or a control change arriving on a MIDI input - how a DAW '
      + 'tells the button it started recording. The message becomes the '
      + 'payload, so “note 95 at velocity 127” is this source plus a test on '
      + 'velocity, and the same note at 0 is the opposite test.',
  },
  {
    key: 'url', label: 'a URL, checked on a clock', tier: 'tinker',
    hint: 'The button goes and looks: it fetches this address every so often '
      + 'and hands what comes back to the test below. Paste the secret '
      + 'calendar link Google, Outlook or iCloud gives you and read it as a '
      + 'calendar - no sign-in, no app to authorise. A server that is down '
      + 'fires nothing, backs off, and says so once rather than every minute.',
    // Only what needs no credential, and that is a decision rather than a
    // stage (TODO 100): a token would have to live in config.json, which the
    // API serves in full and git now tracks. Authenticated polling waits for
    // the secret store (TODO 96a).
    noCredentials: true,
    defaults: { every_minutes: 15, read: 'json' },
    readers: [
      { key: 'json', label: 'JSON', hint: 'The object that comes back is the '
        + 'payload, so a field of it is what the test reads. A bare list '
        + 'becomes {"count": n}.' },
      { key: 'ics', label: 'a calendar (.ics)', hint: 'Becomes “minutes” - how '
        + 'long until the next event starts - plus “events”, how many are '
        + 'still ahead. With no next event “minutes” is absent, and a missing '
        + 'field never fires, so an empty calendar is simply quiet. Repeating '
        + 'events are counted as “recurring” and skipped: reading a repeat '
        + 'rule properly is a calendar library, so this says so rather than '
        + 'pretending they are not there.' },
    ],
  },
];

// The operators a reflex's test may use - one field, one operator, one number,
// and this is the whole list (TODO 72). Mirrors REFLEX_OPS in config.py;
// test_schema_mirror.py fails on drift. Grown into an expression language it
// would stop being evaluable on the device, which is the one thing it must
// stay (ROADMAP D2).
export const REFLEX_OPS = ['<', '<=', '>', '>=', '==', '!='];

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
  'notice', 'stopwatch', 'counter', 'pomodoro', 'metronome', 'countdown',
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

// The shipped colour themes (TODO 95) - a coordinated set of colours for the
// whole button, chosen with one pointer (`active_theme`) instead of eleven
// states one at a time.
//
// **Mirrored in config.py as BUILTIN_THEMES**, because both sides need them:
// the offline editor has no server to ask, and the service has to resolve
// `active_theme: "ember"` on a config that has never been opened in an editor.
// test_themes.py compares the two literally and fails on drift.
//
// **Palette-only, deliberately.** A theme may also carry `looks` and
// `state_looks` (see `Theme` in config.py), but every theme here re-colours the
// palette alone - and a palette entry is the one form that ships to the device
// and renders with **no host attached** (CLAUDE.md: "a stop list is the rich
// form; a palette entry is the fallback form"). A themed button stays themed
// when the PC is off, which is the direction the whole product is travelling.
//
// Each one exists for a different *reason*, which is the point - four palettes
// with no argument behind them would be a colour picker with extra steps:
//   - **Signal** carries a distinct *motion* per state as well as a distinct
//     hue, so red/green - the pair a colourblind reader cannot separate - is
//     told apart by held-versus-blinking. Hue never carries the load alone.
//   - **Ember** puts every state on the black-body curve. It is also the
//     format's stress test: with one hue family, level and motion are all that
//     is left to distinguish states, which is why a theme entry is a whole
//     `LedEffect` (style, both colours, period) rather than a colour. THINKING
//     defaults to `rainbow` - by definition every hue - so a theme that could
//     only set colours could not put that state on the curve at all.
//   - **Nocturne** is the 3 AM nightstand: nothing above a whisper, and the
//     only strobe in it is near-black. A theme is allowed to be quieter than
//     the flash floor requires - the floor is a floor, not a target.
//   - **Studio** speaks transport: record red, play green, stop amber, a hard
//     white metronome tick, and an idle that disappears against a monitor.
//     Everything else is desaturated **so that red means record**.
//
// A fifth theme legible on the 3V3 ring's colour cast waits on TODO 0c's
// bench sitting - authoring it now would be inventing numbers.
//
// Strict JSON, exactly like LOOK_PRESETS and for the same reason: test_themes.py
// slices this array out and feeds every entry through the real Python parser, so
// a theme cannot ship a colour the config would reject or a rate the flash floor
// would rewrite. Keep comments outside the brackets.
export const THEMES = [
  { "id": "signal", "label": "Signal", "about": "Maximum separation - a different hue and a different motion for every state. The one to pick if colour alone is hard to read.",
    "palette": {
      "IDLE": { "style": "breathe", "color": "#0000ff", "color2": "#000000", "period_s": 3 },
      "LISTENING": { "style": "solid", "color": "#ffff00", "color2": "#000000", "period_s": 1 },
      "THINKING": { "style": "rainbow", "color": "#ffffff", "color2": "#000000", "period_s": 0.8 },
      "SUCCESS": { "style": "solid", "color": "#00ff00", "color2": "#000000", "period_s": 1 },
      "ERROR": { "style": "flash", "color": "#ff0000", "color2": "#000000", "period_s": 0.45 },
      "ALERT": { "style": "alternate", "color": "#ff0000", "color2": "#ffffff", "period_s": 0.45 },
      "TIMING": { "style": "breathe", "color": "#00ffff", "color2": "#000000", "period_s": 1.6 },
      "COUNTING": { "style": "flash", "color": "#ff00ff", "color2": "#000000", "period_s": 0.7 },
      "WORKING": { "style": "solid", "color": "#ff5500", "color2": "#000000", "period_s": 1 },
      "RESTING": { "style": "breathe", "color": "#00ff88", "color2": "#000000", "period_s": 4 },
      "METRONOME": { "style": "flash", "color": "#ffffff", "color2": "#000000", "period_s": 0.5 }
    } },
  { "id": "ember", "label": "Ember", "about": "Everything on the black-body curve - deep amber at rest, warm gold when it works, red-orange when it fails. A lamp rather than a gadget.",
    "palette": {
      "IDLE": { "style": "breathe", "color": "#4a1200", "color2": "#000000", "period_s": 5 },
      "LISTENING": { "style": "solid", "color": "#ff8c26", "color2": "#000000", "period_s": 1 },
      "THINKING": { "style": "fade", "color": "#ff3800", "color2": "#ffc46b", "period_s": 1.2 },
      "SUCCESS": { "style": "solid", "color": "#ffd08a", "color2": "#000000", "period_s": 1 },
      "ERROR": { "style": "flash", "color": "#ff2000", "color2": "#000000", "period_s": 0.45 },
      "ALERT": { "style": "alternate", "color": "#ff3800", "color2": "#ffe4c4", "period_s": 0.45 },
      "TIMING": { "style": "breathe", "color": "#ff6a00", "color2": "#000000", "period_s": 2 },
      "COUNTING": { "style": "flash", "color": "#ffa030", "color2": "#000000", "period_s": 0.7 },
      "WORKING": { "style": "breathe", "color": "#ff5000", "color2": "#000000", "period_s": 6 },
      "RESTING": { "style": "breathe", "color": "#ffc46b", "color2": "#000000", "period_s": 6 },
      "METRONOME": { "style": "flash", "color": "#ffe4c4", "color2": "#000000", "period_s": 0.5 }
    } },
  { "id": "nocturne", "label": "Nocturne", "about": "Low, cool and slow. A near-black indigo breath at rest and an error dim enough to sleep through - a button on a nightstand at 3 AM should not be a torch.",
    "palette": {
      "IDLE": { "style": "breathe", "color": "#06001e", "color2": "#000000", "period_s": 6 },
      "LISTENING": { "style": "solid", "color": "#0e1836", "color2": "#000000", "period_s": 1 },
      "THINKING": { "style": "fade", "color": "#04001c", "color2": "#0a1840", "period_s": 3 },
      "SUCCESS": { "style": "solid", "color": "#00301a", "color2": "#000000", "period_s": 1 },
      "ERROR": { "style": "breathe", "color": "#3a0000", "color2": "#000000", "period_s": 1.5 },
      "ALERT": { "style": "breathe", "color": "#5a0008", "color2": "#000000", "period_s": 1.2 },
      "TIMING": { "style": "breathe", "color": "#001e2a", "color2": "#000000", "period_s": 3 },
      "COUNTING": { "style": "breathe", "color": "#1a0028", "color2": "#000000", "period_s": 3 },
      "WORKING": { "style": "breathe", "color": "#0c1428", "color2": "#000000", "period_s": 8 },
      "RESTING": { "style": "breathe", "color": "#021c14", "color2": "#000000", "period_s": 8 },
      "METRONOME": { "style": "flash", "color": "#14202e", "color2": "#000000", "period_s": 0.6 }
    } },
  { "id": "studio", "label": "Studio", "about": "Transport vocabulary - record red, play green, stop amber, a hard white tick. Desaturated everywhere else, so that red means record.",
    "palette": {
      "IDLE": { "style": "solid", "color": "#101820", "color2": "#000000", "period_s": 1 },
      "LISTENING": { "style": "solid", "color": "#7c8a99", "color2": "#000000", "period_s": 1 },
      "THINKING": { "style": "rainbow", "color": "#303030", "color2": "#909090", "period_s": 1.5 },
      "SUCCESS": { "style": "solid", "color": "#2fae5c", "color2": "#000000", "period_s": 1 },
      "ERROR": { "style": "flash", "color": "#e0641e", "color2": "#000000", "period_s": 0.45 },
      "ALERT": { "style": "flash", "color": "#ff0000", "color2": "#000000", "period_s": 0.45 },
      "TIMING": { "style": "breathe", "color": "#c88a2a", "color2": "#000000", "period_s": 2 },
      "COUNTING": { "style": "breathe", "color": "#4f7fa8", "color2": "#000000", "period_s": 2.5 },
      "WORKING": { "style": "breathe", "color": "#37718f", "color2": "#000000", "period_s": 6 },
      "RESTING": { "style": "solid", "color": "#43535f", "color2": "#000000", "period_s": 1 },
      "METRONOME": { "style": "flash", "color": "#ffffff", "color2": "#000000", "period_s": 0.5 }
    } }
];

export const THEME_BY_ID = Object.fromEntries(THEMES.map((t) => [t.id, t]));

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
    label: 'Show a number on the light',
    fields: [
      // Where the number comes from (TODO 118a). Mirrors `READOUT_SOURCES` in
      // config.py - same two values, same order; test_schema_mirror.py fails
      // on drift.
      //
      // **Nothing below is `required` any more, and that is this editor's one
      // missing mechanism rather than a relaxed rule.** Which field must be
      // filled now depends on this row - an event name, or an app and a slot -
      // and `required` is a static flag with no conditional form, exactly as
      // no field here hides behind another one. The parser still refuses a
      // readout with neither, so the binding reports itself as invalid on the
      // next load rather than being accepted as something it is not.
      { key: 'source', label: 'Which number', kind: 'select', required: true,
        rebuilds: true,
        options: [
          { value: 'event', label: 'How many times today' },
          { value: 'app', label: 'An app’s own number' },
        ],
        hint: 'Counting today’s presses of an event is what this has always '
          + 'done. An app’s own number is the value that app keeps - a tally '
          + 'that counts past midnight holds one, and this is how you see it '
          + 'without opening the app.' },
      // Same reading as `log`'s event field - a readout is a sibling of log,
      // not a mode of it: this one only reads count_today(event), it never
      // writes a row, so it can sit on a gesture that a `log` binding
      // elsewhere already feeds without double-counting anything.
      { key: 'event', label: 'Event name', kind: 'text',
        placeholder: 'coffee',
        hint: 'Used when the row above says “how many times today”. Blinks '
          + 'today’s count for this event. 0 is one dim blink, so a real zero '
          + 'reads differently from nothing happening.' },
      // The same pair `set_value` names, picked the same way - one spelling of
      // "an app's value" for the action that writes it and the one that reads
      // it, so a slot renamed in one place is not half-renamed in the other.
      { key: 'app', label: 'App', kind: 'select', rebuilds: true,
        options: (ctx) => (ctx.getModes ? ctx.getModes() : [])
          .filter((m) => m && TEMPLATE_BY_TYPE[m.template]?.docSlots?.length)
          .map((m) => ({ value: m.name, label: m.name })),
        hint: 'Only apps that keep a value of their own appear here. A tally '
          + 'keeps one once you switch on "Keep counting past midnight".' },
      { key: 'slot', label: 'Which value', kind: 'select',
        options: (ctx, obj) => {
          const mode = (ctx.getModes ? ctx.getModes() : [])
            .find((m) => m && m.name === (obj && obj.app));
          const slots = (mode && TEMPLATE_BY_TYPE[mode.template]?.docSlots) || [];
          return slots.map((s) => ({ value: s.name, label: s.name, hint: s.about }));
        },
        hint: 'Which of that app’s values to show.' },
      // TODO 91's compiler, the same four schemes a notice's hour chime
      // offers - and '' is the tens/units digits this action has always
      // blinked. Mirrors `readout.SCHEMES`.
      { key: 'scheme', label: 'How to read it out', kind: 'select',
        options: [
          { value: '', label: 'Tens then units - slow, then quick' },
          { value: 'hour_colors', label: 'A colour per value, that many flashes' },
          { value: 'place_value', label: 'Colour per digit, 1-9 flashes each' },
          { value: 'binary', label: 'Binary - two colours, one per bit' },
          { value: 'morse', label: 'Morse - the digits, spoken' },
        ],
        hint: 'The default stops at 99 - a number past that is clamped, and '
          + 'has been since this action existed. The other four have no '
          + 'ceiling, which is what a tally in the hundreds needs. Length is '
          + 'the trade: counting 99 out in flashes takes a while, where Morse '
          + 'and binary stay short however big the number gets.' },
      { key: 'colors', label: 'That scheme’s colours', kind: 'json',
        shape: 'list', tier: 'tinker',
        hint: 'JSON list of "#rrggbb", in the order the scheme uses them - '
          + 'one colour for Morse, two for binary (0 then 1), one per decimal '
          + 'place for "colour per digit" counting up from the ones, and a '
          + 'wheel of any length for "a colour per value". Empty = that '
          + 'scheme’s own colours. The two rows below are the tens/units '
          + 'default’s colours and are not used by any of the four.' },
      { key: 'tens_color', label: 'Tens colour', kind: 'color', tier: 'tinker',
        hint: 'The slow pulses - the coarse digit.' },
      { key: 'units_color', label: 'Units colour', kind: 'color', tier: 'tinker',
        hint: 'The quick pulses - the fine digit.' },
    ],
    defaults: () => ({
      action: 'readout', source: 'event', event: '', app: '', slot: 'count',
      scheme: '', colors: [],
      tens_color: '#ff8800', units_color: '#3399ff',
    }),
    describe: (a) => {
      const what = a.source === 'app'
        ? `${a.app || '…'}’s ${a.slot || '…'}`
        : `“${a.event || '…'}”`;
      return `Show ${what} on the light`;
    },
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
      { key: 'payload', label: 'Extra JSON payload', kind: 'json',
        shape: 'object', tier: 'tinker',
        hint: 'Optional - merged into the POST body (trigger/mode/ts added '
          + 'for you).' },
      // Declared here and nowhere else: every sub-editor that can hold an
      // action renders `fields`, so one descriptor entry puts this on a
      // gesture, a hook, a reflex, a pool entry and a sequence step at once.
      // It edits nothing - see the widget.
      { key: '__preview__', label: 'Check it', kind: 'webhookPreview',
        hint: 'Shows the exact body this would POST, including the keys an '
          + 'app adds when it finishes. "Send a test" really sends it.' },
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
      { key: 'args', label: 'Arguments', kind: 'json', shape: 'list',
        tier: 'tinker',
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
    type: 'artnet',
    label: 'Send Art-Net (DMX)',
    fields: [
      { key: 'host', label: 'Host', kind: 'text', required: true,
        placeholder: '2.0.0.1',
        hint: 'IP of the lighting desk or Art-Net node - a broadcast '
          + 'address (like 2.255.255.255) reaches every node on the net.' },
      { key: 'universe', label: 'Universe', kind: 'number', min: 0, max: 32767,
        step: 1,
        hint: 'The Art-Net universe (Net/Sub-Net/Universe, packed as one '
          + 'number) this packet addresses.' },
      { key: 'channels', label: 'Channel values', kind: 'json', shape: 'list',
        hint: 'JSON list, one number 0-255 per DMX channel, starting at '
          + 'channel 1. [255, 0, 128] sets channels 1-3 and leaves the rest '
          + 'of the universe untouched.' },
      { key: 'port', label: 'Port', kind: 'number', min: 1, max: 65535,
        step: 1, tier: 'tinker',
        hint: 'Almost always 6454, the standard Art-Net port - change it '
          + 'only if your node says otherwise.' },
    ],
    defaults: () => ({
      action: 'artnet', host: '2.0.0.1', port: 6454, universe: 0, channels: [255],
    }),
    // No delivery to report: Art-Net is UDP, exactly like osc above.
    describe: (a) => `Art-Net universe ${a.universe ?? 0} → ${a.host || '…'}:${a.port ?? 6454}`,
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
      // **Basic tier, not tinker** - this is the one field that decides
      // whether anything happens at all. Hidden, it produced five bindings
      // with no port, every note going to Microsoft GS Wavetable Synth (the
      // first output on a typical Windows machine) while the DAW sat waiting,
      // and no error anywhere because nothing had failed. A field that can
      // silently send your MIDI to the wrong place is not an advanced option.
      { key: 'port', label: 'MIDI port', kind: 'text', suggest: 'midi_out',
        placeholder: 'Button',
        hint: 'Partial name is enough - Windows appends a number that '
          + 'changes per session, so "Button" matches "Button 2". Windows '
          + 'needs loopMIDI to create the port. **Leave it blank and it takes '
          + 'the first output on this machine**, which is usually the built-in '
          + 'synth rather than your DAW.' },
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
      // Dynamic <select>: every takeover template `enter_takeover`'s own
      // isinstance chain (main.py) actually dispatches - which is not the
      // same set as `startedBy: 'gesture'` and used to be filtered on that
      // by mistake (TODO "Smaller, worth doing": the launcher already offers
      // Alarm as a manual target - `ring_notice` is the same function either
      // way it is entered - so excluding it here only made it reachable
      // through one more click). A gentle (non-`urgent`) notice used to be
      // excluded too - `ReminderBehavior` had no `enter_takeover` branch at
      // all - but TODO 84 merged it into the same `NoticeBehavior` class
      // `ring_notice` handles either way, so every notice is a valid target
      // now. The widget calls this with a context object whose `getModes()`
      // returns the sibling modes (injected by menu.js -> modeEditor ->
      // createField), so the picker stays in sync as modes are added/renamed
      // without this module knowing where the list lives (Dependency
      // Inversion).
      { key: 'target', label: 'App to launch', kind: 'modeSelect', required: true,
        hint: 'Which app this opens.',
        options: (ctx) => {
          const modes = (ctx && typeof ctx.getModes === 'function') ? ctx.getModes() : [];
          return (Array.isArray(modes) ? modes : [])
            .filter((m) => m && TAKEOVER_TEMPLATES.has(m.template)
              && typeof m.name === 'string' && m.name)
            .map((m) => ({ value: m.name, label: m.name }));
        } },
    ],
    defaults: () => ({ action: 'enter_mode', target: '' }),
    describe: (a) => `Launch “${a.target || '…'}”`,
  },
  {
    type: 'sequence',
    label: 'Do several things in order',
    // The action that made item 25 buildable: Mackie has no return-to-zero, so
    // "stop and rewind" is Stop, a beat, Stop - two messages one gesture has to
    // send. It is also how a control surface sends a *press and a release*,
    // which is what a DAW expecting a button rather than a trigger wants.
    fields: [
      { key: 'steps', label: 'Steps', kind: 'steps', required: true,
        hint: 'Run in order, and the button is held until the last one is '
          + 'done - so presses made during it are dropped, exactly as they '
          + 'are during any other action. Each step can wait before it runs.' },
    ],
    defaults: () => ({ action: 'sequence', steps: [] }),
    describe: (a) => {
      const steps = Array.isArray(a.steps) ? a.steps : [];
      if (!steps.length) return 'Nothing yet';
      const shown = steps.slice(0, 3).map((step) => describeAction(step));
      return shown.join(' → ') + (steps.length > 3 ? ` → +${steps.length - 3}` : '');
    },
  },
  {
    type: 'set_value',
    label: "Change an app's number",
    // The third action family (ROADMAP 3d): **app-bound**. It names an app and
    // writes one of that app's declared values, which is what makes "Smoking
    // +1" bindable to a gesture in Home without entering the Counter
    // (TODO 15/34). Offered everywhere an ordinary primitive is - it changes
    // no loop and owns no light - which is why it is not `appOnly`: unlike a
    // position, a document lives outside every run loop precisely so anything
    // can write it.
    fields: [
      { key: 'app', label: 'App', kind: 'select', required: true, rebuilds: true,
        options: (ctx) => (ctx.getModes ? ctx.getModes() : [])
          .filter((m) => m && TEMPLATE_BY_TYPE[m.template]?.docSlots?.length)
          .map((m) => ({ value: m.name, label: m.name })),
        hint: 'Only apps that keep a value of their own appear here. A '
          + 'counter keeps one once you switch on "Keep counting past '
          + 'midnight".' },
      { key: 'slot', label: 'Which value', kind: 'select', required: true,
        // Depends on the app above, so it is a function of the live model
        // rather than a fixed list - the same trick the mode pickers use.
        options: (ctx, obj) => {
          const mode = (ctx.getModes ? ctx.getModes() : [])
            .find((m) => m && m.name === (obj && obj.app));
          const slots = (mode && TEMPLATE_BY_TYPE[mode.template]?.docSlots) || [];
          return slots.map((s) => ({ value: s.name, label: s.name, hint: s.about }));
        },
        hint: 'Which of that app’s values to write.' },
      { key: 'op', label: 'How', kind: 'select', required: true,
        options: [
          { value: 'add', label: 'Add to it' },
          { value: 'set', label: 'Set it to' },
        ],
        hint: '"Add to it" is the everyday one - a tally you press up from '
          + 'anywhere. "Set it to" is how you reset it to zero.' },
      { key: 'value', label: 'Amount', kind: 'number', step: 1,
        hint: 'Added, or written, depending on the row above. Negative '
          + 'counts down.' },
    ],
    defaults: () => ({ action: 'set_value', app: '', slot: 'count', op: 'add', value: 1 }),
    describe: (a) => {
      const where = `${a.app || '…'}’s ${a.slot || '…'}`;
      if (a.op === 'set') return `Set ${where} to ${a.value ?? 0}`;
      const amount = Number(a.value ?? 1);
      return `${where} ${amount < 0 ? '' : '+'}${amount}`;
    },
  },
  {
    type: 'set_position',
    label: 'Put an app on a position',
    // **appOnly**: never offered to a gesture. A gesture is answered at the
    // ambient layer, where no app is running to have a position - so the
    // control that offers this is a reflex's, and a reflex reaches a running
    // app only by naming it in "Only while" (TODO 74).
    appOnly: true,
    fields: [
      // A free name rather than a picker: the positions belong to whichever
      // app is running when this arrives, which is a thing only the config's
      // "Only while" says and only at runtime. A name that matches nothing is
      // reported by the app rather than guessed at.
      { key: 'name', label: 'Position', kind: 'text', required: true,
        placeholder: 'Recording',
        hint: 'One of the positions of the app named in "Only while" - a '
          + 'signal light’s states, or a control surface’s positions. '
          + 'The app shows it; it does not send that position’s own '
          + 'message, because something out there just told us this is where '
          + 'we are.' },
    ],
    defaults: () => ({ action: 'set_position', name: '' }),
    describe: (a) => `Show position “${a.name || '…'}”`,
  },
  {
    type: 'load_theme',
    label: 'Load a colour theme',
    // Offered everywhere an ordinary primitive is, and not `appOnly`, for the
    // reason `set_value` is not: it changes no loop and owns no light of its
    // own - it moves one pointer in the live config and the palette push the
    // service already makes carries the change to the button. The case that
    // earns the reach is a reflex: *at sunset, load Nocturne* (TODO 95).
    fields: [
      { key: 'theme', label: 'Theme', kind: 'select', required: false,
        // The config's own themes first, then the shipped ones - a theme saved
        // under a built-in id shadows it, exactly as a named look shadows a
        // preset of the same name.
        options: (ctx) => {
          const own = (ctx && typeof ctx.getThemes === 'function') ? ctx.getThemes() : {};
          const ids = new Set(Object.keys(own || {}));
          return [
            { value: '', label: 'Your own colours', hint: 'Puts the button back on the colours the config file itself carries.' },
            ...Object.entries(own || {}).map(([id, t]) => ({
              value: id, label: (t && t.name) || id, hint: (t && t.about) || '',
            })),
            ...THEMES.filter((t) => !ids.has(t.id))
              .map((t) => ({ value: t.id, label: t.label, hint: t.about })),
          ];
        },
        hint: 'Re-colours the whole button at once. Not saved - a theme a '
          + 'gesture or a reaction loads lasts until the config is reloaded, '
          + 'the same way sleeping does. Pick one on the Lights tab and Save '
          + 'to make it the one the button starts on.' },
    ],
    defaults: () => ({ action: 'load_theme', theme: '' }),
    describe: (a) => (a.theme
      ? `Load theme “${THEME_BY_ID[a.theme]?.label || a.theme}”`
      : 'Back to your own colours'),
  },
  {
    type: 'standby',
    label: 'Sleep / wake the button',
    // No fields, and that is the whole design: which way it goes is session
    // state the running service holds, not a setting, so there is nothing
    // here to configure. Bind it to the five-tap and you have an off switch.
    fields: [],
    defaults: () => ({ action: 'standby' }),
    describe: () => 'Sleep or wake the menus',
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
    // at HH:MM + days editor, plus TODO 106's two: `every` (a repeat within
    // the day) and `between` (which stretch of it). Both optional, and
    // deliberately absent from `defaults()` - a schedule that has never heard
    // of them must keep meaning exactly "once a day at `at`", in the file as
    // well as in the parser.
    custom: true,
    // Mirrors `config.SCHEDULE_REPEATS`. Value '' is "once a day", which is
    // how the absent key is spelled in a select that has no empty state.
    repeats: [
      { value: '', label: 'Once, at that time' },
      { value: 'hour', label: 'Every hour, at that minute past' },
    ],
    defaults: () => ({ type: 'schedule', at: '07:00' }),
    describe: (a) => {
      const days = fmtDays(a.days);
      const window = Array.isArray(a.between) && a.between[0] && a.between[1]
        ? ` between ${a.between[0]} and ${a.between[1]}` : '';
      // The hour in `at` is unused when it repeats hourly (config.py warns
      // about it), so the summary must not print it - a row reading "at 08:30
      // every hour" is the exact misreading that warning exists to catch.
      const when = a.every === 'hour'
        ? `every hour at :${String(a.at || '--:--').slice(-2)}`
        : `at ${a.at || '--:--'}`;
      return `${when}${window}${days ? ` ${days}` : ''}`;
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
// `describe(mode)` returns **what distinguishes this item from its siblings**
// - not what the template is (TODO 101). The nav already says "Stopwatch" as a
// heading, so a row reading "Stopwatch ..." spent its only line saying the one
// thing the reader had just been told. Callers that need the kind as well
// prefix `label` themselves; there is still exactly one description per mode.
//
// Takeover templates also carry the two things a user needs in order not to
// feel trapped, as data rather than as branches in the editor:
//   startedBy  'gesture' (a menu's Launch an app) | 'schedule'
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

// Which end of an app's numbers is the good end, when the *item* knows and the
// template cannot (TODO 109). Mirrors `config.MODE_BETTER`;
// test_schema_mirror.py fails on drift.
export const MODE_BETTER = ['low', 'high'];

// Offered by the three templates whose `readout.better` is null because it is
// a guess about the person rather than a fact about the app - a stopwatch, a
// countdown and a metronome. The blank option is the default and says what it
// does rather than "none": absent is not a missing answer here, it is the
// answer most of these apps want.
//
// Two options, not three. There is no "neither" because no template offering
// this field has an opinion to override; the day one does, that is when the
// word is worth adding on both sides.
const BETTER_FIELD = {
  key: 'better', label: 'Is one of these best?', kind: 'select', tier: 'tinker',
  options: [
    { value: '', label: 'No - just list them' },
    { value: 'low', label: 'Yes - lower is better' },
    { value: 'high', label: 'Yes - higher is better' },
  ],
  hint: 'A mile run has a best time; a loaf of bread does not. Say so and '
    + 'this app’s history crowns one and colours each change good or bad - '
    + 'press Refresh on it to redraw.',
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
 * about the person using it - and where it is a guess, `BETTER_FIELD` lets the
 * *item* answer it (TODO 109), which is the only level that can. Read it
 * through `betterFor`, never off the descriptor, or the override is silently
 * ignored on whichever page forgot.
 */
export const READOUT_MEASURES = ['duration', 'value', 'tally', 'outcome'];

/**
 * A tally's gestures that count, as `[gestureKey, step]` pairs (TODO 118c).
 *
 * **Written the way `_parse_counter_body` reads it**, which is the only reason
 * it is a function rather than a filter written inline: a tally saved before
 * steps existed carries none of these keys at all, and the parser reads that
 * as the short-press/double-tap pair it has always meant. The served editor is
 * seeded from the *parsed* config so it never sees one, but the offline editor
 * reads a file straight off disk - and a page that called a working config
 * empty would be the "confidently wrong classification" INVARIANTS.md's nav
 * rule is about.
 */
export function counterSteps(mode) {
  const keys = GESTURES.filter((g) => g.key !== 'long_press').map((g) => g.key);
  const written = keys.filter((key) => mode && mode[key] !== undefined);
  const source = written.length ? written : ['short_press', 'double_tap'];
  return source
    .map((key) => [key, Number(written.length ? mode[key] : 1)])
    .filter(([, step]) => Number.isFinite(step) && step !== 0);
}

/**
 * The shortcuts an app *contributes* to the rest of the button (TODO 118b).
 *
 * **The phone-app model, and it costs no new action type.** Installing an app
 * on a phone puts its shortcuts in your reach as well as its own screen; a
 * template's `actions` key is that list, and every entry is a **pre-filled
 * instance of an action the button already has** - a `set_value` that already
 * knows the app and the slot, an `enter_mode` that already names the app.
 * Nothing here is a new `type` in ACTIONS, nothing here reaches config.json,
 * and picking one copies the body into the binding exactly as a look preset
 * copies a look. That is the whole mechanism: a table, not a branch.
 *
 * It is `docSlots`' neighbour on purpose. That key declares the durable values
 * an app keeps and this one declares the shortcuts it offers, and both are the
 * manifest a package will carry once apps ship as packages - which is why the
 * shape is data an app author could write rather than code the editor runs.
 *
 * A template's `actions` is **a function of the mode**, because what an app
 * offers depends on how it is configured: a control surface contributes one
 * shortcut per position it actually has, and a tally that keeps a running
 * total contributes a different "count up" from one that starts again each
 * day.
 *
 *   actions: (mode) => [
 *     { id: 'count_up',              // stable within the template; never stored
 *       label: 'count up',           // shown under the app's own name
 *       about: 'One press, +1.',     // optional, the option's hint
 *       body: { action: 'set_value', app: mode.name, slot: 'count', … } },
 *   ]
 *
 * @param {object[]} modes - the sibling modes, from the live model.
 * @param {?string[]} allowed - the action types this *binding* accepts
 *   (POOL_ACTIONS, HOOK_ACTIONS, REFLEX_ACTIONS, a template's own list), or
 *   null for "anything a gesture may hold". **Derived, never widened**: a
 *   contributed action is offered exactly where its underlying action already
 *   is, which is how a control surface's `set_position` shortcuts appear on a
 *   reaction and on nothing else without a word being written about it here.
 */
export function contributedActions(modes, allowed = null) {
  const found = [];
  for (const mode of Array.isArray(modes) ? modes : []) {
    if (!mode || !mode.name) continue;
    const declare = TEMPLATE_BY_TYPE[mode.template]?.actions;
    if (typeof declare !== 'function') continue;
    let offered;
    // A descriptor is data an app author wrote, and one that throws must cost
    // that app its shortcuts rather than the picker its contents.
    try { offered = declare(mode); } catch { continue; }
    for (const shortcut of Array.isArray(offered) ? offered : []) {
      const body = shortcut && shortcut.body;
      const descriptor = body && ACTION_BY_TYPE[body.action];
      if (!descriptor) continue;
      // Two filters, and they are the same rule twice: an action this binding
      // will not accept, and one no gesture may hold (`appOnly`), are both
      // things the parser would drop. Offering either would make a shortcut
      // that vanishes on Save.
      if (allowed ? !allowed.includes(body.action) : descriptor.appOnly) continue;
      found.push({
        app: mode.name,
        id: `${mode.template}:${shortcut.id}`,
        label: shortcut.label || shortcut.id,
        about: shortcut.about || '',
        body,
      });
    }
  }
  return found;
}

export const TEMPLATES = [
  {
    type: 'actions',
    ledStates: [],
    label: 'Actions',
    about: 'One action per gesture, answered without taking the button over.',
    nature: 'ambient',
    allowedActivations: ['always', 'window'],
    body: 'actions', // gesture×ACTIONS sub-editor + unless_logged_today
    // Five, not six, exactly like a control surface - and mirroring
    // `_parse_actions_body`, which drops a long press with a warning (TODO
    // 104). An everyday map is the level with nothing above it, so "up one
    // level" here means off, and the gesture belongs to sleep.
    gestures: ['short_press', 'double_tap', 'triple_tap', 'tap_4', 'tap_5'],
    gesturesNote: 'Long press puts the button to sleep, and wakes it again. '
      + 'That is why it is not in this list: it is the one gesture that means '
      + 'the same thing everywhere.',
    // A filled-in event name so a freshly added mode is valid by construction -
    // it parses, round-trips, and won't be dropped as an empty actions mode.
    defaults: () => ({
      short_press: { action: 'log', event: 'button_press' },
    }),
    describe: (mode) => {
      const parts = [];
      for (const g of GESTURES) {
        if (g.key === 'long_press') continue;  // sleep, not a binding
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
    // TODO 84: one template behind Alarm, Reminder and Dead man's switch,
    // which used to be two templates (`alarm`, `reminders`) plus a preset.
    // Both old template names still parse (config.py's `_parse_notice_body`
    // migrates them), so this descriptor is what a *saved* mode looks like
    // afterward, not a new kind of thing.
    type: 'notice',
    ledStates: ['ALERT'],
    label: 'Notice',
    about: 'The light goes off at a scheduled time, until cleared, snoozed, or missed.',
    nature: 'takeover',
    allowedActivations: ['schedule'],
    body: 'fields',
    fields: [
      { key: 'message', label: 'Message', kind: 'text',
        hint: "Shown while it's up." },
      { key: 'label', label: 'Short label', kind: 'text', tier: 'tinker',
        hint: 'Optional - name for status line / Bluetooth.' },
      // Required, and unconditional (TODO 84): every clear logs 1 and every
      // miss logs 0 under this name, with no separate opt-in field to
      // remember - the same convention every other template's own log name
      // already follows (Stopwatch's "Timer name" and its `required: true`).
      { key: 'log_as', label: 'Log as', kind: 'text', required: true,
        placeholder: 'notice',
        hint: 'Every clear logs 1 and every miss logs 0 under this name - '
          + 'that’s what "answered 6 of the last 7" reads.' },
      // The one setting the two old templates never shared a name for.
      // Independent of "give up after": an old reminder set to wait forever
      // still breathes gently forever, it does not start ringing just
      // because persistence now reads the same as an alarm's.
      { key: 'urgent', label: 'Urgent', kind: 'checkbox',
        hint: 'On: loops a tone and hard-flashes until cleared - a wake-up '
          + 'call. Off: chimes at most once and breathes gently - a nudge '
          + 'you can miss.' },
      { key: 'chime', label: 'Make a sound', kind: 'checkbox',
        hint: 'Off = light only, no sound at all.' },
      // TODO 105, and it is one ordered choice rather than a pair of
      // checkboxes on purpose: each option is strictly weaker than the one
      // above it, so of the sixteen combinations two boxes would offer,
      // twelve mean nothing. Mirrors `config.INTERRUPT_TIERS` - same four
      // values, same order, most permissive first.
      //
      // Deliberately not folded into Urgent: that one is *how loud*, this one
      // is *whether it may speak at all*, and a gentle chime that must still
      // pierce sleep is Urgent off with this set to Always.
      { key: 'interrupts', label: 'How far it may interrupt', kind: 'select',
        options: [
          { value: 'always', label: 'Always - even wakes a sleeping button' },
          { value: 'while_awake', label: 'While awake - but never wakes it' },
          { value: 'when_free', label: 'When free - waits for any app to finish' },
          { value: 'never', label: 'Never - no light, no sound' },
        ],
        hint: 'One that may not show yet waits, and "Give up after" below '
          + 'decides when waiting becomes a miss. Never shows nothing at all: '
          + 'it goes straight to the miss, which is how you get a scheduled '
          + 'webhook with no light - bind it under "If nobody answers".' },
      // The dead man's switch (TODO 44), generalised: basic tier, not
      // tinker, because someone who wants this is looking for it, and
      // burying the thing a preset is named after would be a joke at their
      // expense.
      { key: 'timeout_minutes', label: 'Give up after (minutes)', kind: 'number',
        min: 0, step: 1,
        hint: 'Minutes to wait before giving up on its own. 0 = waits until '
          + 'cleared, which is an ordinary alarm.' },
      { key: 'snooze_minutes', label: 'Snooze minutes', kind: 'number', min: 0, step: 1,
        hint: 'Long press snoozes this long instead of clearing. 0 = no snooze.' },
      // TODO 106's hour chime. Mirrors `readout.SCHEMES` - same four values,
      // same order - and '' is "off", the ordinary ring.
      //
      // **The hint carries the cost, because the cost is the decision.** Every
      // number below is measured (tests/test_hour_chime.py pins them), and the
      // spread is the whole reason there are four schemes rather than the one
      // the original sketch asked for: counting to twelve on a single pixel is
      // slow, and two of these do not count to twelve at all. Someone choosing
      // "a colour per hour" should learn what midday costs here, not on the
      // first day they leave it running.
      { key: 'readout_scheme', label: 'Say the hour', kind: 'select',
        options: [
          { value: '', label: 'No - just ring or flash' },
          { value: 'hour_colors', label: 'A colour per hour, 1-12 flashes' },
          { value: 'place_value', label: 'Colour per digit, 1-9 flashes each' },
          { value: 'binary', label: 'Binary - two colours, one per bit' },
          { value: 'morse', label: 'Morse - the digits, spoken' },
        ],
        hint: 'Turns this from an alarm into a chime: it washes up to white, '
          + 'counts the hour, and fades back to whatever the light was doing. '
          + 'How long that takes depends entirely on this row. Counting the '
          + 'hour at noon takes about 6.0s as colours, 7.0s in Morse, 1.7s by '
          + 'digit and 1.8s in binary - and the two fades below are on top of '
          + 'all four, so the honest totals at midday are roughly 26s, 27s, '
          + '22s and 22s. Twelve flashes is a long time for a light on a desk; '
          + 'noon in binary is four symbols. (Worst case is not always noon: '
          + '“colour per digit” peaks at nine o’clock, 4.5s.)' },
      // Always shown rather than revealed by the row above: nothing in this
      // editor hides a field behind another one today, and inventing that
      // mechanism for one number would be a widget change, not a schema one.
      { key: 'readout_fade_s', label: 'Fade in and out (seconds)', kind: 'number',
        min: 0, step: 1,
        hint: 'Only used when the row above says the hour. Each way, so this '
          + 'is counted twice. 10 is the slow swell a '
          + 'church bell wants; 2 makes the whole chime brief enough to catch '
          + 'out of the corner of your eye. 0 cuts straight to white.' },
    ],
    bindings: [
      { key: 'on_cleared', label: 'When cleared', actions: HOOK_ACTIONS,
        hint: 'Runs in addition to the automatic log, whenever this is cleared.' },
      { key: 'on_snoozed', label: 'When snoozed', actions: HOOK_ACTIONS,
        hint: 'Runs whenever long press snoozes it.' },
      { key: 'on_missed', label: 'If nobody answers', actions: HOOK_ACTIONS,
        hint: 'Runs when it goes unanswered for the full timeout - or, if it '
          + 'was never allowed to show at all, straight away. It needs this PC '
          + 'awake and connected - if the service stops or Bluetooth drops it '
          + 'cannot fire, so treat it as a nudge rather than a safety device.' },
    ],
    // `outcome`, not `value`, and that is the whole reason the measure
    // exists: a clear logs 1 and a miss logs 0 under the same name, so the
    // honest readout is "answered 6 of the last 7" and the dishonest one is
    // an average. Unconditional now (TODO 84) - every notice has a `log_as`.
    readout: {
      kind: 'log', nameField: 'log_as', measure: 'outcome',
      noun: 'ring', better: null,
      states: { 1: 'answered', 0: 'no answer' },
    },
    // **Snooze and arm are not here, and could not be.** Both are commands to
    // a *running* notice, and the only action that reaches a running app is
    // `set_position`, which addresses a signal light's or a control surface's
    // positions. Adding "snooze" would mean adding a primitive, which is the
    // one thing 118b is not for - so this contributes the shortcut that is
    // already expressible: ring it now, which is how you test one.
    actions: (mode) => [
      {
        id: 'ring',
        label: 'ring it now',
        about: 'Sets it off immediately, without waiting for its time - which '
          + 'is how you check what it looks and sounds like.',
        body: { action: 'enter_mode', target: mode.name },
      },
    ],
    // `when_free` and not the first entry, mirroring `config.DEFAULT_INTERRUPTS`
    // and for the reason written there: a new notice defaulting to Always
    // would make sleep meaningless within a week.
    // `readout_scheme: ''` is "off" - a new notice is an alarm, not a chime.
    // The fade carries its default here so the number field is never born
    // empty; it is inert until a scheme is chosen.
    defaults: () => ({
      message: '', label: '', log_as: 'notice', urgent: true, chime: true,
      timeout_minutes: 0, snooze_minutes: 0, interrupts: 'when_free',
      readout_scheme: '', readout_fade_s: 10,
    }),
    startedBy: 'schedule',
    // A chime is not waiting to be dismissed, so "any press" would describe
    // the wrong thing entirely: it ends by itself, and a press only shortens
    // it (TODO 106).
    exits: (mode) => {
      if (mode.readout_scheme) return 'ends on its own; a press cuts it short';
      return Number(mode.snooze_minutes) > 0
        ? `any press; long press snoozes ${mode.snooze_minutes}m`
        : 'any press';
    },
    // Alarm-or-Reminder survives the trim, because `urgent` is the one thing
    // that makes two notices *behave* differently rather than merely differ.
    // The time is read off the activation - a notice is always scheduled, and
    // when it goes off is the first thing anyone wants from this row.
    //
    // The tier joins it only when it is not the default: the two ends change
    // what the row *is* - one pierces sleep, the other never lights up - and a
    // silent notice that read like every other notice is the one row here you
    // would forget you had written.
    describe: (mode) => {
      // A chime is a different *kind* of row, not a variant of one: it never
      // waits to be cleared, so "snooze" and "Alarm" would both be lies about
      // it. It leads with the word instead, and keeps only the two things that
      // still apply - when, and how far it may interrupt.
      const kind = mode.readout_scheme
        ? 'Chime' : (mode.urgent ? 'Alarm' : 'Reminder');
      const when = describeActivation(mode.activation);
      const snooze = !mode.readout_scheme && Number(mode.snooze_minutes) > 0
        ? `, snooze ${mode.snooze_minutes}m` : '';
      const reach = { always: ', even when asleep', while_awake: ', only while awake', never: ', silent' };
      const tier = reach[mode.interrupts] || '';
      return `${kind}${mode.message ? ` “${mode.message}”` : ''} · ${when}${snooze}${tier}`;
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
      BETTER_FIELD,
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
    // TODO 66: what `on_exit` actually carries, for a webhook or OSC binding
    // to read without opening main.py. `summary.clean` sorts by key name -
    // that sorted order *is* the OSC argument order - so this list is written
    // in that order rather than the order the code happens to build the dict.
    summaryKeys: [
      { key: 'elapsed_s', about: 'seconds run, at exit' },
      { key: 'laps', about: 'lap count' },
    ],
    // One shortcut, and it is the useful one: a stopwatch's timer is a *named*
    // timer in the log, so `timer_toggle` on the same name starts and stops the
    // very run this app would - from a gesture in your menus, without opening
    // it. Everywhere an ordinary primitive is offered, since that is all it is.
    //
    // **"Show elapsed" is deliberately absent**: `readout` counts today's rows
    // of an event, so pointed at a stopwatch it would say how many runs there
    // have been, not how long the current one is. A duration on the light is a
    // primitive the button does not have, and inventing one to fill this list
    // would be the tail wagging the dog.
    actions: (mode) => [
      {
        id: 'toggle',
        label: 'start / stop the timer',
        about: 'Toggles the same named timer this stopwatch runs, without '
          + 'opening it. The elapsed time is logged on the stop, as usual.',
        body: { action: 'timer_toggle', log_as: mode.log_as || 'stopwatch' },
      },
    ],
    // Named, like the countdown's and the metronome's: this field is
    // `required` and StopwatchBehavior now defaults to the same word, so a
    // stopwatch added here and one a scene file leaves out agree on what the
    // timer is called instead of one of them being unsaveable.
    defaults: () => ({ log_as: 'stopwatch', ladder: defaultLadder() }),
    startedBy: 'gesture',
    exits: () => 'long press (short/double = lap)',
    describe: (mode) => `logs “${mode.log_as || '…'}”`
      + (mode.ladder && mode.ladder.enabled ? ' · the light is a clock' : ''),
  },
  {
    type: 'counter',
    ledStates: ['COUNTING'],
    // The durable values an app of this template keeps (TODO 34). Mirrors
    // DOC_SLOTS in config.py - the manifest's precursor, and where a slot's
    // declaration will live once packages exist. test_documents.py fails on
    // drift. (Comment above `type` so the drift guards read the keys as a
    // pair, the same rule `ledStates` follows.)
    docSlots: [
      { name: 'count', default: 0,
        about: 'The running total, when this tally keeps counting past midnight.' },
    ],
    // What a tally contributes to the rest of the button (TODO 118b) - the two
    // the owner named: count, and reveal the count. `docSlots`' neighbour, and
    // deliberately: one declares what this app remembers, the other what it
    // lends out.
    actions: (mode) => [
      {
        id: 'count_up',
        label: 'count up',
        about: 'Adds to this tally without opening it - a gesture in your '
          + 'menus, a reaction, a step in a sequence. Change the amount below '
          + 'for “+5” or “−1”.',
        // **Which body is honest depends on this tally's own setting**, which
        // is the reason `actions` is a function of the mode rather than a
        // fixed list. A running total lives in the document, so `set_value`
        // moves it; a day counter *is* its rows, so a row is what adds to it.
        // Either way this shortcut moves the same number the app itself shows.
        body: mode.durable
          ? { action: 'set_value', app: mode.name, slot: 'count', op: 'add', value: 1 }
          : { action: 'log', event: mode.event || 'counter' },
      },
      {
        id: 'show_count',
        label: 'show the count',
        about: 'Blinks the count on the light and changes nothing - the same '
          + 'number, in the same scheme, that the tally shows itself.',
        // **The same `mode.durable` test the shortcut above makes**, and it is
        // the join TODO 118a existed to close. A `readout` can point at an
        // app's own slot now, so a tally that keeps counting past midnight
        // reveals the number it is actually keeping rather than recounting
        // today's rows - two answers that agreed only while nothing counted by
        // more than one, and diverged past 99 in any case.
        //
        // Mirrors `config.counter_readout`, which is what `run_counter`'s own
        // periodic flash is built from: the shortcut and the app's surface are
        // one object on the Python side, so this table is the third copy of a
        // decision rather than a second decision. test_readout_source.py
        // compares the two.
        body: mode.durable
          ? {
            action: 'readout', source: 'app', app: mode.name, slot: 'count',
            event: mode.event || 'counter',
            scheme: mode.readout_scheme || '',
            colors: Array.isArray(mode.readout_colors) ? mode.readout_colors : [],
            tens_color: mode.tens_color || '#ff8800',
            units_color: mode.units_color || '#3399ff',
          }
          : {
            action: 'readout', source: 'event', event: mode.event || 'counter',
            scheme: mode.readout_scheme || '',
            colors: Array.isArray(mode.readout_colors) ? mode.readout_colors : [],
            tens_color: mode.tens_color || '#ff8800',
            units_color: mode.units_color || '#3399ff',
          },
      },
    ],
    label: 'Tally',
    about: 'A count you press up.',
    nature: 'takeover',
    allowedActivations: ['manual'], // started by an enter_mode gesture only
    body: 'fields',
    fields: [
      { key: 'event', label: 'Event name', kind: 'text', required: true,
        placeholder: 'water',
        hint: 'Logged per increment (short press / double tap). Long press exits.' },
      // The one field that changes which question the number answers, so it
      // is basic-tier rather than tinker: "how many today" and "how many
      // ever" are both ordinary things to want from a tally.
      { key: 'durable', label: 'Keep counting past midnight', kind: 'checkbox',
        hint: 'Off: the number is today’s presses, and it starts again each '
          + 'day. On: it is a running total this app remembers, which "Change '
          + 'an app’s number" can add to from any gesture - and which you '
          + 'reset by setting it to 0. Either way every press is logged, so '
          + 'history and streaks are the same.' },
      // Unlike a stopwatch or countdown, a tally has no "longest"/"shortest"
      // pair to fall back on when nobody answers - a busiest day is all
      // `renderTally` can say without this. So the default here still reads
      // as today's behaviour (busiest, unlabelled), and this only starts
      // mattering the day someone is counting something they want fewer of.
      BETTER_FIELD,
      // The count, said out loud on a timer (TODO 118c). 0 is off, which is
      // every tally written before this existed.
      { key: 'show_every_s', label: 'Show the count every (seconds)',
        kind: 'number', min: 0, step: 1,
        hint: 'The tally blinks its own number on the light this often, in '
          + 'whatever the row below says. 0 = only when you press. '
          + 'A press cuts the digits short, because you already know.' },
      // **The scheme lives here, on the tally, and not on each binding** -
      // TODO 91's "Done when" in one field. The app's own periodic flash and
      // the "show the count" shortcut it contributes are both built from it
      // (`config.counter_readout`), so configuring it once is configuring it
      // everywhere this number is shown.
      { key: 'readout_scheme', label: 'Read the count as', kind: 'select',
        options: [
          { value: '', label: 'Tens then units - slow, then quick' },
          { value: 'hour_colors', label: 'A colour per value, that many flashes' },
          { value: 'place_value', label: 'Colour per digit, 1-9 flashes each' },
          { value: 'binary', label: 'Binary - two colours, one per bit' },
          { value: 'morse', label: 'Morse - the digits, spoken' },
        ],
        hint: 'The default stops at 99 - a tally past that shows 99 and has '
          + 'always done so. The other four have no ceiling. "Colour per '
          + 'digit" is the same idea without the cap and is the natural move '
          + 'for a tally that runs into the hundreds; Morse and binary stay '
          + 'short however big the number gets.' },
      { key: 'readout_colors', label: 'That scheme’s colours', kind: 'json',
        shape: 'list', tier: 'tinker',
        hint: 'JSON list of "#rrggbb", in the order the scheme uses them - '
          + 'one for Morse, two for binary (0 then 1), one per decimal place '
          + 'for "colour per digit" counting up from the ones, a wheel of any '
          + 'length for "a colour per value". Empty = that scheme’s own '
          + 'colours. The two rows below belong to the tens/units default.' },
      { key: 'tens_color', label: 'Tens colour', kind: 'color', tier: 'tinker',
        hint: 'The slow pulses - the coarse digit, on the tens/units default. '
          + 'The "show the count" shortcut this tally contributes carries the '
          + 'same one, so the two never disagree.' },
      { key: 'units_color', label: 'Units colour', kind: 'color', tier: 'tinker',
        hint: 'The quick pulses - the fine digit, on the tens/units default.' },
      // Five steps and one way out (TODO 118c). **Long press is not here and
      // cannot be**: it leaves the tally, as it leaves every app, and
      // `_parse_counter_body` drops a step written against it exactly as
      // `_parse_control_body` drops a binding on it. That is why this list is
      // five long where the button has six gestures - the same shape the
      // Actions and Control templates' `gestures` lists already have.
      //
      // Written out rather than derived from GESTURES, which is a concession
      // to the mirror test next door: `test_schema_mirror.py` reads these
      // descriptors with a bracket walk and cannot evaluate a `.map()`, and
      // its own rule is that a mirror which becomes hard to extract loses the
      // clever side, not the test. `test_app_actions.py` pins the list against
      // TRIGGER_TYPES instead, so the derivation's guarantee survives as an
      // assertion.
      //
      // All five are basic-tier: assigning the presses *is* this app's
      // surface, and burying three of them under Tinker would hide the feature
      // behind the setting that turns it on.
      { key: 'short_press', label: 'Short press counts', kind: 'number', step: 1,
        hint: '0 = this press does nothing. An amount other than 1 moves the '
          + 'number and is written on the row - but a tally that starts again '
          + 'each day counts presses, so switch on "Keep counting past '
          + 'midnight" if +5 should still read as 5 tomorrow.' },
      { key: 'double_tap', label: 'Double tap counts', kind: 'number', step: 1,
        hint: '0 = this press does nothing. Negative counts down, which is how '
          + 'you undo a miscount.' },
      { key: 'triple_tap', label: 'Triple tap counts', kind: 'number', step: 1,
        hint: '0 = this press does nothing.' },
      { key: 'tap_4', label: 'Four taps counts', kind: 'number', step: 1,
        hint: '0 = this press does nothing. Filling it in slows every shorter '
          + 'tap slightly - the button must wait to rule out a 4th.' },
      { key: 'tap_5', label: 'Five taps counts', kind: 'number', step: 1,
        hint: '0 = this press does nothing. Deliberately awkward, so a good '
          + 'home for a reset or a big jump - and it slows the shorter taps '
          + 'the same way.' },
    ],
    // A tally, not a value: each press is one row and the number worth seeing
    // is how many of them a day held - which is exactly what `count_today`
    // already answers on the button, arrived at the same way.
    readout: {
      kind: 'log', nameField: 'event', measure: 'tally',
      noun: 'press', better: null,
    },
    // TODO 66, sorted the way summary.clean will send it over OSC.
    summaryKeys: [
      { key: 'added', about: 'increments this session' },
      { key: 'count', about: 'running total' },
    ],
    // Named for the same reason the stopwatch's is: `event` is `required` and
    // run_counter uses it unguarded, so an empty default writes rows called ""
    // and sums every unnamed counter into one bucket.
    // The two steps `CounterBehavior` defaults to, spelled out - and the other
    // three written as 0 rather than left out, because the number widget has no
    // empty state and a slot that vanished on Save would read as the field
    // having been ignored. Zeroes are dropped by the parser, so an untouched
    // tally still tells the device to count no further than two.
    defaults: () => ({
      event: 'counter', durable: false,
      short_press: 1, double_tap: 1, triple_tap: 0, tap_4: 0, tap_5: 0,
      show_every_s: 0, tens_color: '#ff8800', units_color: '#3399ff',
    }),
    startedBy: 'gesture',
    exits: () => 'long press (the presses with a step count)',
    describe: (mode) => {
      const steps = counterSteps(mode)
        .map(([, step]) => `${step > 0 ? '+' : ''}${step}`);
      const how = steps.length ? steps.join('/') : 'no press counts';
      return `${how} to “${mode.event || '…'}”`
        + (mode.durable ? ' · a running total' : ' · today only')
        + (Number(mode.show_every_s) > 0 ? ` · shows every ${fmtLength(mode.show_every_s)}` : '');
    },
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
    // The plainest contribution there is, and worth having for exactly that
    // reason: "open it" under the menu's own name beats finding "Launch an
    // app" and then finding this menu in its target list. Same body either
    // way - which is the point of a contributed action being a pre-filled
    // instance rather than a new kind of thing.
    actions: (mode) => [
      {
        id: 'open',
        label: 'open this menu',
        about: 'Opens the menu, so the next presses step through its apps.',
        body: { action: 'enter_mode', target: mode.name },
      },
    ],
    defaults: () => ({ targets: '', return_after: true, log_as: '' }),
    startedBy: 'gesture',
    exits: () => 'long press (short = next app, double tap = launch)',
    describe: (mode) => {
      const listed = String(mode.targets || '').trim();
      const count = listed ? listed.split(/\n+/).filter(Boolean).length : 0;
      return count ? `over ${count} chosen app(s)` : 'over every app';
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
      BETTER_FIELD,
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
    describe: (mode) => `${mode.start_bpm ?? 120} BPM`
      + (mode.clock_port ? ` · follows ${mode.clock_port}` : ''),
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
    BETTER_FIELD,
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
  describe: (mode) => `${mode.minutes ?? 10} min`
    + (mode.label ? ` · “${mode.label}”` : ''),
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
  // TODO 66, sorted the way summary.clean will send it over OSC.
  summaryKeys: [
    { key: 'blocks', about: 'work blocks completed' },
    { key: 'focused_s', about: 'seconds spent working' },
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
  // TODO 66, sorted the way summary.clean will send it over OSC.
  summaryKeys: [
    { key: 'best_pct', about: 'closest guess, 0-100' },
    { key: 'hits', about: 'guesses within tolerance' },
    { key: 'played', about: 'rounds played' },
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
    return `${rounds} · ${mode.sweep_s ?? 4}s wheel`;
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
  // TODO 66, sorted the way summary.clean will send it over OSC.
  summaryKeys: [
    { key: 'average_ms', about: 'mean reaction time, 0 if none played' },
    { key: 'best_ms', about: 'fastest reaction, 0 if none played' },
    { key: 'false_starts', about: 'presses before the light went out' },
    { key: 'played', about: 'attempts, false starts included' },
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
    return rounds;
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
    { key: 'states', label: 'Positions', kind: 'json', shape: 'list',
      tier: 'tinker',
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
  // One shortcut per position this light actually has - which is why a
  // template's `actions` is a function of the mode rather than a fixed list.
  //
  // **This is where the allow-list rule pays for itself.** `set_position` is
  // `appOnly`, and it is in `REFLEX_ACTIONS` and in nothing else, so these
  // appear on a reaction's "then" and on no gesture, no hook, no pool entry
  // and no sequence step - without a word about it being written here. The
  // free-text position field stays exactly as it was for anything hand-typed;
  // this only means the names you already wrote are pickable.
  actions: (mode) => (Array.isArray(mode.states) ? mode.states : [])
    .filter((state) => state && state.name)
    .map((state) => ({
      id: `position:${state.name}`,
      label: `show “${state.name}”`,
      about: 'For a reaction limited to this app: something out there reports '
        + 'where we are, and the light shows it without sending this '
        + 'position’s own message back.',
      body: { action: 'set_position', name: state.name },
    })),
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
    if (!names.length) return 'no positions yet';
    return names.join(' / ');
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
    // A JSON field for the reason the Signal light's positions are one, and
    // with the same known rough edge: a proper repeating sub-form is the
    // follow-up. What differs is where the colour comes from - a position
    // *names* a look rather than carrying one, because this template already
    // answers "what does this look like" through its LISTENING look, and two
    // controls for one question is the thing CLAUDE.md forbids. The named look
    // is the more explicit of the two, so it wins while a position is showing.
    { key: 'positions', label: 'Positions something else reports', kind: 'json',
      shape: 'list', tier: 'tinker',
      hint: 'Optional. List of {name, look} - a reaction’s "Set position" puts '
        + 'the page on one and it wears that look until it is told otherwise. '
        + 'No gesture moves it. A position with no look wears this page’s '
        + 'own colour.' },
    { key: 'log_as', label: 'Log each command as', kind: 'text',
      placeholder: 'daw',
      hint: 'Optional - one row per command sent. A failed send logs '
        + 'nothing, so counts stay honest. A position that arrives is not a '
        + 'command and is not counted as one.' },
    { key: 'return_after', label: 'Come back here after a branch',
      kind: 'checkbox', tier: 'tinker',
      hint: 'Bind a gesture to "Launch an app" and this becomes a menu page. '
        + 'On: leaving what it opened returns here, so long press always '
        + 'travels one level. Off: drops straight back to your menus.' },
  ],
  // Optional, like the field: a control surface logs only if you ask it to.
  readout: {
    kind: 'log', nameField: 'log_as', measure: 'tally',
    noun: 'press', better: null,
  },
  // The Signal light's contribution, asked of the other template with
  // positions - and the case this feature is most obviously for: pairing a
  // reaction with a page position used to mean typing the name back in by
  // hand, with nothing checking it matched. Same `set_position` action, same
  // reflex-only reach; only the typing goes away.
  actions: (mode) => (Array.isArray(mode.positions) ? mode.positions : [])
    .filter((position) => position && position.name)
    .map((position) => ({
      id: `position:${position.name}`,
      label: `show “${position.name}”`,
      about: 'For a reaction limited to this page: the page wears this '
        + 'position’s look until something says otherwise. No gesture moves '
        + 'it and nothing is sent.',
      body: { action: 'set_position', name: position.name },
    })),
  defaults: () => ({
    short_press: { action: 'log', event: 'control_press' },
    log_as: '', return_after: true, positions: [],
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
    const positions = Array.isArray(mode.positions) ? mode.positions.length : 0;
    // Said before the bindings, because a surface with positions is a readout
    // of something else's state first and a remote second.
    if (positions) {
      parts.unshift(`${positions} position${positions === 1 ? '' : 's'}`);
    }
    return parts.length ? parts.join(' · ') : 'nothing bound yet';
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
    if (!count) return 'no looks chosen yet';
    return `${count} look${count === 1 ? '' : 's'}`
      + `${mode.auto === false ? ', manual' : `, ${mode.dwell_s || 8}s each`}`;
  },
});

export const TEMPLATE_BY_TYPE = Object.fromEntries(TEMPLATES.map((t) => [t.type, t]));

// Ready-made modes, offered next to "+ Add mode". Each is a complete mode
// object the parser accepts as-is - a starting point to edit, not a special
// kind of mode. Names are checked for collisions when one is added.
export const BUILTIN_MODES = [
  // Three presets over the one notice template (TODO 84) - what a preset buys
  // is *findability*, nobody looking for a dead man's switch would think to
  // open a generic notice and read its fields.
  {
    id: 'alarm',
    label: 'Alarm',
    blurb: 'Rings at a set time until you deal with it.',
    mode: () => ({
      name: 'Alarm', template: 'notice',
      activation: { type: 'schedule', at: '07:00' },
      ...TEMPLATE_BY_TYPE.notice.defaults(),
      urgent: true, log_as: 'alarm',
    }),
  },
  {
    id: 'reminder',
    label: 'Reminder',
    blurb: 'A gentler alarm - shows at a set time, chimes once, gives up on its own.',
    mode: () => ({
      name: 'Reminder', template: 'notice',
      activation: { type: 'schedule', at: '10:00' },
      ...TEMPLATE_BY_TYPE.notice.defaults(),
      urgent: false, timeout_minutes: 5, log_as: 'reminder',
    }),
  },
  {
    id: 'deadman',
    label: "Dead man's switch",
    blurb: 'Rings to check in; runs an action if you do not answer.',
    mode: () => ({
      name: 'Check in', template: 'notice',
      activation: { type: 'schedule', at: '09:00' },
      ...TEMPLATE_BY_TYPE.notice.defaults(),
      message: 'Still there?',
      timeout_minutes: 15,
      log_as: 'checkin',
      on_missed: { action: 'webhook', url: '', method: 'POST' },
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
    // Spread, like the Notice presets above: a preset claims to be a finished
    // mode, so it has to carry every field its template declares or the
    // editor's own Check rejects what "Add a ready-made mode" just wrote
    // (TODO 35's failure, met again the moment the Tally grew its step fields).
    mode: () => ({
      name: 'Gratitude', template: 'counter', activation: { type: 'manual' },
      ...TEMPLATE_BY_TYPE.counter.defaults(),
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
      name: 'Wake up', template: 'notice',
      activation: { type: 'schedule', at: '05:00' },
      ...TEMPLATE_BY_TYPE.notice.defaults(),
      message: 'Wake up', snooze_minutes: 9, log_as: 'woke_up',
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

// Which templates are a *menu*: a gesture picks between things. The everyday
// gesture map is the plain case, a launcher picks an app and a control surface
// picks an action - one idea wearing three template names. UI-only grouping,
// so it lives here beside the groups rather than becoming a mirrored token: a
// launcher's `nature` is still 'takeover' and must stay that way (CLAUDE.md).
export const MENU_TEMPLATES = ['actions', 'launcher', 'control'];

// TODO 75: three groups, and the words only became true once reflexes existed
// (TODO 71). "Reflexes" used to head the gesture maps - the most *voluntary*
// thing on the page - under a word meaning involuntary. It now means what it
// says, and what it displaced is a menu.
// TODO 103 renamed it again, to "Reactions", and that is allowed only because
// it is a *synonym*: nothing else took the name and no concept changed hands,
// which is exactly what was untrue the first time. The token did not move -
// `AppConfig.reflexes` and `REFLEX_ACTIONS` are unchanged, per CLAUDE.md.
// TODO 102 then took the group out of this list altogether: reactions are a
// destination of their own now (the Actions page), and a nav group that
// jumps to a page reachable from the nav is a second door onto one room -
// which is what TODO 82 removed for apps. The remaining groups are the two
// kinds of *mode*, plus the unrecognised bucket (TODO 107).
export const MODE_GROUPS = [
  {
    key: 'menus',
    title: 'Menus',
    blurb: 'A press picks between things. The everyday map is read top to '
      + "bottom and the first entry that's awake and sets this press wins, so "
      + 'order is priority - move one up to win, leave a gesture unset and it '
      + 'falls through. Launchers and control pages are the same idea with '
      + 'the button to themselves.',
    emptyText: 'None yet.',
  },
  {
    key: 'apps',
    title: 'Apps',
    blurb: 'One at a time, and while it runs it owns the button - every menu '
      + 'is muted until you leave. Most are launched by a press bound to '
      + '“Launch an app”; an alarm launches itself at its set time.',
    emptyText: 'None yet.',
  },
  {
    // TODO 107. Shown only when it has members - see menu.js. The everyday
    // cause is not a broken config but a *newer* one than this page: `/static`
    // is served no-store only after a service restart, so a browser can run a
    // stale module graph against a config that has since gained a template.
    // Filing those under Menus (the old fallback) made a scheduled Notice
    // read as a mis-added gesture map, which is how alarms "became menus".
    key: 'unknown',
    title: 'Unrecognised',
    blurb: 'This page does not know these templates. They are running fine - '
      + 'it is the editor that is behind. Reload the page; if they are still '
      + 'here, restart the service so /static stops being cached.',
    emptyText: 'None.',
  },
];

/** How you leave a takeover mode, in one sentence. Null for everyday modes,
 *  which are never entered and so never need leaving. */
export function describeExit(mode) {
  const descriptor = mode && TEMPLATE_BY_TYPE[mode.template];
  return descriptor && descriptor.exits ? descriptor.exits(mode) : null;
}

/** Every way in to `mode` that can be named — a gesture in another mode, or a
 *  reflex. An empty list means nothing can start it, which is a mode you can
 *  configure but never reach.
 *
 *  Reflexes are listed here rather than left to the launcher fallback below
 *  because "a script opens this" is the most surprising answer on the page,
 *  and an app reachable *only* that way would otherwise read as reachable for
 *  a reason that is not true. */
export function findEntryPoints(mode, allModes, actions = {}, reflexes = []) {
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
  for (const reflex of reflexes || []) {
    const action = resolveBinding(reflex?.then, actions);
    if (action && action.action === 'enter_mode' && action.target === mode.name) {
      entries.push(`the reaction “${reflex.name || '(unnamed)'}”`);
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
 * Null for a template that owns no LED state (a gesture map, a launcher, hot/cold,
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

/** One reflex in a sentence: what has to be true, what it does, and what it
 *  is limited to. One formatter, because the row that edits it and the nav
 *  that lists it must not describe the same object two ways. */
export function describeReflex(reflex) {
  const midi = reflex?.from?.midi;
  const url = reflex?.from?.url;
  // A polled source says its reader and its interval and *not* its address,
  // deliberately: the endpoints this is built for are secret-URL calendars
  // (TODO 100), where the link is the credential. A summary line is repeated
  // into the nav and every card, so printing it would scatter the secret
  // across the UI to say nothing the reader and interval do not already say.
  const reader = url
    ? REFLEX_SOURCES.find((s) => s.key === 'url')?.readers
      ?.find((r) => r.key === (url.read || 'json'))?.label
    : null;
  // Source and test read as one clause - "MIDI note 95, velocity == 127" -
  // because that is one circumstance said in two halves, and an arrow between
  // them would suggest two steps.
  const circumstance = [
    midi ? `MIDI ${'cc' in midi ? `CC ${midi.cc}` : `note ${midi.note}`}` : null,
    url ? `${reader || 'a URL'} every ${url.every_minutes ?? 15} min` : null,
    reflex?.when?.field
      ? `${reflex.when.field} ${reflex.when.op || '<'} ${reflex.when.value ?? 0}`
      : null,
  ].filter(Boolean).join(', ');
  const scope = reflex?.while ? ` (only while ${reflex.while})` : '';
  const then = describeAction(reflex?.then);
  return `${circumstance ? `${circumstance} → ` : ''}${then}${scope}`;
}

/**
 * The set of modes something can reach, given the whole config.
 *
 * **Roots are the things nobody has to start.** A gesture map is live by
 * definition, a clock starts its own apps, and - since TODO 71 - a reflex is
 * fired by the world, so whatever it opens is a root too. Everything else is
 * reachable only by being pointed at - by a gesture bound to "Launch an app",
 * or by sitting in a launcher's list - and reachability is transitive, because
 * a launcher you cannot open cannot open anything either. That transitivity is
 * the reason this is a walk rather than a filter, and the reason a per-mode
 * card could never answer the question on its own.
 *
 * *A new way to open an app is an edge in this walk, or the App page will call
 * working configs broken.*
 */
export function reachableModes(modes, actions = {}, reflexes = []) {
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
  // A scoped reflex (`while`) is still a root: it opens its app when that app
  // is running, and an app already running is reached by definition - so
  // narrowing this by scope could only ever produce a false "unreachable".
  for (const reflex of reflexes || []) {
    const action = resolveBinding(reflex?.then, actions);
    if (action && action.action === 'enter_mode' && action.target) {
      push(byName.get(action.target));
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
export function danglingTargets(modes, actions = {}, reflexes = []) {
  const all = (modes || []).filter(Boolean);
  const names = new Set(all.map((m) => m.name).filter(Boolean));
  const missing = new Map(); // target name -> [what points at it]
  const note = (target, from) => {
    const seen = missing.get(target) || [];
    seen.push(from);
    missing.set(target, seen);
  };
  for (const mode of all) {
    for (const gesture of GESTURES) {
      const action = resolveBinding(mode[gesture.key], actions);
      if (!action || action.action !== 'enter_mode' || !action.target) continue;
      if (names.has(action.target)) continue;
      note(action.target, `${gesture.label} on ${mode.name || '(unnamed)'}`);
    }
  }
  for (const reflex of reflexes || []) {
    const action = resolveBinding(reflex?.then, actions);
    if (!action || action.action !== 'enter_mode' || !action.target) continue;
    if (names.has(action.target)) continue;
    note(action.target, `the reaction “${reflex.name || '(unnamed)'}”`);
  }
  return missing;
}

// --- where a pooled action is used -----------------------------------------
// TODO 102, and the same question the look pool already answers about a look:
// **editing a shared thing changes it everywhere, and that has to be visible
// before the edit rather than after it.**

/**
 * Every slot in a config that holds an action binding, as
 * `{ owner, key, where }` - so `owner[key]` is the binding and `where` is the
 * sentence a person would use for that place.
 *
 * **One walk, two callers, and that is the point.** The editor's rename used
 * to have a hand-written list of places to rewrite - gestures and a signal
 * light's positions - which quietly missed hooks, a Notice's outcomes, a
 * reaction's `then` and every step of a sequence. Renaming a pooled action
 * from the editor could therefore dangle exactly the references the parser
 * then warned about. A list of usages and a list of things to rewrite are the
 * same list, so they are computed once.
 *
 * A `bindings` key on a template descriptor joins this for free, which is what
 * that key is for (CLAUDE.md).
 */
export function actionRefs(modes = [], reflexes = [], pool = {}) {
  const refs = [];
  const add = (owner, key, where) => {
    if (owner && owner[key] !== undefined && owner[key] !== null) refs.push({ owner, key, where });
  };
  // A sequence step may name a pool entry (a *sequence* may not - that is the
  // one-level rule, refused in resolve_action), so a step is a slot too.
  const steps = (action, where) => {
    if (!action || action.action !== 'sequence' || !Array.isArray(action.steps)) return;
    action.steps.forEach((_, i) => add(action.steps, i, `${where}, step ${i + 1}`));
  };
  const slot = (owner, key, where) => {
    add(owner, key, where);
    steps(owner?.[key], where);
  };

  for (const mode of modes || []) {
    if (!mode) continue;
    const label = mode.name || '(unnamed)';
    const descriptor = TEMPLATE_BY_TYPE[mode.template];
    for (const gesture of GESTURES) slot(mode, gesture.key, `${gesture.label} on ${label}`);
    for (const hook of MODE_HOOKS) slot(mode, hook.key, `${hook.label} on ${label}`);
    for (const binding of descriptor?.bindings || []) {
      slot(mode, binding.key, `${binding.label} on ${label}`);
    }
    // A signal light's positions each fire one on the way in.
    for (const state of mode.states || []) {
      if (state) slot(state, 'action', `${state.name || 'a position'} in ${label}`);
    }
  }
  for (const reflex of reflexes || []) {
    if (reflex) slot(reflex, 'then', `the reaction “${reflex.name || '(unnamed)'}”`);
  }
  for (const [name, action] of Object.entries(pool || {})) {
    steps(action, `“${name}”`);
  }
  return refs;
}

/** Where the pool entry `name` is used, in the words a person would use.
 *  Only *named* references count - an inline action that happens to look the
 *  same is a different action, which is the whole distinction the pool draws. */
export function actionUsedBy(name, modes, reflexes, pool) {
  return actionRefs(modes, reflexes, pool)
    .filter((ref) => ref.owner[ref.key] === name)
    .map((ref) => ref.where);
}

// --- what an app has actually done -----------------------------------------

/**
 * The live numbers for `mode`, picked out of `/api/events/summary`'s rows.
 * `null` when the template logs nothing, the mode has not named its log, or
 * the log has never seen it - all three of which mean "say nothing", not
 * "say zero".
 *
 * **Structured, not formatted** (TODO 101): schema.js is the data module and
 * deliberately holds no `format.js` import, so this returns the numbers and
 * the caller writes the sentence. That also makes it a table test.
 *
 * **`best` appears only where a `better` was actually chosen** - by the
 * template, or by this item overriding it (`betterFor`). Most templates
 * declare none, and that is the honest part rather than a gap: "fastest" is a
 * fact about a reaction timer and a guess about a stopwatch, since the same
 * template times a mile run, where quicker is better, and a cake, where it is
 * not. TODO 109 is that guess becoming the item's to make; putting a best on
 * every app regardless would print a judgement the config never made.
 */
export function betterFor(mode, readout) {
  const own = mode?.better;
  return MODE_BETTER.includes(own) ? own : (readout?.better ?? null);
}

// --- what the button does on its own (TODO 111) ----------------------------
// A compiled package runs with nobody connected, and the whole hazard is that
// it is a *snapshot*: edit the config afterwards and the button quietly keeps
// doing the old thing whenever the host is away. `GET /api/app` answers that
// comparison; this turns the answer into a verdict, and the page writes the
// sentence - the same structured-not-formatted split `readoutStat` follows.

/**
 * One of five states, from what `/api/app` said.
 *
 *   unsupported  the button is there and its firmware cannot run apps at all
 *   unbuildable  nothing in this config compiles yet (`why` says what)
 *   empty        it could run one, and there is none installed
 *   stale        one is installed and it is not what this config makes now
 *   current      installed, and it matches
 *
 * **`supported` is asked first and answers for a disconnected button too**,
 * because `info` falls back to the assumed one when nothing is attached - so
 * "your firmware is too old" and "no button is plugged in" are the same answer
 * here, and the page says the honest half: what would be installed *if*.
 *
 * `null` in means the page has not asked yet (or there is no service to ask),
 * which is silence rather than a state - the same rule `readoutStat` follows
 * for a log that has never seen an app.
 */
export function standaloneVerdict(status) {
  if (!status) return null;
  if (!status.supported) return { state: 'unsupported', buildable: !!status.buildable };
  if (!status.buildable) return { state: 'unbuildable', why: status.why || '' };
  // 0 is the wire's "no package", not a checksum: the firmware starts there
  // and stays there with no `app.pkg` on flash, and a device too old to send
  // the field decodes to it (device.py's `package_crc: int = 0`). A real
  // package could in principle checksum to zero and would then read as empty,
  // which costs an Install nobody needed - the opposite mistake, reporting a
  // bare board as up to date, is the one that matters.
  if (!status.installed_crc) return { state: 'empty', bytes: status.bytes };
  if (status.current) return { state: 'current', bytes: status.bytes };
  return { state: 'stale', bytes: status.bytes };
}

export function readoutStat(mode, rows) {
  const readout = TEMPLATE_BY_TYPE[mode?.template]?.readout;
  if (!readout) return null;
  const better = betterFor(mode, readout);
  const name = mode[readout.nameField];
  if (!name) return null;
  const row = (rows || []).find((r) => r && r.kind === readout.kind && r.name === name);
  if (!row || !row.count) return null;

  const stat = {
    count: row.count, noun: readout.noun, last: row.last,
    best: null, unit: readout.unit || '', bestIsDuration: false,
  };
  if (better === 'low' || better === 'high') {
    const duration = readout.measure === 'duration';
    const low = duration ? row.duration_min : row.value_min;
    const high = duration ? row.duration_max : row.value_max;
    const best = better === 'low' ? low : high;
    if (best !== null && best !== undefined) {
      stat.best = best;
      stat.bestIsDuration = duration;
    }
  }
  return stat;
}

// --- what starts a thing ---------------------------------------------------
// TODO 101. The nav's groups say what a mode *is*; this says what sets it off,
// which is the other half and the half nobody could see. It is a render of
// `reachableModes` rather than new logic - which is why "nothing starts this"
// comes out for free, and it is the valuable one: an app you can configure and
// never reach is a bug in your config, and it used to be reported only in
// prose on a page you had to go to.

/** The five answers, as data so the nav renders from a table rather than a
 *  switch. Glyphs are text, not emoji: emoji render differently on every
 *  platform and several are colour-only, and **colour is already spoken for by
 *  the look swatch beside them**. `live` draws nothing - a gesture map is
 *  always listening, and every row in that group is, so an empty column reads
 *  as a property of the group rather than as a missing value. */
export const STARTERS = [
  { key: 'live', glyph: '', label: 'always listening',
    title: 'Always listening. It answers presses whenever no app has taken the button over.' },
  { key: 'clock', glyph: '◷', label: 'a clock',
    title: 'A schedule starts this, with nobody pressing anything.' },
  { key: 'reaction', glyph: '⚡', label: 'a reaction',
    title: 'Something outside the button starts this.' },
  { key: 'press', glyph: '▸', label: 'a press',
    title: 'A gesture somewhere opens this.' },
  { key: 'none', glyph: '⊘', label: 'nothing',
    title: 'Nothing can reach this. Bind a gesture to "Launch an app", or add it to a launcher.' },
];

export const STARTER_BY_KEY = Object.fromEntries(STARTERS.map((s) => [s.key, s]));

/**
 * What sets `mode` off: one of STARTERS' keys.
 *
 * **`reached` is passed in rather than computed here**, because the answer is
 * a property of the whole config and the nav asks it once per row. Computing
 * it inside would make an O(n) walk O(n squared) on every keystroke, for an
 * answer that cannot differ between two rows of one render.
 *
 * **The order of the checks is the order of surprise.** A mode may be several
 * of these at once - a scheduled notice you can also launch by hand - and the
 * one worth one line is the most autonomous, because that is the one you did
 * not do. `none` is first in effect: if nothing reaches it, nothing else about
 * it is true.
 */
export function startedBy(mode, reached, actions = {}, reflexes = []) {
  const descriptor = mode && TEMPLATE_BY_TYPE[mode.template];
  // An unknown template is not classified here either (TODO 107): the nav
  // gives it its own group, and guessing a starter would be the same invented
  // classification one layer down.
  if (!descriptor) return 'none';
  if (descriptor.nature === 'ambient') return 'live';
  if (reached && !reached.has(mode)) return 'none';
  if (descriptor.startedBy === 'schedule') return 'clock';
  for (const reflex of reflexes || []) {
    const action = resolveBinding(reflex?.then, actions);
    if (action && action.action === 'enter_mode' && action.target === mode.name) {
      return 'reaction';
    }
  }
  return 'press';
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
  { key: 'COUNTING', label: 'Tally open', meaning: 'a tally is open' },
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
  // A Morse look (TODO 83) is a look but not a style either, and it compiles
  // to a stop list only on the server - see ledPreview.js's colorAt for why
  // this describes the message rather than trying to render its rhythm.
  if (effect && typeof effect.morse === 'string') {
    const dpm = effect.dpm || 400;
    const shape = Array.isArray(effect.ramp) && effect.ramp.length ? 'ramp' : (effect.color || '#ff0000');
    return `Morse "${effect.morse}" at ${dpm} dots/min, ${shape}, `
      + (effect.repeat === false ? 'plays once' : 'looping');
  }
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
        hint: 'Floor for flash + alternate. 0.33s = 3/sec, the display '
          + 'guideline (WCAG 2.3.1). Lower it to let the metronome and light '
          + 'shows run faster: that guideline is written for screens filling '
          + 'much of your vision, not for one small LED on a desk.' },
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
