[CmdletBinding()]
param([string]$Output = "")

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Output) { $Output = Join-Path $Root 'exports/packages/VoxelCharacterFactory-source.zip' }
python (Join-Path $PSScriptRoot 'package_windows.py') --output $Output
if ($LASTEXITCODE -ne 0) { throw "Windows source packaging failed with exit code $LASTEXITCODE." }
