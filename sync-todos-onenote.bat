@echo off
title Meeting Agent — Sync Todos to OneNote
color 0A

echo.
echo ============================================================
echo   Meeting Agent  ^|  Sync Latest Todos to OneNote
echo ============================================================
echo.

:: Move to project root
cd /d "C:\Users\10320283\OneDrive - BD\Documents\Github\meeting-followup-agent"

:: Run PowerShell sync script
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_onenote.ps1"

echo.
pause
