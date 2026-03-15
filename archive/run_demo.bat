@echo off
setlocal
cd /d "%~dp0"
set "MPLCONFIGDIR=%CD%\.mplconfig"
echo Running folder processing (console mode)...
call ".\.venv\Scripts\python.exe" ".\src\main.py" process --save-annotations
echo.
pause
