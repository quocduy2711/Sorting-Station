#!/bin/bash
echo "==================================================="
echo "SORTING STATION - Linux/Mac Setup"
echo "==================================================="

echo "[1] Checking for Python..."
if ! command -v python3 &> /dev/null
then
    echo "python3 is not installed or not in PATH!"
    exit 1
fi

echo "[2] Creating virtual environment..."
python3 -m venv .venv
if [ $? -ne 0 ]; then
    echo "Failed to create virtual environment!"
    exit 1
fi

echo "[3] Activating virtual environment..."
source .venv/bin/activate

echo "[4] Installing dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies!"
    exit 1
fi

echo "[5] Setting up environment variables..."
if [ ! -f .env ]; then
    echo "Copying .env.example to .env"
    cp .env.example .env
else
    echo ".env file already exists, skipping copy."
fi

echo "==================================================="
echo "SETUP COMPLETE!"
echo "==================================================="
echo "To start the project, run:"
echo "source .venv/bin/activate"
echo "python main.py"
echo "==================================================="
