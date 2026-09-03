@echo off
setlocal
set "PLATFORM_ROOT=%~dp0.."
"%PLATFORM_ROOT%\web\backend\.venv\Scripts\python.exe" "%PLATFORM_ROOT%\scripts\datactl.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo datactl failed with exit code %EXIT_CODE%.
exit /b %EXIT_CODE%
