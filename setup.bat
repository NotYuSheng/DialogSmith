@echo off
setlocal enabledelayedexpansion

rem Set base directory to location of this script
set "BASE_DIR=%cd%\"

echo [1/6] Creating virtual environment...
python -m venv "%BASE_DIR%venv"
if errorlevel 1 (
    echo Failed to create virtual environment. Aborting.
    exit /b 1
)

echo [2/6] Activating virtual environment...
call "%BASE_DIR%venv\Scripts\activate"
if errorlevel 1 (
    echo Failed to activate virtual environment. Aborting.
    exit /b 1
)

echo [3/6] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip. Aborting.
    exit /b 1
)

echo [4/6] Cloning LLaMA-Factory...
if exist "%BASE_DIR%LLaMA-Factory" (
    echo LLaMA-Factory directory already exists. Skipping clone...
) else (
    git clone https://github.com/hiyouga/LLaMA-Factory.git "%BASE_DIR%LLaMA-Factory"
    if errorlevel 1 (
        echo Failed to clone LLaMA-Factory. Aborting.
        exit /b 1
    )
)

echo [5/6] Installing LLaMA-Factory dependencies...
pip install -r "%BASE_DIR%LLaMA-Factory\requirements.txt"
if errorlevel 1 (
    echo Failed to install LLaMA-Factory dependencies. Aborting.
    exit /b 1
)

echo [6/6] Patching dataset_info.json with chat_sharegpt entry...

set "INFO_FILE=%BASE_DIR%LLaMA-Factory\data\dataset_info.json"

:: Exit if file is missing
if not exist "%INFO_FILE%" (
    echo dataset_info.json not found at %INFO_FILE%
    exit /b 1
)

:: Check if already patched
findstr /C:"\"chat_sharegpt\"" "%INFO_FILE%" >nul
if not errorlevel 1 (
    echo chat_sharegpt entry already exists. Skipping patch.
    goto :eof
)

:: Patch file
powershell -Command ^
  "$path = '%INFO_FILE%';" ^
  "$lines = Get-Content $path;" ^
  "$lines = $lines[0..($lines.Count - 3)];" ^
  "$lines += '  },';" ^
  "$lines += '  \"chat_sharegpt\": {';" ^
  "$lines += '    \"file_name\": \"../../data/chat_sharegpt.json\",';" ^
  "$lines += '    \"formatting\": \"sharegpt\",';" ^
  "$lines += '    \"columns\": {';" ^
  "$lines += '      \"messages\": \"conversations\"';" ^
  "$lines += '    },';" ^
  "$lines += '    \"tags\": {';" ^
  "$lines += '      \"role_tag\": \"from\",';" ^
  "$lines += '      \"content_tag\": \"value\",';" ^
  "$lines += '      \"user_tag\": \"user\",';" ^
  "$lines += '      \"assistant_tag\": \"assistant\"';" ^
  "$lines += '    }';" ^
  "$lines += '  }';" ^
  "$lines += '}';" ^
  "Set-Content -Path $path -Value $lines"

if errorlevel 1 (
    echo Failed to patch dataset_info.json
    exit /b 1
)

echo dataset_info.json patched successfully.

echo.
echo 🧠 Running Telegram export processors...
python "%BASE_DIR%scripts\telegram_extract.py"
if errorlevel 1 (
    echo Failed to run telegram_extract.py. Aborting.
    exit /b 1
)

python "%BASE_DIR%scripts\convert_to_sharegpt.py"
if errorlevel 1 (
    echo Failed to run convert_to_sharegpt.py. Aborting.
    exit /b 1
)

echo.
echo All steps completed successfully.

echo.
echo Please refer to the README.md for the next steps.
echo You will find instructions on how to launch training.

pause
