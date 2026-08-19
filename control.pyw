# Double-click this to get the tray control panel.
#
# .pyw so Windows runs it with pythonw.exe and no console window appears -
# the whole point of a tray app is that it has no terminal behind it. Uses
# the project's venv rather than whatever `python` happens to mean, so a
# desktop shortcut works without activating anything first.
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv" / ("Scripts/pythonw.exe" if sys.platform == "win32" else "bin/python")

python = str(VENV) if VENV.exists() else sys.executable

# Launch and leave, rather than waiting for the panel to exit. Waiting kept a
# second pythonw alive for the whole session with the *same* command line as
# the panel itself, which is a genuinely confusing thing to meet in Task
# Manager when you are already trying to work out why there seem to be two of
# something. Nothing reads this process's exit code - it is a double-click
# target - so there is nothing to stay alive for.
subprocess.Popen([python, "-m", "aibutton.control", *sys.argv[1:]], cwd=str(ROOT))
