@echo off
setlocal
cd /d "%~dp0"

set "VCF_PYTHON="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info ^>= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "VCF_PYTHON=py -3"
)
if not defined VCF_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info ^>= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "VCF_PYTHON=python"
    )
)

if not defined VCF_PYTHON (
    echo Python 3.11 or newer is required. Install Python from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

%VCF_PYTHON% -m app.main
set "VCF_EXIT_CODE=%ERRORLEVEL%"
if not "%VCF_EXIT_CODE%"=="0" (
    echo Voxel Character Factory exited with code %VCF_EXIT_CODE%.
    pause
)
exit /b %VCF_EXIT_CODE%
