@echo off
rem ============================================================================
rem  Salesforce Translation Handler -- Windows double-click launcher.
rem  Requires Python 3.9+ on PATH.
rem ============================================================================
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "STX_APP=%VENV_DIR%\Scripts\stx-app.exe"

rem --- If venv and app exist, launch immediately ---
if exist "%STX_APP%" (
    start "" "%STX_APP%"
    goto :eof
)

rem --- Venv exists but app missing (upgrade scenario) ---
if exist "%VENV_DIR%\Scripts\python.exe" (
    echo Virtual environment exists but stx-app is missing. Upgrading...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
    "%VENV_DIR%\Scripts\python.exe" -m pip install -e ".[gui]"
    if errorlevel 1 (
        echo.
        echo ERROR: Upgrade failed. Try deleting .venv and re-running this launcher.
        pause
        exit /b 1
    )
    if exist "%STX_APP%" (
        start "" "%STX_APP%"
        goto :eof
    )
    echo.
    echo ERROR: stx-app was not created after upgrade. Check the errors above.
    pause
    exit /b 1
)

rem --- No venv -- fresh setup ---
echo Setting up the virtual environment for the first run, please wait...

rem Locate Python
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
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
%PY% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo.
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

rem Install
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
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

start "" "%STX_APP%"
goto :eof

:py_missing
echo.
echo ERROR: Python was not found on PATH.
echo Install Python 3.9+ from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1
