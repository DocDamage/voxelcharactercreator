[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    python tools/validate.py
    if ($LASTEXITCODE -ne 0) { throw "Project validation failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}
