@echo off
setlocal
cd /d "%~dp0"
set "MPLCONFIGDIR=%CD%\.mplconfig"
echo ========================================
echo  Мониторинг папки incoming
echo  (Ctrl+C для остановки)
echo ========================================
echo.
call ".\.venv\Scripts\python.exe" ".\src\main.py" watch
