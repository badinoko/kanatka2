@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe receiver\receiver_app.py
pause
