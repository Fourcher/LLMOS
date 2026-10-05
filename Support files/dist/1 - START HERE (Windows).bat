@echo off
rem LLM OS Setup for Windows - double-click this file to start.
rem
rem If Windows shows "Windows protected your PC": click "More info", then "Run anyway".
title LLM OS Setup
cd /d "%~dp0"
echo.
echo   LLM OS Setup
echo   ------------
echo   Starting the setup page in your web browser...
echo.

rem Find a Python 3 that really runs ("python" on a fresh Windows is only a shortcut to the Store).
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% "setup\llmos-setup.py"
if errorlevel 1 pause
goto :eof

:nopython
echo   One thing first: this setup needs Python 3, which is free.
echo.
where winget >nul 2>nul
if errorlevel 1 goto manual
choice /C YN /M "  Install Python 3 now with Windows' own package manager (winget)"
if errorlevel 2 goto manual
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
echo.
echo   Done. Double-click this START HERE file again to continue.
pause
goto :eof

:manual
echo   Download it from https://www.python.org/downloads/ (the page opens now).
echo   While installing, tick "Add python.exe to PATH". Then double-click this
echo   START HERE file again.
start "" "https://www.python.org/downloads/"
pause
