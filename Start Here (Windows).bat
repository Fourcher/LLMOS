@echo off
rem LLM OS Setup: double-click this file to start.
title LLM OS Setup
if not exist "%~dp0Support files\dist\setup\start.ps1" goto unzip
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Support files\dist\setup\start.ps1"
if errorlevel 1 pause
exit /b

:unzip
echo.
echo   Unzip the LLM OS folder first: right-click the zip file, choose
echo   "Extract All...", then open Start Here inside the folder it makes.
echo.
pause
