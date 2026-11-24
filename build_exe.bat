@echo off
title ScreenLens AI - Folder Directory EXE Builder
color 0D

echo ============================================================
echo   ScreenLens AI - PyInstaller One-Folder (Instant Open)
echo ============================================================
echo.

:: Verify PyInstaller
echo [*] Checking PyInstaller installation...
python -m pip install pyinstaller

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyInstaller packaging tool.
    pause
    exit /b
)

echo.
echo [*] Compiling ScreenLens AI into a pre-decompressed folder (dist\ScreenLens_AI)...
echo This will allow the application to open INSTANTLY (under 500ms) upon double-click.
echo (Since PyTorch/EasyOCR are large libraries, compilation may take 1-3 minutes...)
echo.

:: Run PyInstaller to build a pre-decompressed directory structure
:: --onedir compiles into a folder (which avoids start-up decompression lag)
:: --noconsole prevents the command prompt window from popping up behind the GUI
python -m PyInstaller --noconsole --onedir --noconfirm --name="ScreenLens_AI" app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Folder compilation failed!
    echo Please make sure app.py is in the workspace and not running in the background.
    echo.
    pause
    exit /b
)

echo.
echo ============================================================
echo   [SUCCESS] Folder Directory Compilation Completed Successfully!
echo ============================================================
echo.
echo Your instant-open standalone folder is located inside "dist":
echo PATH: .\dist\ScreenLens_AI\
echo.
echo You can run the application instantly using:
echo .\dist\ScreenLens_AI\ScreenLens_AI.exe
echo.
echo To share: Simply zip the "ScreenLens_AI" folder and send it!
echo.
pause
