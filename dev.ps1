# AI Button dev environment: mock hardware, web UI at http://localhost:8080
#   .\dev.ps1            mock GPIO + canned AI (fully offline)
#   .\dev.ps1 -RealAI    mock GPIO, but real Ollama backends (tests actual prompts)
param([switch]$RealAI)

$flags = @("-m", "aibutton.main", "--mock", "--no-ble", "--config", "$PSScriptRoot\config.json")
if ($RealAI) { $flags += "--real-ai" }
& "$PSScriptRoot\.venv\Scripts\python.exe" @flags
