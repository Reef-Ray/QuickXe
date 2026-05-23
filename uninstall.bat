@echo off
setlocal enableextensions
title QuickXe Uninstaller

echo.
echo  ============================================
echo    QuickXe Uninstaller
echo  ============================================
echo.
echo  This will remove:
echo    - The QuickXe shortcut from your Desktop
echo    - The built QuickXe.exe (dist\ and build\ folders)
echo    - Saved settings and covers at %%APPDATA%%\QuickXe
echo.
echo  Your game files are NEVER touched - only QuickXe's own data.
echo  Source files in this folder are kept so you can rebuild later.
echo  To remove those too, just delete this folder afterward.
echo.

set /p CONFIRM="Continue? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo  Cancelled.
    pause
    exit /b 0
)

echo.

REM ---- 1. Desktop shortcut ----
echo  [1/3] Removing desktop shortcut...
set "SHORTCUT=%USERPROFILE%\Desktop\QuickXe.lnk"
if exist "%SHORTCUT%" (
    del /f /q "%SHORTCUT%"
    echo        Removed: %SHORTCUT%
) else (
    echo        No shortcut found - skipping.
)
set "ONEDRIVE_SHORTCUT=%USERPROFILE%\OneDrive\Desktop\QuickXe.lnk"
if exist "%ONEDRIVE_SHORTCUT%" (
    del /f /q "%ONEDRIVE_SHORTCUT%"
    echo        Removed: %ONEDRIVE_SHORTCUT%
)

REM ---- 2. Built exe + build artifacts ----
echo.
echo  [2/3] Removing build artifacts...
if exist "dist" (
    rmdir /s /q "dist"
    echo        Removed: dist\
) else (
    echo        No dist folder - skipping.
)
if exist "build" (
    rmdir /s /q "build"
    echo        Removed: build\
)
if exist "QuickXe.spec" (
    del /f /q "QuickXe.spec"
    echo        Removed: QuickXe.spec
)

REM ---- 3. Saved config + covers in AppData ----
echo.
echo  [3/3] Removing saved settings and covers...
if exist "%APPDATA%\QuickXe" (
    rmdir /s /q "%APPDATA%\QuickXe"
    echo        Removed: %APPDATA%\QuickXe
) else (
    echo        No saved settings - skipping.
)

echo.
echo  ============================================
echo    Uninstall complete.
echo  ============================================
echo.
echo    Source files are still in:  %CD%
echo    Delete this whole folder to remove them too.
echo.
pause
