@echo off
title Meeting Watcher - Stopping

set "SCRIPT_DIR=%~dp0"
set "PID_FILE=%SCRIPT_DIR%data\watcher.pid"

if not exist "%PID_FILE%" (
    echo No watcher PID file found. Watcher may not be running.
    pause
    exit /b 0
)

set /p WATCHER_PID=<"%PID_FILE%"
echo Stopping Meeting Watcher (PID: %WATCHER_PID%)...

taskkill /PID %WATCHER_PID% /F >nul 2>&1
if errorlevel 1 (
    echo Process not found - watcher may have already stopped.
) else (
    echo Watcher stopped.
)

del "%PID_FILE%" >nul 2>&1
echo.
pause
