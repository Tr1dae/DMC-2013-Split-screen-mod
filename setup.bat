@echo off
rem Backs up the original game files and builds the mod into build\ (does not touch the game).
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 is required: https://www.python.org/downloads/ & pause & exit /b 1)
python -I tools\setup.py || (echo Setup FAILED. & pause & exit /b 1)
pause
