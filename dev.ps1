# AI Button dev environment: MockDevice + web UI at http://localhost:8080
#   .\dev.ps1    the whole app against the in-memory device (fully offline)
& "$PSScriptRoot\.venv\Scripts\python.exe" -m aibutton.main --config "$PSScriptRoot\config.json"
