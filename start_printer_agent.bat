@echo off
TITLE Printer Agent & Web Counter Portal
COLOR 0A
cd /d "%~dp0"

echo ================================================================
echo           PRINTER AGENT - COUNTER & WEB PORTAL
echo ================================================================
echo.

:: Detect Python executable
set "PYTHON_EXE="

:: 1. Check C:\Python314\python.exe
if exist "C:\Python314\python.exe" (
    set "PYTHON_EXE=C:\Python314\python.exe"
    goto :PYTHON_FOUND
)

:: 2. Check standard python command
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_EXE=python"
    goto :PYTHON_FOUND
)

:: 3. Check Windows py launcher
py -3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_EXE=py -3"
    goto :PYTHON_FOUND
)

:PYTHON_NOT_FOUND
echo [ERROR] Python is not found!
echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
pause
exit /b 1

:PYTHON_FOUND
echo [INFO] Using Python: %PYTHON_EXE%

:: Ensure dependencies are installed
echo.
echo [1/3] Verifying dependencies...
%PYTHON_EXE% -m pip install -r requirements.txt --quiet

:: Start the Web Portal & Printer Agent
echo.
echo [2/3] Starting Printer Agent Web Server...
echo ----------------------------------------------------------------
echo   Operator Dashboard: http://localhost:8000
echo   Admin Login Email : admin@printagent.com
echo   Admin Password    : admin123
echo ----------------------------------------------------------------
echo.
echo [3/3] Launching portal on all local network interfaces...
%PYTHON_EXE% main.py web --port 8000 --shop counter-1

pause
