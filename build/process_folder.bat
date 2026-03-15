@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo   PhotoSelector — Batch Processing
echo ========================================
echo.

if "%~1"=="" (
    echo Usage: process_folder.bat "D:\path\to\photos"
    echo.
    echo This will process all photos in the specified folder.
    echo Results will appear in workdir\selected\ and workdir\sheets\
    echo.
    echo You can also just copy photos into workdir\incoming\
    echo and use the Start button in the web interface.
    echo.
    pause
    exit /b 1
)

echo Processing folder: %~1
echo.
"PhotoSelector.exe" process --source "%~1"
echo.
echo Done! Open PhotoSelector to see results.
pause
