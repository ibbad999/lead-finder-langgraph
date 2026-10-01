@echo off
REM One-click launcher for the Lead Finder dashboard.
REM Double-click this file (or run it from PowerShell/cmd) - it activates
REM the venv, starts the server, and opens your browser automatically.

cd /d %~dp0

if not exist venv\Scripts\activate.bat (
    echo Could not find venv\Scripts\activate.bat
    echo Run this from the project root, after creating your virtual environment.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python dashboard\server.py

pause
