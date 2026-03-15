@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo  Запуск тестов
echo ========================================
echo.
call ".\.venv\Scripts\python.exe" -m unittest discover -s tests -p "test_*.py" -v
echo.
pause
