@echo off
rem Builds CoopMod's xinput1_3.dll (32-bit) into ..\build\.
setlocal
cd /d "%~dp0"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
cl /nologo /O2 /W3 /MT /LD xinput_proxy.c /Fe..\build\xinput1_3.dll /Fo..\build\_obj\ /link /DEF:xinput_proxy.def /NOLOGO || exit /b 1
del ..\build\xinput1_3.exp ..\build\xinput1_3.lib 2>nul
echo built ..\build\xinput1_3.dll
