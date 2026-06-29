@echo off
title Meeting Watcher - Started
color 0A

set "SCRIPT_DIR=%~dp0"

:: Check if already running
tasklist /FI "IMAGENAME eq powershell.exe" /FI "WINDOWTITLE eq MeetingWatcher*" 2>nul | find /I "powershell" >nul
if not errorlevel 1 (
    echo Watcher is already running.
    pause
    exit /b 0
)

echo Starting Meeting Follow-Up Watcher in background...
echo It will automatically sync todos when a Teams meeting ends.
echo.
echo To stop: run stop-watcher.bat
echo Log file: data\watcher.log
echo.

:: Start hidden background PowerShell process
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
    "Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""%SCRIPT_DIR%meeting-watcher.ps1""' -PassThru | Select-Object -ExpandProperty Id | Set-Content ""%SCRIPT_DIR%data\watcher.pid"""

timeout /t 2 >nul

:: Verify it started
if exist "%SCRIPT_DIR%data\watcher.pid" (
    set /p PID=<"%SCRIPT_DIR%data\watcher.pid"
    echo Watcher started (PID: %PID%)
    echo Monitoring Teams meetings every 2 minutes.
) else (
    echo WARNING: Could not confirm watcher started.
)

pause
