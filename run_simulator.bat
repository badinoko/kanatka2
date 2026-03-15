@echo off
setlocal
cd /d "%~dp0"
set "MPLCONFIGDIR=%CD%\.mplconfig"
echo.
echo ========================================
echo   Camera Simulator
echo   INBOX -^> incoming
echo   (Ctrl+C to stop)
echo ========================================
echo.
call ".\.venv\Scripts\python.exe" ".\tools\camera_simulator.py" %*
echo.
echo ========================================
echo   Done.
echo ========================================
pause
