# Web UI — UX audit

A review of the AI Button web interface (`aibutton/web/`): the dashboard
(`index.html`), the configuration menu (`menu.js`, `modeEditor.js`,
`widgets.js`, `schema.js`), and the REST surface they call (`webui.py`).

Split into **fixes** (defects / problems) and **improvements** (enhancements).
Items marked ✅ have been addressed; the rest are open.

## Fixes

### Accessibility
1. ✅ **Icon controls have no accessible name/state.** The expand toggle
   (`.mode-toggle` ▸/▾) and the ↑ ↓ ✕ minis relied on a `title` + glyph; no
   `aria-label`, and the toggle had no `aria-expanded`. → added both.
2. ✅ **Status changes aren't announced.** `#state`/`#last` update via polling
   with no `aria-live`. → `role="status"` + `aria-live="polite"`.
3. ✅ **No visible focus indicator.** Custom dark controls used the faint UA
   default outline. → added a `:focus-visible` ring.
4. **Small, low-contrast text.** `--dim` (#8a94a3) at 11–12 px for hints/errors/
   meta; `.mode-sum-sep` uses `--line` (#2a313b), near-invisible. Verify against
   WCAG AA (4.5:1 for <18 px) and raise.
5. **Form controls without programmatic labels.** The window/schedule editors
   pair `<input type=time>` with plain `<span class="scope-lbl">` rather than
   `<label for>`.
6. ✅ **Animations ignore `prefers-reduced-motion`.** Breathe/rainbow/flash run
   constantly. → reduced-motion media query with static state colors.

### Data-loss / destructive
7. ✅ **No unsaved-changes guard.** `dirty` was tracked but nothing warned on
   reload/close. → `beforeunload` guard when dirty.
8. **Delete mode is instant and irreversible.** ✕ → `onRemove` splices
   immediately; no confirm/undo.
9. **Revert discards silently** even when dirty.

### Async / feedback robustness
10. ✅ **Buttons not disabled during in-flight requests.** `save()`/`check()`
    could double-submit. → disable the action bar while busy.
11. **Trigger/clock failures only `console.warn`** — no on-screen feedback.
12. **Validation appears only on Check/Save, far from the field** — the offending
    (possibly collapsed) card isn't expanded/scrolled to; no live validation.

### Correctness / confusing behavior
13. ✅ **Stale `enter_mode` target passed validation but broke at runtime.**
    Renaming/deleting a takeover left the action pointing at a missing name; the
    validator only checked non-empty. → the select now flags a value that isn't
    among the current options.
14. ✅ **Simulating a gesture while OFF did nothing, silently.** → the
    short/long/double sim buttons are disabled while the device is off.
15. **Test clock can't set a date**, so day-scoped (Mon–Fri) rules can't be
    tested though the API accepts full ISO. → `datetime-local`.
16. **Counter amount invisible in Recent events** — `+20` looks like `+1`
    (`recent()` doesn't expose `count`).
17. **Virtual panel shows raw enum** (`POMODORO_WORK`) and can diverge from the
    badge (badge never shows `LISTENING`).
18. **Polling never pauses or backs off** — 1 s `/api/status`, 5 s `/api/events`
    forever, even when hidden/offline.
19. **Save collapses every card and loses scroll** (`save()` calls `_render()`).
20. ✅ **Event table rebuilt with unescaped `innerHTML`** — a log/timer name like
    `<img onerror=…>` would execute. → user values are now HTML-escaped.

## Improvements

### Realtime & status
1. Push updates via SSE/WebSocket instead of 1 s polling.
2. Live takeover panel — a big running countdown/value for stopwatch / counter /
   pomodoro (server already emits "Work 24:58").
3. Connection indicator + "updated Ns ago".
4. Highlight the mode that would handle a press right now (from modes + clock).

### Editor power
5. Drag-and-drop reordering (keyboard-accessible) instead of ↑/↓.
6. Duplicate-mode button.
7. Per-mode enable/disable toggle (mute without deleting).
8. Collapse-all / expand-all, and remember expanded cards across reloads.
9. Search/filter the modes list.
10. Sound preview (▶) per cue/alarm via `/api/dev/sound/...`.

### Feedback & guidance
11. Toast notifications instead of the persistent `<pre>`.
12. Inline live validation + a clickable error summary that expands/scrolls to
    the offending card.
13. Confirm-with-undo (snackbar) for destructive actions.
14. Recipe quick-add ("Add a wake alarm", "Add a focus stopwatch") + real empty
    states.

### Data & insight
15. Stats panel — daily counts, streaks, focus totals (`count_today` /
    `current_streak` / `total_today`), none surfaced today (TODO #14).
16. Richer event log — filter by name/kind, group by day, show the counter
    amount, "load more".
17. Config export/import (download/upload JSON).

### Ergonomics & a11y
18. Keyboard shortcuts — Ctrl/Cmd+S to Save, Esc to collapse.
19. Mobile polish — sticky bottom action bar, ≥44 px tap targets, clock presets.
20. Theming & a calmer-motion preference beyond the media query.

---

## Quick wins implemented in this pass

Fixes 1, 2, 3, 6, 7, 10, 13, 14, 20 — the contained, high-impact set that
hardens accessibility, prevents data loss / double-submit, removes the event-log
injection vector, and clears up two confusing behaviors. The rest remain open
above and are good follow-ups.
