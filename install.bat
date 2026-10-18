@echo off
rem Installs the CoopMod build over the game files (originals live in backup\). Run setup.bat first.
cd /d "%~dp0"
if not exist "build\Engine.upk" (echo Run setup.bat first. & pause & exit /b 1)
tasklist /FI "IMAGENAME eq DMC-DevilMayCry.exe" | find /I "DMC-DevilMayCry.exe" >nul && (echo Close the game first. & pause & exit /b 1)
copy /y "build\Engine.upk" "..\DevilGame\CookedPCConsole\Engine.upk" || goto :fail
copy /y "build\DevilGame.upk" "..\DevilGame\CookedPCConsole\DevilGame.upk" || goto :fail
copy /y "build\NTGameFramework.upk" "..\DevilGame\CookedPCConsole\NTGameFramework.upk" || goto :fail
copy /y "build\Dante_Archetypes_SF.upk" "..\DevilGame\CookedPCConsole\Dante_Archetypes_SF.upk" || goto :fail
copy /y "build\DefaultInput.ini" "..\DevilGame\Config\DefaultInput.ini" || goto :fail
copy /y "build\DMC-DevilMayCry.exe" "..\Binaries\Win32\DMC-DevilMayCry.exe" || goto :fail
if exist "build\xinput1_3.dll" copy /y "build\xinput1_3.dll" "..\Binaries\Win32\xinput1_3.dll"
echo CoopMod installed.
pause
exit /b 0
:fail
echo Install FAILED.
pause
exit /b 1
