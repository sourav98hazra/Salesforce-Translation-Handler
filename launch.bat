@echo off
rem ============================================================================
rem  Salesforce Translation Handler -- Windows double-click launcher.
rem
rem  First run: creates a virtual environment and installs the app.  Subsequent
rem  runs detect the existing venv and start instantly.
rem
rem  Requires Python 3.9+ available on PATH (the Windows installer's "py"
rem  launcher works too).
rem ============================================================================
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYW=%VENV_DIR%\Scripts\pythonw.exe"
set "STX_APP=%VENV_DIR%\Scripts\stx-app.exe"

if exist "%STX_APP%" (
    start "" "%STX_APP%"
    goto :eof
)

echo Setting up the virtual environment for the first run, please wait...
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 -m venv "%VENV_DIR%" || goto :py_missing
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% NEQ 0 goto :py_missing
    python -m venv "%VENV_DIR%" || goto :py_missing
)

call "%VENV_DIR%\Scripts\activate.bat"
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV_DIR%\Scripts\python.exe" -m pip install -e ".[gui]"
if errorlevel 1 (
    echo.
    echo Failed to install dependencies.  Please review the errors above.
    pause
    exit /b 1
)

start "" "%STX_APP%"
goto :eof

:py_missing
echo.
echo Python 3.9 or newer was not found on PATH.
echo Install it from https://www.python.org/downloads/ and re-run this launcher.
pause
exit /b 1
