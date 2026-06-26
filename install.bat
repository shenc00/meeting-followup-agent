@echo off
setlocal EnableDelayedExpansion

title Meeting Follow-Up Agent — Installer
echo.
echo ============================================================
echo   Meeting Follow-Up Agent  ^|  One-Click Installer
echo ============================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────
echo [1/6] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if !PY_MAJOR! LSS 3 (
    echo ERROR: Python 3.11+ required. Found !PY_VER!
    pause
    exit /b 1
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 11 (
    echo ERROR: Python 3.11+ required. Found !PY_VER!
    pause
    exit /b 1
)
echo        OK — Python !PY_VER!

:: ── 2. Create virtual environment ────────────────────────────
echo.
echo [2/6] Creating virtual environment (.venv)...
if exist .venv (
    echo        .venv already exists — skipping creation.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo        Created .venv
)

:: ── 3. Activate venv ──────────────────────────────────────────
echo.
echo [3/6] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Could not activate .venv\Scripts\activate.bat
    pause
    exit /b 1
)
echo        Activated

:: ── 4. Upgrade pip ───────────────────────────────────────────
echo.
echo [4/6] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo        Done

:: ── 5. Install dependencies ───────────────────────────────────
echo.
echo [5/6] Installing dependencies...
pip install -e . --quiet
if errorlevel 1 (
    echo ERROR: Dependency installation failed. Check requirements.txt and try again.
    pause
    exit /b 1
)
echo        All packages installed

:: ── 6. First-time config setup ───────────────────────────────
echo.
echo [6/6] Setting up configuration...
if not exist config\config.yaml (
    if exist config\config.yaml.example (
        copy config\config.yaml.example config\config.yaml >nul
        echo        config\config.yaml created from example.
        echo        ^>^> IMPORTANT: Edit config\config.yaml and add your credentials.
    ) else (
        echo        WARNING: config\config.yaml.example not found.
    )
) else (
    echo        config\config.yaml already exists — skipping.
)

:: Create data directory
if not exist data mkdir data

:: ── Done ──────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Installation complete!
echo ============================================================
echo.
echo   Next steps:
echo     1. Edit config\config.yaml  — add your Microsoft 365 and OpenAI credentials
echo     2. Run:  meeting-agent auth  — authenticate with Microsoft Graph
echo     3. Run:  meeting-agent process --all  — process pending meetings
echo     4. Run:  meeting-agent dashboard  — view open actions
echo.
echo   The 'meeting-agent' command is available in this terminal.
echo   To use it in a new terminal, activate the venv first:
echo     .venv\Scripts\activate
echo.
pause
