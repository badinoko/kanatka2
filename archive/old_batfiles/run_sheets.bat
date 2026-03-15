@echo off
setlocal
cd /d "%~dp0"
set "MPLCONFIGDIR=%CD%\.mplconfig"
echo ========================================
echo  Сборка печатных листов
echo ========================================
echo.
call ".\.venv\Scripts\python.exe" ".\src\main.py" sheet
echo.
echo Готово!
pause
