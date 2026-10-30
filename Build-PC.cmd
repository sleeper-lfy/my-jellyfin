@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package-pc.ps1"
set "LUMEN_BUILD_EXIT=%ERRORLEVEL%"
if not "%LUMEN_BUILD_EXIT%"=="0" echo Build failed. Read the log path above. Existing packages may be from an older build.
pause
exit /b %LUMEN_BUILD_EXIT%
