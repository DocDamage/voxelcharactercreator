[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Job,
    [string]$Blender = $env:VCF_BLENDER
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Blender) { throw 'Set -Blender or VCF_BLENDER to blender.exe.' }
if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) { throw "Blender executable not found: $Blender" }
$JobPath = Join-Path $Root $Job
if (-not (Test-Path -LiteralPath $JobPath -PathType Leaf)) { throw "Job not found: $Job" }
& $Blender --background --python (Join-Path $Root 'blender_worker/process_character.py') -- --job $JobPath --project-root $Root
exit $LASTEXITCODE
