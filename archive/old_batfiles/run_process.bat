@echo off
setlocal
cd /d "%~dp0"
set "MPLCONFIGDIR=%CD%\.mplconfig"
echo ========================================
echo  Обработка папки с фото
echo ========================================
echo.
call ".\.venv\Scripts\python.exe" ".\src\main.py" process --save-annotations
echo.
echo Готово!
pause
