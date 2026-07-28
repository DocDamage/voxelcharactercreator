[CmdletBinding()]
param(
    [switch]$Unit,
    [switch]$Blender,
    [switch]$Godot,
    [switch]$Visual,
    [switch]$Performance
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    if (-not ($Blender -or $Godot -or $Visual -or $Performance) -or $Unit) {
        python -m compileall -q app blender_worker tools tests vcf_core
        python tools/generate_pilot_assets.py --check
        python tools/validate.py
        python tools/scan_secrets.py
        python -m unittest discover -v
    }
    if ($Performance) {
        New-Item -ItemType Directory -Path (Join-Path $Root 'logs') -Force | Out-Null
        python tools/benchmark_vox.py --output (Join-Path $Root 'logs/vox-mesh-benchmark.json')
        $BlenderExe = $env:VCF_BLENDER
        if (-not $BlenderExe) {
            $Candidates = Get-ChildItem -Path 'C:\Program Files\Blender Foundation' -Filter blender.exe -Recurse -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending
            if ($Candidates) { $BlenderExe = $Candidates[0].FullName }
        }
        if ($BlenderExe -and (Test-Path -LiteralPath $BlenderExe -PathType Leaf)) {
            $env:VCF_BENCHMARK_OUTPUT = Join-Path $Root 'logs/vox-blender-benchmark.json'
            & $BlenderExe --background --python (Join-Path $Root 'tests/blender/benchmark_vox_import.py')
            if ($LASTEXITCODE -ne 0) { throw "Blender VOX benchmark failed with exit code $LASTEXITCODE." }
            Remove-Item Env:VCF_BENCHMARK_OUTPUT -ErrorAction SilentlyContinue
        }
    }
    if ($Blender) {
        $BlenderExe = $env:VCF_BLENDER
        if (-not $BlenderExe) {
            $Candidates = Get-ChildItem -Path 'C:\Program Files\Blender Foundation' -Filter blender.exe -Recurse -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending
            if ($Candidates) { $BlenderExe = $Candidates[0].FullName }
        }
        if (-not $BlenderExe -or -not (Test-Path -LiteralPath $BlenderExe -PathType Leaf)) {
            throw 'Set VCF_BLENDER to blender.exe before running -Blender.'
        }
        & $BlenderExe --background --python (Join-Path $Root 'tests/blender/verify_vox_import.py')
        if ($LASTEXITCODE -ne 0) { throw "Blender VOX integration verification failed with exit code $LASTEXITCODE." }
        & $BlenderExe --background --python (Join-Path $Root 'tests/blender/verify_asset_assembly.py')
        if ($LASTEXITCODE -ne 0) { throw "Blender asset-assembly integration verification failed with exit code $LASTEXITCODE." }
        & $BlenderExe --background --python (Join-Path $Root 'tests/blender/verify_phase3_rig.py')
        if ($LASTEXITCODE -ne 0) { throw "Blender Phase 3 rig integration verification failed with exit code $LASTEXITCODE." }
    }
    foreach ($Deferred in @($Godot, $Visual)) {
        if ($Deferred) {
            throw 'This verification mode has no implementation yet. It is gated on the Phase 1-4 integration work.'
        }
    }
}
finally {
    Pop-Location
}
