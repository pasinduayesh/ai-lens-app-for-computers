@echo off
title ScreenLens AI - Setup Ollama Assistant
color 0B

echo ============================================================
echo      ScreenLens AI - Ollama & Model Setup Helper
echo ============================================================
echo.

:: 1. Check if Ollama is installed
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Ollama is not installed on this computer.
    echo.
    echo [*] Opening the official Ollama download page in your browser...
    start https://ollama.com/download/OllamaSetup.exe
    echo.
    echo ------------------------------------------------------------
    echo INSTRUCTIONS:
    echo 1. Install Ollama from the downloaded OllamaSetup.exe.
    echo 2. Once installed, run this batch file again to automatically
    echo    download the "gemma4:31b-cloud" model.
    echo ------------------------------------------------------------
    echo.
    pause
    exit /b
)

:: 2. Ollama is found - pull the model
echo [*] Ollama is installed!
echo [*] Pulling AI model: gemma4:31b-cloud...
echo (Depending on your internet speed, this may take a few minutes...)
echo.

ollama run gemma4:31b-cloud

echo.
echo ============================================================
echo   [SUCCESS] Ollama and gemma4:31b-cloud are ready!
echo ============================================================
echo.
echo ScreenLens AI is now fully equipped for:
echo   - AI Chat & Streaming Answers
echo   - Sinhala Text Vision Extraction
echo   - Contextual Screen Analysis
echo.
pause
