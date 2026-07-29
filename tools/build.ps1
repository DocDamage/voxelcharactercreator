[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Job,
    [string]$Blender = $env:VCF_BLENDER,
    [switch]$NoCache,
    [ValidateSet('prepare','ingest','assemble_proxy','assemble_assets','resolve_parts','rig','align_sockets','rigid_bind','secondary_motion','animate','qa','render','optimize','export','godot_import')]
    [string]$RetryStage
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Blender) {
    $Candidates = Get-ChildItem -Path 'C:\Program Files\Blender Foundation' -Filter blender.exe -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    if ($Candidates) { $Blender = $Candidates[0].FullName }
}
if (-not $Blender) { throw 'Install Blender under C:\Program Files\Blender Foundation, or set -Blender/VCF_BLENDER to blender.exe.' }
if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) { throw "Blender executable not found: $Blender" }
$JobPath = Join-Path $Root $Job
if (-not (Test-Path -LiteralPath $JobPath -PathType Leaf)) { throw "Job not found: $Job" }
$WorkerArgs = @('--background', '--python', (Join-Path $Root 'blender_worker/process_character.py'), '--', '--job', $JobPath, '--project-root', $Root)
if ($NoCache) { $WorkerArgs += '--no-cache' }
if ($RetryStage) { $WorkerArgs += @('--retry-stage', $RetryStage) }
& $Blender @WorkerArgs
exit $LASTEXITCODE
