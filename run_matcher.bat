@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
)

if not exist "%VENV_DIR%\Scripts\pip.exe" (
    echo [ERROR] pip was not found in the virtual environment.
    exit /b 1
)

echo [INFO] Installing or updating dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    exit /b 1
)

"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install project dependencies.
    exit /b 1
)

if "%~1"=="" (
    echo [INFO] No arguments provided. Showing help:
    "%PYTHON_EXE%" screen_template_matcher.py --help
    exit /b %errorlevel%
)

"%PYTHON_EXE%" screen_template_matcher.py %*
exit /b %errorlevel%
