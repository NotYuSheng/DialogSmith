@echo off
setlocal
rem Cross-platform setup for Windows (Linux/macOS users: run setup.sh).
rem Creates a venv, installs pinned dependencies, and processes your Telegram
rem export into a training-ready ShareGPT dataset.

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

echo [1/4] Creating virtual environment (venv)...
python -m venv venv
if errorlevel 1 (echo Failed to create virtual environment. & exit /b 1)

echo [2/4] Installing dependencies (this can take a while)...
call venv\Scripts\python -m pip install --upgrade pip
if errorlevel 1 (echo Failed to upgrade pip. & exit /b 1)
call venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (echo Failed to install dependencies. & exit /b 1)

echo [3/4] Preparing .env...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo       Created .env from .env.example - edit it to enable optional LLM validation.
)

echo [4/4] Processing Telegram export (data\result.json -^> data\chat_sharegpt.json)...
if not exist "data\result.json" (
    echo       data\result.json not found. Place your Telegram export there, then re-run.
    exit /b 1
)
call venv\Scripts\python -m ingest --source telegram
if errorlevel 1 (echo Failed to process Telegram export. & exit /b 1)

echo.
echo All steps completed successfully.
echo.
echo Next, activate the environment and launch training:
echo.
echo   venv\Scripts\activate
echo   llamafactory-cli train configs\train_lora.yaml
echo.
echo See README.md for export/merge and inference instructions.
pause
