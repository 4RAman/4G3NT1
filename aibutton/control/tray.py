"""The tray icon, its menu, and the status/log window behind it.

This is the I/O edge: everything it renders comes from
[status.py](status.py)'s pure derivations and everything it does goes
through [supervisor.py](supervisor.py). Keep decisions out of here.

**Threading.** Tk insists on owning the thread its `mainloop` runs on, and
pystray's Win32 backend runs a message loop in whatever thread starts it.
So Tk gets the main thread and the icon gets a daemon thread, and every
menu callback hops back onto Tk with `after(0, ...)` rather than touching
widgets from the tray thread. Polling runs on Tk's timer for the same
reason - one thread owns the UI state, which is why nothing here locks.
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import scrolledtext

import pystray

from .icon import ensure_ico, status_dot
from .status import Health, Level, headline, summary_lines
from .supervisor import Supervisor, web_url

log = logging.getLogger(__name__)

POLL_MS = 1000
# Fixed number of status slots in the tray menu. pystray builds its menu once
# and re-reads each item's text/visibility, so the slots exist up front and
# the unused ones hide themselves.
_STATUS_SLOTS = 6


class ControlPanel:
    def __init__(self, root_dir: Path, config: Path) -> None:
        self.sup = Supervisor(root_dir, config)
        self.config = config
        self.health = Health()
        self._level = Level.STOPPED
        self._quitting = False

        self._tk = tk.Tk()
        self._tk.title("Button control")
        self._tk.geometry("560x420")
        self._tk.minsize(420, 300)
        # Closing the window hides it; the tray icon is the real lifetime.
        self._tk.protocol("WM_DELETE_WINDOW", self.hide_window)
        self._tk.withdraw()
        ico = ensure_ico(Path(__file__).resolve().parent)
        if ico is not None:  # cosmetic; the panel works without it
            with contextlib.suppress(tk.TclError):
                self._tk.iconbitmap(str(ico))
        self._build_window()

        self._icon = pystray.Icon(
            "button-control",
            status_dot(Level.STOPPED),
            "Button control",
            menu=self._menu(),
        )

    # --- the window ---------------------------------------------------

    def _build_window(self) -> None:
        pad = {"padx": 10, "pady": 6}
        self._summary = tk.StringVar(value="Service: Stopped")
        tk.Label(
            self._tk,
            textvariable=self._summary,
            justify="left",
            anchor="w",
            font=("Segoe UI", 10),
        ).pack(fill="x", **pad)

        bar = tk.Frame(self._tk)
        bar.pack(fill="x", **pad)
        self._start_btn = tk.Button(bar, text="Start", width=12, command=self.start)
        self._stop_btn = tk.Button(bar, text="Stop", width=12, command=self.stop)
        self._flash_btn = tk.Button(
            bar, text="Update firmware", width=16, command=self.flash
        )
        self._web_btn = tk.Button(bar, text="Open web UI", width=14, command=self.open_web)
        for b in (self._start_btn, self._stop_btn, self._flash_btn, self._web_btn):
            b.pack(side="left", padx=(0, 6))

        # Wrapped, not horizontally scrolled: the lines that matter here are
        # long Windows paths and mpremote errors, and `see("end")` on an
        # unwrapped widget scrolls sideways too - parking the view on the
        # tail of the last path with the actual message off-screen left.
        self._log = scrolledtext.ScrolledText(
            self._tk, height=14, wrap="word", font=("Consolas", 9)
        )
        self._log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._log.configure(state="disabled")

    def _refresh_window(self) -> None:
        if not self._tk.winfo_viewable():
            return  # hidden: nothing to draw, and the log would churn
        self._summary.set("\n".join(summary_lines(self.health)))
        running = self.health.running
        self._start_btn.configure(state="disabled" if running else "normal")
        self._stop_btn.configure(
            state="normal" if self.sup.owns_process else "disabled"
        )
        self._flash_btn.configure(state="disabled" if self.sup.flashing else "normal")
        self._web_btn.configure(
            state="normal" if (running and web_url(self.config)) else "disabled"
        )

        text = self.sup.log_text()
        if text != getattr(self, "_shown_log", None):
            self._shown_log = text
            at_bottom = self._log.yview()[1] > 0.99
            self._log.configure(state="normal")
            self._log.delete("1.0", "end")
            self._log.insert("1.0", text)
            self._log.configure(state="disabled")
            if at_bottom:  # follow the tail, unless the user scrolled up
                self._log.see("end")

    def show_window(self) -> None:
        self._tk.deiconify()
        self._tk.lift()
        self._tk.focus_force()
        self._shown_log = None  # force a redraw of the log we skipped while hidden
        self._refresh_window()

    def hide_window(self) -> None:
        self._tk.withdraw()

    # --- the menu -----------------------------------------------------

    # pystray calls every dynamic property with the item itself, so each of
    # these takes (and ignores) one positional argument.

    def _status_slot(self, index: int) -> pystray.MenuItem:
        return pystray.MenuItem(
            lambda *_: (summary_lines(self.health) + [""] * _STATUS_SLOTS)[index],
            None,
            enabled=False,
            visible=lambda *_: index < len(summary_lines(self.health)),
        )

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            *[self._status_slot(i) for i in range(_STATUS_SLOTS)],
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start",
                self._on(self.start),
                visible=lambda *_: not self.health.running,
            ),
            pystray.MenuItem(
                "Stop", self._on(self.stop), visible=lambda *_: self.sup.owns_process
            ),
            pystray.MenuItem(
                "Open web UI",
                self._on(self.open_web),
                default=True,  # left-click does this
                visible=lambda *_: bool(self.health.running and web_url(self.config)),
            ),
            pystray.MenuItem(
                lambda *_: "Updating firmware..." if self.sup.flashing
                else "Update the button's firmware",
                self._on(self.flash),
                enabled=lambda *_: not self.sup.flashing,
            ),
            pystray.MenuItem(
                "Use the real button",
                self._on(self.toggle_ble),
                checked=lambda *_: self.sup.use_ble,
                # Changing it mid-run would lie about what is running, and
                # the service reads it only at launch.
                enabled=lambda *_: not self.health.running,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Status and log...", self._on(self.show_window)),
            pystray.MenuItem(
                # Say what Quit will do, rather than silently orphaning or
                # silently killing the service.
                lambda *_: "Quit (stops the service)" if self.sup.owns_process
                else "Quit",
                self._on(self.quit),
            ),
        )

    def _on(self, fn):
        """Wrap a menu callback so it runs on Tk's thread, not the tray's."""
        return lambda *_a: self._tk.after(0, fn)

    # --- actions ------------------------------------------------------

    def start(self) -> None:
        self.sup.start()
        self.show_window()  # the log is where a refused start explains itself
        self._tick(reschedule=False)

    def stop(self) -> None:
        self.sup.stop()
        self._tick(reschedule=False)

    def flash(self) -> None:
        if self.sup.flash():
            self.show_window()  # flashing fails in ways you need to read

    def toggle_ble(self) -> None:
        self.sup.set_use_ble(not self.sup.use_ble)
        self.sup.note(
            "--- Start will use "
            + ("the real button (BLE)" if self.sup.use_ble else "a simulated button")
            + " ---"
        )
        self._tick(reschedule=False)

    def open_web(self) -> None:
        url = web_url(self.config)
        if url:
            webbrowser.open(url)

    def quit(self) -> None:
        self._quitting = True
        if self.sup.owns_process:
            self.sup.stop()
        self.sup.close()
        self._icon.stop()
        self._tk.quit()

    # --- the poll loop ------------------------------------------------

    def _tick(self, reschedule: bool = True) -> None:
        if self._quitting:
            return
        try:
            self.health = self.sup.poll()
            level = self.health.level
            if level is not self._level:
                self._level = level
                self._icon.icon = status_dot(level)
                self._icon.title = f"Button control - {headline(self.health)}"
            # Cheap, and the labels depend on state this tick may have changed.
            self._icon.update_menu()
            self._refresh_window()
        except Exception:
            # The control panel watching a service must not need watching.
            log.exception("control panel tick failed")
        finally:
            if reschedule and not self._quitting:
                self._tk.after(POLL_MS, self._tick)

    def run(self) -> None:
        import threading

        threading.Thread(target=self._icon.run, daemon=True, name="tray").start()
        self._tk.after(0, self._tick)
        self._tk.mainloop()
