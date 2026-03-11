@echo off
echo Building GameTracker Agent...
echo.

cd /d "%~dp0"

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Build with PyInstaller
echo Building executable...
pyinstaller --onefile --name GameTrackerAgent --icon=NONE --add-data "requirements.txt;." agent.py

echo.
echo Build complete! Executable is in dist\GameTrackerAgent.exe
pause
