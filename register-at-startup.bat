@echo off
title Register Meeting Watcher at Windows Startup

set "SCRIPT_DIR=%~dp0"
set "WATCHER_PS1=%SCRIPT_DIR%meeting-watcher.ps1"
set "TASK_NAME=MeetingFollowUpWatcher"

echo.
echo ============================================
echo  Register Meeting Watcher at Login
echo ============================================
echo.
echo This creates a Windows Task Scheduler entry that
echo automatically starts the watcher when you log in.
echo.
echo Task: %TASK_NAME%
echo Script: %WATCHER_PS1%
echo.

:: Create the scheduled task (runs at user login, hidden window)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"' + '%WATCHER_PS1%' + '\"');" ^
    "$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME;" ^
    "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit '23:00:00' -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5);" ^
    "Register-ScheduledTask -TaskName '%TASK_NAME%' -Action $action -Trigger $trigger -Settings $settings -Description 'Auto-syncs meeting todos to OneNote after Teams meetings end' -Force | Out-Null;" ^
    "Write-Host 'Task registered successfully.'"

echo.
echo Done. The watcher will now start automatically at every login.
echo To remove: schtasks /Delete /TN "%TASK_NAME%" /F
echo To start now without rebooting: run start-watcher.bat
echo.
pause
