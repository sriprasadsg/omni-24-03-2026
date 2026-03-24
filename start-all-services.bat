@echo off
REM Enterprise Omni-Agent Platform - Service Launcher (Windows Batch)
REM Alternative batch file version for systems where PowerShell execution is restricted

echo =============================================
echo Enterprise Omni-Agent Platform - Launcher
echo =============================================
echo.

set PROJECT_ROOT=d:\Downloads\enterprise-omni-agent-ai-platform

if not exist "%PROJECT_ROOT%" (
    echo ERROR: Project directory not found at %PROJECT_ROOT%
    echo Please update the PROJECT_ROOT variable in this script.
    pause
    exit /b 1
)

echo Starting services...
echo.

REM 1. Launch Backend
echo [1/3] Starting Backend (Port 5000)...
start "Backend Server" /D "%PROJECT_ROOT%\backend" cmd /k "venv\Scripts\python.exe -m uvicorn app:app --port 5000 --host 0.0.0.0"
echo   Backend launched in new window
timeout /t 2 /nobreak >nul

REM 2. Launch Frontend
echo [2/3] Starting Frontend (Port 3000)...
start "Frontend Server" /D "%PROJECT_ROOT%" cmd /k "npm run dev"
echo   Frontend launched in new window
timeout /t 2 /nobreak >nul

REM 3. Launch Agent
echo [3/3] Starting Agent...
start "Agent" /D "%PROJECT_ROOT%\agent" cmd /k "%PROJECT_ROOT%\agent\venv\Scripts\python.exe agent.py"
echo   Agent launched in new window
timeout /t 1 /nobreak >nul

echo.
echo =============================================
echo All services started!
echo =============================================
echo.
echo Service URLs:
echo   Frontend:  http://127.0.0.1:3000
echo   Backend:   http://127.0.0.1:5000
echo   Health:    http://127.0.0.1:5000/health
echo.
echo IMPORTANT: Wait 60-90 seconds for:
echo   1. Backend to fully initialize
echo   2. Frontend to compile and start
echo   3. Agent to complete first compliance scan
echo.
echo To test Phase 1 compliance features:
echo   1. Wait 90 seconds
echo   2. Open http://localhost:3000 in your browser
echo   3. Navigate to: Agents - EILT0197 - Compliance Tab
echo   4. Verify you see 28-36 compliance checks
echo.
echo To stop all services:
echo   - Close all 3 command windows that were opened
echo.

set /p OPEN_BROWSER="Open browser automatically after 90 seconds? (Y/N): "

if /i "%OPEN_BROWSER%"=="Y" (
    echo.
    echo Waiting 90 seconds for services to initialize...
    timeout /t 90 /nobreak
    echo.
    echo Opening browser...
    start http://127.0.0.1:3000
    echo.
    echo Browser opened! You should now be able to test the compliance features.
) else (
    echo.
    echo Remember to wait 90 seconds before opening http://127.0.0.1:3000
)

echo.
pause
