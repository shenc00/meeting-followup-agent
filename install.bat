@echo off
setlocal EnableDelayedExpansion

title Meeting Follow-Up Agent ? Installer
echo.
echo ============================================================
echo   Meeting Follow-Up Agent  ^|  One-Click Installer
echo ============================================================
echo.

:: ?? 1. Locate or auto-install Python ?????????????????????????
echo [1/6] Checking Python...
call :FIND_PYTHON
if "!PYTHON_CMD!"=="" (
    echo        Python not found. Attempting automatic installation...
    call :INSTALL_PYTHON
    call :FIND_PYTHON
    if "!PYTHON_CMD!"=="" (
        echo.
        echo ERROR: Automatic Python installation failed.
        echo        Please install Python 3.11+ manually from https://python.org
        echo        then rerun this script.
        pause
        exit /b 1
    )
)

:: Version gate
for /f "tokens=2 delims= " %%v in ('!PYTHON_CMD! --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if !PY_MAJOR! LSS 3 goto :VERSION_ERR
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 11 goto :VERSION_ERR
echo        OK ? Python !PY_VER! ^(!PYTHON_CMD!^)
goto :AFTER_PYTHON

:VERSION_ERR
echo        Python !PY_VER! is too old. Attempting to install a newer version...
call :INSTALL_PYTHON
call :FIND_PYTHON
if "!PYTHON_CMD!"=="" (
    echo ERROR: Could not install a supported Python. Install 3.11+ from https://python.org
    pause
    exit /b 1
)

:AFTER_PYTHON

:: ?? 2. Ensure pip is available ???????????????????????????????
echo.
echo [2/6] Ensuring pip is available...
!PYTHON_CMD! -m pip --version >nul 2>&1
if errorlevel 1 (
    echo        pip missing ? bootstrapping via ensurepip...
    !PYTHON_CMD! -m ensurepip --upgrade
    if errorlevel 1 (
        echo        ensurepip failed ? downloading get-pip.py...
        powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'"
        !PYTHON_CMD! "%TEMP%\get-pip.py" --quiet
        if errorlevel 1 (
            echo ERROR: Could not install pip. Check your internet connection.
            pause
            exit /b 1
        )
    )
)
!PYTHON_CMD! -m pip install --upgrade pip --quiet 2>nul
echo        pip OK

:: ── Enable Windows long paths (avoids MAX_PATH errors in deep packages) ──────
echo.
echo [2b] Enabling Windows long path support...
powershell -NoProfile -Command ^
    "Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled' -Value 1 -Type DWord -ErrorAction SilentlyContinue"
!PYTHON_CMD! -m pip config set global.no-cache-dir false >nul 2>&1

:: ── 3. Create virtual environment ────────────────────────────
echo.
echo [3/6] Creating virtual environment (.venv)...
if exist .venv (
    echo        .venv already exists ? skipping creation.
) else (
    !PYTHON_CMD! -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo        Created .venv
)

:: ?? 4. Activate venv ?????????????????????????????????????????
echo.
echo [4/6] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Could not activate .venv. Check write permissions on this folder.
    pause
    exit /b 1
)
echo        Activated

:: ?? 5. Install all dependencies ??????????????????????????????
echo.
echo [5/6] Installing dependencies (this may take a minute)...
python -m pip install --upgrade pip --quiet 2>nul
python -m pip install -e . 2>&1
if errorlevel 1 (
    echo.
    echo        Retrying with verbose output for diagnosis...
    python -m pip install -e . --verbose
    if errorlevel 1 (
        echo ERROR: Dependency installation failed. See output above.
        pause
        exit /b 1
    )
)
echo        All packages installed successfully

:: ?? 6. First-time config and data directory ??????????????????
echo.
echo [6/6] Setting up configuration...
if not exist data mkdir data
if not exist config\config.yaml (
    if exist config\config.yaml.example (
        copy config\config.yaml.example config\config.yaml >nul
        echo        config\config.yaml created from template.
        echo        ^>^> ACTION REQUIRED: Edit config\config.yaml and add your credentials.
    ) else (
        echo        WARNING: config\config.yaml.example not found.
    )
) else (
    echo        config\config.yaml already exists ? skipping.
)

:: ?? Done ?????????????????????????????????????????????????????
echo.
echo ============================================================
echo   Installation complete!
echo ============================================================
echo.
echo   Next steps:
echo     1. Edit config\config.yaml  ? add Microsoft 365 + OpenAI credentials
echo     2. Run:  meeting-agent auth           ? authenticate with Microsoft Graph
echo     3. Run:  meeting-agent process --all  ? process pending meetings
echo     4. Run:  meeting-agent dashboard      ? view open actions
echo.
echo   To use in a new terminal, activate the venv first:
echo     .venv\Scripts\activate
echo.
pause
goto :EOF


:: ???????????????????????????????????????????????????????????????
:: SUBROUTINES
:: ???????????????????????????????????????????????????????????????

:FIND_PYTHON
set PYTHON_CMD=
py --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('py --version 2^>^&1') do set _VER=%%v
    if not "!_VER!"=="" ( set PYTHON_CMD=py & goto :EOF )
)
python --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set _VER=%%v
    if not "!_VER!"=="" ( set PYTHON_CMD=python & goto :EOF )
)
python3 --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims= " %%v in ('python3 --version 2^>^&1') do set _VER=%%v
    if not "!_VER!"=="" ( set PYTHON_CMD=python3 & goto :EOF )
)
goto :EOF


:INSTALL_PYTHON
:: Strategy 1 ? winget (Windows 10 1709+ / Windows 11)
winget --version >nul 2>&1
if not errorlevel 1 (
    echo        Installing via winget...
    winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 (
        for /f "tokens=*" %%p in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"PATH\",\"Machine\")+\";\"+ [Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do set "PATH=%%p"
        echo        Python installed via winget.
        goto :EOF
    )
)
:: Strategy 2 ? direct download from python.org
echo        Downloading Python 3.12.7 installer...
set _PY_EXE=%TEMP%\python-3.12.7-amd64.exe
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '!_PY_EXE!'"
if not exist "!_PY_EXE!" ( echo        Download failed. & goto :EOF )
echo        Running silent installer...
"!_PY_EXE!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
for /f "tokens=*" %%p in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"PATH\",\"Machine\")+\";\"+ [Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do set "PATH=%%p"
del /f /q "!_PY_EXE!" >nul 2>&1
echo        Python 3.12 installed.
goto :EOF
