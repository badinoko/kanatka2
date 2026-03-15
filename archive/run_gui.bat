@echo off
setlocal
cd /d "%~dp0"
set "MPLCONFIGDIR=%CD%\.mplconfig"
echo Starting PhotoSelector...
call ".\.venv\Scripts\python.exe" ".\src\main.py"
