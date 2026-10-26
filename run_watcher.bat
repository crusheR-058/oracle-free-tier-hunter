@echo off
setlocal enabledelayedexpansion

echo =======================================================================
echo          ORACLE FREE-TIER HUNTER - WINDOWS LAUNCHER
echo =======================================================================
echo.

:: Check Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from python.org or Microsoft Store.
    pause
    exit /b 1
)

:: Check if virtualenv or requirements needed
if not exist "config.yaml" (
    echo [INFO] config.yaml not found. Copying config.example.yaml to config.yaml...
    copy config.example.yaml config.yaml
    echo [INFO] config.yaml created with default WATCH_ONLY mode.
)

:: Run Hunter CLI
echo [INFO] Starting Oracle Free-Tier Hunter...
python main.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Process exited with error code %ERRORLEVEL%.
    pause
)
