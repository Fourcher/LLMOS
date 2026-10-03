@echo off
rem Windows: double-click to open the LLM OS Exporter (needs Python 3 from python.org or the Microsoft Store)
cd /d "%~dp0exporter"
where py >nul 2>nul && (py -3 exporter.py) || (python exporter.py)
if errorlevel 1 (echo Python 3 is needed: https://www.python.org/downloads/ & pause)
