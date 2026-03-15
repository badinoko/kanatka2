@echo off
setlocal
cd /d "%~dp0"
set "MPLCONFIGDIR=%CD%\.mplconfig"
echo ========================================
echo  Симулятор камеры
echo  Подает фото из INBOX в incoming
echo  с реалистичными задержками
echo  (Ctrl+C для остановки)
echo ========================================
echo.
call ".\.venv\Scripts\python.exe" ".\tools\camera_simulator.py"
