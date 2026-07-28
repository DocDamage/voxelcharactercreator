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
        & $BlenderExe --background --python (Join-Path $Root 'tests/blender/verify_phase4_animation.py')
        if ($LASTEXITCODE -ne 0) { throw "Blender Phase 4 animation/QA verification failed with exit code $LASTEXITCODE." }
    }
    if ($Visual) {
        & (Join-Path $Root 'tools/build.ps1') -Job 'characters/original/heavy_sword_hero.json'
        if ($LASTEXITCODE -ne 0) { throw "Phase 4 visual build failed with exit code $LASTEXITCODE." }
        $VisualFiles = Get-ChildItem (Join-Path $Root 'exports/original/heavy_sword_hero') -Filter 'original_heavy_sword_hero_*.png'
        if ($VisualFiles.Count -lt 17) { throw "Expected at least 17 Phase 4 preview images; found $($VisualFiles.Count)." }
    }
    if ($Godot) {
        $GodotExe = $env:VCF_GODOT
        if (-not $GodotExe) {
            $GodotCommand = Get-Command godot.exe -ErrorAction SilentlyContinue
            if ($GodotCommand) {
                $GodotExe = $GodotCommand.Source
                $ResolvedGodot = (Get-Item -LiteralPath $GodotExe).Target
                if ($ResolvedGodot) {
                    $ConsoleGodot = Get-ChildItem -LiteralPath (Split-Path $ResolvedGodot -Parent) -Filter '*console.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
                    if ($ConsoleGodot) { $GodotExe = $ConsoleGodot.FullName }
                }
            }
        }
        if ($GodotExe -and (Test-Path -LiteralPath $GodotExe -PathType Leaf)) {
            $GodotItem = Get-Item -LiteralPath $GodotExe
            $ResolvedGodot = $GodotItem.Target
            if (-not $ResolvedGodot) { $ResolvedGodot = $GodotItem.FullName }
            $ConsoleGodot = Get-ChildItem -LiteralPath (Split-Path $ResolvedGodot -Parent) -Filter '*console.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($ConsoleGodot) { $GodotExe = $ConsoleGodot.FullName }
        }
        if (-not $GodotExe -or -not (Test-Path -LiteralPath $GodotExe -PathType Leaf)) { throw 'Set VCF_GODOT to Godot 4.6.2 or newer before running -Godot.' }
        $Export = Join-Path $Root 'exports/original/heavy_sword_hero/original_heavy_sword_hero.glb'
        if (-not (Test-Path -LiteralPath $Export -PathType Leaf)) {
            & (Join-Path $Root 'tools/build.ps1') -Job 'characters/original/heavy_sword_hero.json'
            if ($LASTEXITCODE -ne 0) { throw "Pilot build failed with exit code $LASTEXITCODE." }
        }
        Copy-Item -LiteralPath $Export -Destination (Join-Path $Root 'tests/godot/imported/character.glb') -Force
        $GodotProject = Join-Path $Root 'tests/godot'
        & $GodotExe --headless --editor --path $GodotProject --import
        if ($LASTEXITCODE -ne 0) { throw "Godot GLB import failed with exit code $LASTEXITCODE." }
        & $GodotExe --headless --path $GodotProject --script (Join-Path $GodotProject 'verify_import.gd')
        if ($LASTEXITCODE -ne 0) { throw "Godot scene verification failed with exit code $LASTEXITCODE." }
    }
}
finally {
    Pop-Location
}
