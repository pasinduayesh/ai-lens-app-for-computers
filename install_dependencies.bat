@echo off
title ScreenLens AI - One-Click Installer
color 0B

echo ============================================================
echo      ScreenLens AI - Dependency installer for Windows 11
echo ============================================================
echo.

:: Check if Python is installed
echo [*] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to system PATH!
    echo Please install Python (version 3.10 or higher recommended) from python.org
    echo IMPORTANT: Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b
)

:: Display Python version
for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
echo [SUCCESS] Found %PYVER%
echo.

:: Install pip requirements
echo [*] Installing required python components from requirements.txt...
echo This will install PyQt6, EasyOCR, Pillow, MSS, and keyboard libraries.
echo (EasyOCR requires PyTorch, so downloading may take a few minutes...)
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Dependency installation failed! 
    echo Please check your internet connection or run the terminal as Administrator.
    echo.
    pause
    exit /b
)

echo.
echo ============================================================
echo    [SUCCESS] All Dependencies Installed Successfully!
echo ============================================================
echo.
echo Next Steps:
echo 1. Ensure Ollama is installed on this laptop (from ollama.com).
echo 2. In a terminal, pull the required AI model:
echo    ollama pull gemma4:31b-cloud
echo 3. Run ScreenLens AI:
echo    python app.py
echo.
pause
