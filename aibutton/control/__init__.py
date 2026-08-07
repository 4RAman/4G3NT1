"""The control panel: a tray icon that starts, stops, watches and updates
the button service.

It sits *around* the service, never inside it - the web UI at :8080 is
served by the running service and so can never be what launches it. Nothing
in `aibutton/` imports this package; it imports the service, not the
reverse.
"""
