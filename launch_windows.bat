@echo off
cd /d "%~dp0"
py -3 -m app.main
if errorlevel 1 pause
