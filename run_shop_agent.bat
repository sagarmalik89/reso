@echo off
TITLE Shop Local Printer Connector - Printer Agent
COLOR 0B
cd /d "%~dp0"

:: Auto-detect python
set "PYTHON_EXE="
if exist "C:\Python314\python.exe" set "PYTHON_EXE=C:\Python314\python.exe"
if not defined PYTHON_EXE (
    python --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    py -3 --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "PYTHON_EXE=py -3"
)
if not defined PYTHON_EXE (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

:: Read configuration or defaults
set "PORTAL_URL=http://localhost:8000"
set "SHOP_ID=counter-1"
set "API_KEY="

if exist "shop_config.txt" (
    for /f "tokens=1,2 delims==" %%a in (shop_config.txt) do (
        if "%%a"=="PORTAL_URL" set "PORTAL_URL=%%b"
        if "%%a"=="SHOP_ID" set "SHOP_ID=%%b"
        if "%%a"=="API_KEY" set "API_KEY=%%b"
    )
)

:MENU
cls
echo ================================================================
echo        🖨️  PRINTER AGENT - LOCAL SHOP CONNECTOR
echo ================================================================
echo   Shop ID      : %SHOP_ID%
echo   Portal Server: %PORTAL_URL%
echo ================================================================
echo.
echo   [1] Start Live Print Agent (Auto-Print Incoming Orders)
echo   [2] Print Test Page (Verify Physical Printer Connection)
echo   [3] List Detected Windows Printers
echo   [4] Configure Shop ID / Server URL
echo   [5] Exit
echo.
set /p CHOICE="Choose an option [1-5]: "

if "%CHOICE%"=="1" goto :START_AGENT
if "%CHOICE%"=="2" goto :TEST_PRINT
if "%CHOICE%"=="3" goto :LIST_PRINTERS
if "%CHOICE%"=="4" goto :CONFIGURE
if "%CHOICE%"=="5" exit /b 0
goto :MENU

:START_AGENT
cls
echo Starting Shop Print Agent for %SHOP_ID%...
%PYTHON_EXE% -m printer_agent.shop_client --server "%PORTAL_URL%" --shop "%SHOP_ID%" --key "%API_KEY%"
pause
goto :MENU

:TEST_PRINT
cls
echo Sending test page to physical printer...
%PYTHON_EXE% -m printer_agent.shop_client --server "%PORTAL_URL%" --shop "%SHOP_ID%" --key "%API_KEY%" --test-print
pause
goto :MENU

:LIST_PRINTERS
cls
%PYTHON_EXE% main.py printers
pause
goto :MENU

:CONFIGURE
cls
echo Configure Shop Agent Connection:
set /p NEW_SHOP="Enter your Shop ID (e.g. counter-1 or malik-cafe): "
if not "%NEW_SHOP%"=="" set "SHOP_ID=%NEW_SHOP%"
set /p NEW_URL="Enter Server URL (default: http://localhost:8000): "
if not "%NEW_URL%"=="" set "PORTAL_URL=%NEW_URL%"
set /p NEW_KEY="Enter Shop API Key (from Dashboard): "
if not "%NEW_KEY%"=="" set "API_KEY=%NEW_KEY%"

(
echo PORTAL_URL=%PORTAL_URL%
echo SHOP_ID=%SHOP_ID%
echo API_KEY=%API_KEY%
) > shop_config.txt

echo.
echo ✅ Settings saved to shop_config.txt!
pause
goto :MENU
