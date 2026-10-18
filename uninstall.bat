@echo off
rem Restores the original game files saved in backup\ by setup.bat.
cd /d "%~dp0"
if not exist "backup\Binaries\DMC-DevilMayCry.exe" (echo No backup found - use Steam "Verify integrity of game files". & pause & exit /b 1)
tasklist /FI "IMAGENAME eq DMC-DevilMayCry.exe" | find /I "DMC-DevilMayCry.exe" >nul && (echo Close the game first. & pause & exit /b 1)
copy /y "backup\CookedPCConsole\*.upk" "..\DevilGame\CookedPCConsole\" || goto :fail
copy /y "backup\Config\*.ini" "..\DevilGame\Config\" || goto :fail
copy /y "backup\Binaries\DMC-DevilMayCry.exe" "..\Binaries\Win32\DMC-DevilMayCry.exe" || goto :fail
if exist "..\Binaries\Win32\xinput1_3.dll" del "..\Binaries\Win32\xinput1_3.dll"
echo Original files restored.
pause
exit /b 0
:fail
echo Restore FAILED - use Steam "Verify integrity of game files" instead.
pause
exit /b 1
