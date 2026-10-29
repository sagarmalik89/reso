@echo off
TITLE Build Standalone Windows Executable - Printer Agent
COLOR 0B
cd /d "%~dp0"

echo ================================================================
echo       PRINTER AGENT - BUILD STANDALONE EXECUTABLE (.EXE)
echo ================================================================
echo.

:: Detect Python executable
set "PYTHON_EXE="

if exist "C:\Python314\python.exe" (
    set "PYTHON_EXE=C:\Python314\python.exe"
    goto :PYTHON_FOUND
)

python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_EXE=python"
    goto :PYTHON_FOUND
)

py -3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_EXE=py -3"
    goto :PYTHON_FOUND
)

:PYTHON_NOT_FOUND
echo [ERROR] Python is not found!
echo Please install Python 3.10+ and check "Add Python to PATH".
pause
exit /b 1

:PYTHON_FOUND
echo [INFO] Using Python: %PYTHON_EXE%
echo.

echo [1/3] Installing build dependencies (pystray, pyinstaller, pillow)...
%PYTHON_EXE% -m pip install pystray pyinstaller pillow pywin32 --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Pip encountered an issue installing packages. Attempting build anyway...
)

echo.
echo [2/3] Compiling PrinterAgent.exe with PyInstaller...
%PYTHON_EXE% build_exe.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build failed! Check the log output above.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo [3/3] BUILD COMPLETE!
echo Output folder: release\
echo Executable   : release\PrinterAgent.exe
echo ================================================================
echo.

explorer.exe release\
pause
