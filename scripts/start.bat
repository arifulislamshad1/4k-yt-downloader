@echo off
title YT Downloader Helper
cd /d "%~dp0.."
where py >nul 2>nul || (echo Python launcher "py" was not found. Install Python from python.org and tick "Add python.exe to PATH". & pause & exit /b 1)
py -3 helper\server.py %*
if errorlevel 1 pause
