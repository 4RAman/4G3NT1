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
sys.exit(
    subprocess.call([python, "-m", "aibutton.control", *sys.argv[1:]], cwd=str(ROOT))
)
