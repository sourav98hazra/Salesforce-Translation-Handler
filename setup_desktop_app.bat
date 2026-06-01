@echo off
REM ===========================================================================
REM  Salesforce Translation Manager - one-click desktop setup (Windows)
REM
REM  Double-click this file ONCE.  It will:
REM    1. Create a Python virtual environment (.venv) if one doesn't exist
REM    2. Install the app + GUI dependencies + PyInstaller
REM    3. Build a standalone SalesforceTranslationHandler.exe in dist\
REM    4. Put a "Salesforce Translation Manager" shortcut (with the app
REM       logo) on your Desktop
REM
REM  After it finishes, just double-click the Desktop shortcut to launch
REM  the app - no terminal, no Python knowledge needed.
REM
REM  Requirement: Python 3.9+ installed and on PATH (https://python.org).
REM ===========================================================================

setlocal enabledelayedexpansion

REM Always operate from the folder this script lives in (the repo root),
REM so it doesn't matter where the user double-clicks it from.
cd /d "%~dp0"

echo ============================================================
echo   Salesforce Translation Manager - Desktop Setup
echo ============================================================
echo.

REM --- 1. Locate a Python launcher -------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo ERROR: Python was not found on your PATH.
    echo Install Python 3.9 or newer from https://www.python.org/downloads/
    echo and make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

REM Check Python version
%PY% -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.9 or newer is required.
    echo Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- 2. Check for existing setup ---
if exist "dist\SalesforceTranslationHandler.exe" (
    echo [1/4] Existing installation detected. Upgrading dependencies...
    if exist ".venv\Scripts\python.exe" (
        set "VENV_PY=.venv\Scripts\python.exe"
        "%VENV_PY%" -m pip install --upgrade pip >nul 2>nul
        "%VENV_PY%" -m pip install -e ".[gui]" pyinstaller
        goto :build_step
    )
)
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo ERROR: failed to create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment already exists - reusing it.
)

set "VENV_PY=.venv\Scripts\python.exe"

REM --- 3. Install dependencies ----------------------------------------------
echo [2/4] Installing dependencies ^(first run may take a few minutes^)...
"%VENV_PY%" -m pip install --upgrade pip >nul 2>nul
"%VENV_PY%" -m pip install -e ".[gui]" pyinstaller
if errorlevel 1 (
    echo ERROR: dependency installation failed. See messages above.
    pause
    exit /b 1
)

:build_step
REM --- 4. Build the standalone executable -----------------------------------
echo [3/4] Building the standalone application ^(this can take a minute^)...
"%VENV_PY%" build_exe.py
if errorlevel 1 (
    echo ERROR: the build failed. See messages above.
    pause
    exit /b 1
)

REM --- 5. Create the Desktop shortcut ---------------------------------------
echo [4/4] Creating the Desktop shortcut...
"%VENV_PY%" scripts\create_shortcut.py --target exe
if errorlevel 1 (
    echo WARNING: the shortcut could not be created, but the .exe was built.
    echo You can find it in the dist\ folder and create a shortcut manually.
    pause
    exit /b 0
)

echo.
echo ============================================================
echo   All done!
echo.
echo   A "Salesforce Translation Manager" shortcut is now on
echo   your Desktop.  Double-click it to launch the app.
echo ============================================================
echo.
pause
