@echo off
REM Windows launcher: bootstraps .venv, runs the CLI wizard on first run,
REM then launches the tray app with pythonw (no console window).
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    call :find_python PY_CMD
    if not defined PY_CMD (
        echo.
        echo ERROR: No suitable Python found.
        echo Install Python 3.10-3.13 from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" in the installer.
        pause
        exit /b 1
    )

    echo Using Python: !PY_CMD!
    !PY_CMD! --version

    if exist ".venv" (
        echo Removing previous .venv ...
        rmdir /s /q ".venv"
    )

    echo Creating virtual environment in .venv ...
    !PY_CMD! -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo ERROR: .venv\Scripts\python.exe was not created.
        if exist ".venv\bin\python.exe" (
            echo Your Python built a Unix-style venv ^(bin/ instead of Scripts/^).
            echo This happens with MSYS2/MinGW Python on Windows.
            echo Install standard Windows Python from https://www.python.org/downloads/
        ) else (
            echo The interpreter may be a Microsoft Store stub or broken install.
            echo Install real Python from https://www.python.org/downloads/ and tick "Add to PATH".
        )
        pause
        exit /b 1
    )

    echo Installing dependencies ^(first run only, takes ~1 minute^)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 (echo ERROR: pip upgrade failed & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: pip install failed. See output above.
        pause
        exit /b 1
    )
    echo Setup complete.
)

if not exist "config.yaml" (
    echo.
    ".venv\Scripts\python.exe" -m src.wizard
    if errorlevel 1 (
        echo Wizard cancelled. You can rerun this launcher any time.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:find_python
REM Search common locations for a Windows-compatible Python, in order of
REM preference. Sets the named variable to a callable command, or leaves it
REM undefined if none found.
setlocal EnableDelayedExpansion
set "FOUND="

REM 1. py launcher (official python.org installer installs this)
where py >nul 2>&1 && set "FOUND=py -3"

REM 2. Anaconda / Miniconda base env in this user's profile
if not defined FOUND if exist "%USERPROFILE%\anaconda3\python.exe" set "FOUND=""%USERPROFILE%\anaconda3\python.exe"""
if not defined FOUND if exist "%USERPROFILE%\miniconda3\python.exe" set "FOUND=""%USERPROFILE%\miniconda3\python.exe"""

REM 3. System-wide Anaconda / Miniconda
if not defined FOUND if exist "C:\ProgramData\anaconda3\python.exe" set "FOUND=""C:\ProgramData\anaconda3\python.exe"""
if not defined FOUND if exist "C:\ProgramData\miniconda3\python.exe" set "FOUND=""C:\ProgramData\miniconda3\python.exe"""

REM 4. Plain `python` on PATH (validated later by checking venv layout)
if not defined FOUND where python >nul 2>&1 && set "FOUND=python"

endlocal & set "%~1=%FOUND%"
exit /b 0
