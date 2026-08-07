<#
.SYNOPSIS
    Create (or remove) Desktop and Start Menu shortcuts for the tray control panel.

.DESCRIPTION
    The shortcut points at the venv's pythonw.exe, not python.exe: pythonw has
    no console, which is the entire point of a tray app - python.exe would
    leave a black window sitting behind it for the life of the session.

    It targets the interpreter directly rather than control.pyw, because a
    .pyw shortcut depends on the machine's .pyw file association pointing at a
    Python that has this project's dependencies. Naming the interpreter makes
    the shortcut work regardless of what else is installed.

.EXAMPLE
    .\tools\install_shortcuts.ps1
    .\tools\install_shortcuts.ps1 -Remove
    .\tools\install_shortcuts.ps1 -DesktopOnly
#>
[CmdletBinding()]
param(
    [switch]$Remove,
    [switch]$DesktopOnly,
    [switch]$StartMenuOnly
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Name = 'Button Control.lnk'

$Desktop = [Environment]::GetFolderPath('Desktop')
$StartMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'

$targets = @()
if (-not $StartMenuOnly) { $targets += (Join-Path $Desktop $Name) }
if (-not $DesktopOnly) { $targets += (Join-Path $StartMenu $Name) }

if ($Remove) {
    foreach ($t in $targets) {
        if (Test-Path $t) { Remove-Item $t -Force; Write-Host "removed  $t" }
        else { Write-Host "not there $t" }
    }
    return
}

$Pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $Pythonw)) {
    throw "no venv at $Pythonw - create it first: python -m venv .venv"
}

# Draw the .ico from the same code the tray uses, so the shortcut and the
# window cannot drift apart. Cosmetic: a failure here still leaves a working
# shortcut with the default Python icon.
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$IconPath = Join-Path $Root 'aibutton\control\button.ico'
try {
    & $Python -c "from pathlib import Path; from aibutton.control.icon import ensure_ico; print(ensure_ico(Path(r'$Root') / 'aibutton' / 'control'))" | Out-Null
} catch {
    Write-Warning "could not generate the icon: $_"
}

$shell = New-Object -ComObject WScript.Shell
foreach ($t in $targets) {
    $parent = Split-Path -Parent $t
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }

    $lnk = $shell.CreateShortcut($t)
    $lnk.TargetPath = $Pythonw
    $lnk.Arguments = '-m aibutton.control'
    $lnk.WorkingDirectory = $Root
    $lnk.Description = 'Start, watch and update the button service'
    $lnk.WindowStyle = 7          # minimised: there is no window to show
    if (Test-Path $IconPath) { $lnk.IconLocation = "$IconPath,0" }
    $lnk.Save()
    Write-Host "created  $t"
}

Write-Host ''
Write-Host 'Launch it from the Start Menu or the desktop; it appears as a tray icon.'
Write-Host 'Remove again with:  .\tools\install_shortcuts.ps1 -Remove'
