@echo off
rem ============================================================================
rem  Salesforce Translation Handler -- Windows double-click launcher.
rem  Requires Python 3.9+ on PATH.
rem
rem  How to update the app:
rem    1. Open a terminal in this folder and run: git pull
rem    2. Double-click this launcher -- it will reinstall automatically.
rem ============================================================================
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "STX_APP=%VENV_DIR%\Scripts\stx-app.exe"
set "STAMP_FILE=%VENV_DIR%\.install_stamp"

rem ===========================================================================
rem SECTION 1: Locate Python (needed for both fresh setup and reinstall)
rem ===========================================================================
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)

rem ===========================================================================
rem SECTION 2: No venv at all -- full fresh setup
rem ===========================================================================
if not exist "%VENV_DIR%\Scripts\python.exe" goto :fresh_setup

rem ===========================================================================
rem SECTION 3: Venv exists -- check if pyproject.toml changed since last install
rem ===========================================================================
rem Compare pyproject.toml modification timestamp against our stamp file.
rem If pyproject.toml is newer, reinstall so new dependencies are picked up.
set "NEED_REINSTALL=0"

if not exist "%STX_APP%" (
    set "NEED_REINSTALL=1"
    echo [launcher] stx-app.exe not found -- will reinstall.
)

if exist "pyproject.toml" if exist "%STAMP_FILE%" (
    rem Use xcopy /D to test if pyproject.toml is newer than the stamp file.
    rem /D:MM-DD-YYYY compares dates; we use xcopy /D to a temp to detect newer.
    for %%F in ("pyproject.toml") do set "TOML_DATE=%%~tF"
    for %%F in ("%STAMP_FILE%") do set "STAMP_DATE=%%~tF"
    if "!TOML_DATE!" GTR "!STAMP_DATE!" set "NEED_REINSTALL=1"
)

if not exist "%STAMP_FILE%" set "NEED_REINSTALL=1"

if "!NEED_REINSTALL!"=="1" (
    echo [launcher] Source has changed -- reinstalling dependencies...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
    "%VENV_DIR%\Scripts\python.exe" -m pip install -e ".[gui]"
    if errorlevel 1 (
        echo.
        echo ERROR: Reinstall failed. See messages above.
        echo Try deleting the .venv folder and running this launcher again.
        pause
        exit /b 1
    )
    rem Write a new stamp file so we know when the last install happened.
    echo %DATE% %TIME% > "%STAMP_FILE%"
    echo [launcher] Reinstall complete.
)

rem ===========================================================================
rem SECTION 4: Launch
rem ===========================================================================
if not exist "%STX_APP%" (
    echo.
    echo ERROR: stx-app.exe still not found after reinstall.
    echo The GUI extra may have failed to install. See messages above.
    pause
    exit /b 1
)

start "" "%STX_APP%"
goto :eof

rem ===========================================================================
rem SECTION 5: Fresh setup (no venv)
rem ===========================================================================
:fresh_setup
echo ============================================================
echo  Salesforce Translation Handler -- First-time setup
echo  This may take a few minutes. Please wait.
echo ============================================================
echo.

if not defined PY goto :py_missing

rem Check Python version (must be 3.9+)
for /f "tokens=2 delims= " %%v in ('%PY% --version 2^>^&1') do set "PY_VER=%%v"
echo Detected Python %PY_VER%

%PY% -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: Python 3.9 or newer is required. Found: %PY_VER%
    echo Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

rem Create venv
echo Creating virtual environment...
%PY% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo.
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

rem Install dependencies
echo Installing dependencies (this takes a few minutes the first time)...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
"%VENV_DIR%\Scripts\python.exe" -m pip install -e ".[gui]"
if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed. See messages above.
    echo You may need to delete .venv and try again.
    pause
    exit /b 1
)

if not exist "%STX_APP%" (
    echo.
    echo ERROR: Setup completed but stx-app.exe was not created.
    echo The GUI extra may have failed to install. See errors above.
    pause
    exit /b 1
)

rem Write stamp file
echo %DATE% %TIME% > "%STAMP_FILE%"
echo.
echo ============================================================
echo  Setup complete! Launching app...
echo ============================================================

start "" "%STX_APP%"
goto :eof

:py_missing
echo.
echo ERROR: Python was not found on PATH.
echo Install Python 3.9+ from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1
