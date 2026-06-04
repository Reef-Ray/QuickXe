@echo off
setlocal enableextensions
title QuickXe Installer

echo.
echo  ============================================
echo    QuickXe Installer
echo  ============================================
echo.

REM ---- Check Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo  [X] Python is not installed or not on PATH.
    echo.
    echo      Install Python 3.10+ from https://python.org
    echo      During install, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo  [1/4] Installing dependencies (PySide6, pyinstaller, pillow)...
echo        This includes Qt - first install is ~250MB, takes a few minutes.
echo.
python -m pip install --upgrade pip >nul
python -m pip install PySide6 pyinstaller pillow
if errorlevel 1 (
    echo.
    echo  [X] Failed to install dependencies. See errors above.
    pause
    exit /b 1
)

echo.
echo  [2/4] Building QuickXe (this takes ~1-2 minutes)...
echo.
python -m PyInstaller ^
    --onedir ^
    --windowed ^
    --name QuickXe ^
    --icon quickxe.ico ^
    --add-data "quickxe.ico;." ^
    --add-data "index.html;." ^
    --collect-submodules PySide6 ^
    --collect-data PySide6 ^
    --collect-binaries PySide6 ^
    --hidden-import PySide6.QtWebEngineWidgets ^
    --hidden-import PySide6.QtWebEngineCore ^
    --hidden-import PySide6.QtWebChannel ^
    --distpath dist ^
    --workpath build ^
    --noconfirm ^
    quickxe.py
if not exist "dist\QuickXe\QuickXe.exe" (
    echo.
    echo  [X] Build failed. See errors above.
    pause
    exit /b 1
)

echo.
echo  [3/4] Cleaning up build files...
if exist build rmdir /s /q build
if exist QuickXe.spec del /f /q QuickXe.spec

echo.
echo  [4/4] Creating desktop shortcut...
cscript //nologo create_shortcut.vbs /silent
if errorlevel 1 (
    echo  [!] Couldn't create the desktop shortcut. The exe is fine
    echo      though - it's at:  %CD%\dist\QuickXe.exe
)

echo.
echo  ============================================
echo    Done! QuickXe is installed.
echo  ============================================
echo.
echo    Launch it from the QuickXe icon on your desktop,
echo    or from:  %CD%\dist\QuickXe\QuickXe.exe
echo.
echo    Startup is now ~1-2 seconds (no more onefile unpacking).
echo    To remove it later, run uninstall.bat
echo.
pause
