@echo off
echo ===================================================
echo SORTING STATION - Windows Setup
echo ===================================================

echo [1] Checking for Python...
python --version
IF %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in PATH!
    pause
    exit /b 1
)

echo [2] Creating virtual environment...
python -m venv .venv
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to create virtual environment!
    pause
    exit /b 1
)

echo [3] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [4] Installing dependencies...
pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies!
    pause
    exit /b 1
)

echo [5] Setting up environment variables...
IF NOT EXIST ".env" (
    echo Copying .env.example to .env
    copy .env.example .env
) ELSE (
    echo .env file already exists, skipping copy.
)

echo ===================================================
echo SETUP COMPLETE!
echo ===================================================
echo To start the project, run:
echo call .venv\Scripts\activate.bat
echo python main.py
echo ===================================================
pause
