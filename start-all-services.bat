@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  Enterprise Omni-Agent AI Platform — Windows Service Launcher
::  Run from project root: start-all-services.bat
::  Auto-installs missing dependencies before starting.
:: ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "BACKEND_DIR=%ROOT%\backend"
set "AGENT_DIR=%ROOT%\agent"
set "BACKEND_PYTHON=%BACKEND_DIR%\venv\Scripts\python.exe"
set "AGENT_PYTHON=%AGENT_DIR%\venv\Scripts\python.exe"

set "BACKEND_PORT=5000"
set "FRONTEND_PORT=3000"
set "MONGO_PORT=27017"

set "MONGODB_URL=mongodb://127.0.0.1:%MONGO_PORT%"
set "DATABASE_NAME=omni_agent_platform"
set "CORS_ORIGINS=https://localhost,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
set "VITE_PROXY_TARGET=http://127.0.0.1:%BACKEND_PORT%"

set "API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%"
set "REGISTRATION_KEY=reg_platformadmin123"
set "TENANT_ID=platform-admin"

:: ── TLS: generate a self-signed cert so Vite serves HTTPS (vite.config picks it
:: up automatically when certs\server.{key,crt} exist). Falls back to HTTP if
:: openssl is not installed.
set "CERT_DIR=%ROOT%\certs"
set "FRONTEND_SCHEME=http"
if exist "%CERT_DIR%\server.crt" if exist "%CERT_DIR%\server.key" set "FRONTEND_SCHEME=https"
if not "%FRONTEND_SCHEME%"=="https" (
    where openssl >nul 2>&1
    if not errorlevel 1 (
        if not exist "%CERT_DIR%" mkdir "%CERT_DIR%"
        openssl req -x509 -newkey rsa:2048 -nodes -keyout "%CERT_DIR%\server.key" -out "%CERT_DIR%\server.crt" -days 825 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >nul 2>&1
        if not errorlevel 1 set "FRONTEND_SCHEME=https"
    ) else (
        echo   !!  openssl not found - frontend stays HTTP ^(install openssl for HTTPS^)
    )
)
set "FRONTEND_URL=%FRONTEND_SCHEME%://localhost:%FRONTEND_PORT%"

cls
echo.
echo   ===================================================
echo    Enterprise Omni-Agent AI Platform
echo    Windows Service Launcher
echo   ===================================================
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
echo [0] Checking prerequisites...

python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   ERR Python not found in PATH.
    echo       Install Python 3.10+ from https://python.org and tick "Add to PATH".
    goto :error
)
echo   OK  Python found

node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   ERR Node.js not found in PATH.
    echo       Install Node.js from https://nodejs.org/
    goto :error
)
echo   OK  Node.js found

if not exist "%BACKEND_DIR%" (
    echo   ERR Backend directory not found: %BACKEND_DIR%
    goto :error
)

:: ── Backend venv ──────────────────────────────────────────────────────────────
if not exist "%BACKEND_PYTHON%" (
    echo   ... Backend venv missing - creating it now, first time takes ~60s...
    cd /d "%BACKEND_DIR%"
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo   ERR Failed to create backend venv.
        goto :error
    )
    echo   ... Installing backend dependencies...
    call "%BACKEND_DIR%\venv\Scripts\pip.exe" install --upgrade pip --quiet
    call "%BACKEND_DIR%\venv\Scripts\pip.exe" install -r "%BACKEND_DIR%\requirements.txt" --quiet
    if %ERRORLEVEL% neq 0 (
        echo   ERR pip install failed. Check requirements.txt and try again.
        goto :error
    )
    echo   OK  Backend venv ready
) else (
    echo   OK  Backend venv found
)

:: ── Frontend node_modules ─────────────────────────────────────────────────────
if not exist "%ROOT%\node_modules" (
    echo   ... node_modules missing - running npm install, first time takes ~30s...
    cd /d "%ROOT%"
    call npm install
    if %ERRORLEVEL% neq 0 (
        echo   ERR npm install failed.
        goto :error
    )
    echo   OK  node_modules ready
) else (
    echo   OK  node_modules found
)

:: ── Agent venv ────────────────────────────────────────────────────────────────
set "START_AGENT=0"
if exist "%AGENT_DIR%\agent.py" (
    if not exist "%AGENT_PYTHON%" (
        echo   ... Agent venv missing - creating it now...
        cd /d "%AGENT_DIR%"
        python -m venv venv
        if %ERRORLEVEL%==0 (
            call "%AGENT_DIR%\venv\Scripts\pip.exe" install --upgrade pip --quiet
            if exist "%AGENT_DIR%\requirements.txt" (
                call "%AGENT_DIR%\venv\Scripts\pip.exe" install -r "%AGENT_DIR%\requirements.txt" --quiet
            )
            echo   OK  Agent venv ready
            set "START_AGENT=1"
        ) else (
            echo   !!  Agent venv creation failed - agent will not be started
        )
    ) else (
        echo   OK  Agent venv found
        set "START_AGENT=1"
    )
) else (
    echo   !!  Agent directory missing - agent will not be started
)

echo   OK  All prerequisites satisfied
echo.

:: ── Clear stale processes ─────────────────────────────────────────────────────
echo [1] Clearing ports %BACKEND_PORT% and %FRONTEND_PORT%...
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R ":%BACKEND_PORT% " ^| findstr LISTENING') do (
    if "%%P" neq "0" taskkill /F /PID %%P >nul 2>&1
)
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R ":%FRONTEND_PORT% " ^| findstr LISTENING') do (
    if "%%P" neq "0" taskkill /F /PID %%P >nul 2>&1
)
echo   OK  Ports cleared
echo.

:: ── MongoDB ───────────────────────────────────────────────────────────────────
echo [2] Checking MongoDB on port %MONGO_PORT%...
netstat -ano 2>nul | findstr /R ":%MONGO_PORT% " | findstr LISTENING >nul 2>&1
if %ERRORLEVEL%==0 (
    echo   OK  MongoDB already running
) else (
    echo   ... Trying Windows MongoDB service...
    net start MongoDB >nul 2>&1
    timeout /t 3 /nobreak >nul
    netstat -ano 2>nul | findstr /R ":%MONGO_PORT% " | findstr LISTENING >nul 2>&1
    if %ERRORLEVEL%==0 (
        echo   OK  MongoDB service started
    ) else (
        echo   ... Service not available - trying mongod directly...
        if not exist "C:\data\db" mkdir "C:\data\db"
        start /min "mongod" mongod --dbpath "C:\data\db" --port %MONGO_PORT%
        timeout /t 5 /nobreak >nul
        netstat -ano 2>nul | findstr /R ":%MONGO_PORT% " | findstr LISTENING >nul 2>&1
        if %ERRORLEVEL% neq 0 (
            echo   ERR MongoDB could not be started.
            echo       Install MongoDB from https://www.mongodb.com/try/download/community
            echo       or start it manually, then re-run this script.
            goto :error
        )
        echo   OK  MongoDB started via mongod
    )
)
echo.

:: ── Backend ───────────────────────────────────────────────────────────────────
echo [3] Starting Backend ^(FastAPI on port %BACKEND_PORT%^)...
start "Omni-Backend :5000" /D "%BACKEND_DIR%" cmd /k ^
    "set MONGODB_URL=%MONGODB_URL%& set DATABASE_NAME=%DATABASE_NAME%& set CORS_ORIGINS=%CORS_ORIGINS%& set SUPER_ADMIN_PASSWORD=Admin@2030& set PLATFORM_URL=http://127.0.0.1:%BACKEND_PORT%& set TICKET_ATTACHMENT_DIR=%TEMP%\ticket_attachments& echo.& echo   Omni-Agent Backend  http://127.0.0.1:%BACKEND_PORT%& echo.& %BACKEND_PYTHON% -m uvicorn app:socket_app --host 0.0.0.0 --port %BACKEND_PORT% --log-level info"

echo   ... Waiting for backend to be ready (up to 90s)...
set /a TRIES=0
:wait_backend
    timeout /t 3 /nobreak >nul
    netstat -ano 2>nul | findstr /R ":%BACKEND_PORT% " | findstr LISTENING >nul 2>&1
    if %ERRORLEVEL%==0 goto :backend_up
    set /a TRIES+=1
    if %TRIES% lss 30 goto :wait_backend
    echo   ERR Backend did not start after 90s. Check the Backend terminal window.
    goto :error
:backend_up
echo   OK  Backend is up at http://127.0.0.1:%BACKEND_PORT%
echo.

:: ── Frontend ──────────────────────────────────────────────────────────────────
echo [4] Starting Frontend ^(Vite/React on port %FRONTEND_PORT%^)...
start "Omni-Frontend :3000" /D "%ROOT%" cmd /k ^
    "set VITE_PROXY_TARGET=%VITE_PROXY_TARGET% & echo. & echo   Omni-Agent Frontend  %FRONTEND_URL% & echo. & npm run dev -- --port %FRONTEND_PORT%"

echo   ... Waiting for frontend to compile (up to 60s)...
set /a TRIES=0
:wait_frontend
    timeout /t 3 /nobreak >nul
    netstat -ano 2>nul | findstr /R ":%FRONTEND_PORT% " | findstr LISTENING >nul 2>&1
    if %ERRORLEVEL%==0 goto :frontend_up
    set /a TRIES+=1
    if %TRIES% lss 20 goto :wait_frontend
    echo   !!  Frontend did not respond - check the Frontend terminal window.
    goto :summary
:frontend_up
echo   OK  Frontend is up at %FRONTEND_URL%
echo.

:: ── Agent ─────────────────────────────────────────────────────────────────────
if "%START_AGENT%"=="1" (
    echo [5] Starting Agent...
    start "Omni-Agent" /D "%AGENT_DIR%" cmd /k ^
        "set API_BASE_URL=%API_BASE_URL%& set REGISTRATION_KEY=%REGISTRATION_KEY%& set TENANT_ID=%TENANT_ID%& set MONGODB_URL=%MONGODB_URL%& set DATABASE_NAME=%DATABASE_NAME%& echo.& echo   Agent connecting to %API_BASE_URL%& echo.& %AGENT_PYTHON% agent.py --url %API_BASE_URL% --key %REGISTRATION_KEY%"
    echo   OK  Agent launched
    echo.
)

:: ── Summary ───────────────────────────────────────────────────────────────────
:summary
echo.
echo   ===================================================
echo    All services started!
echo   ===================================================
echo.
echo   Service URLs:
echo     Frontend   %FRONTEND_URL%
echo     Backend    http://127.0.0.1:%BACKEND_PORT%
echo     API Docs   http://127.0.0.1:%BACKEND_PORT%/docs
echo     Health     http://127.0.0.1:%BACKEND_PORT%/health
echo.
echo   Default login:  super@omni.ai  /  Admin@2030
echo.
echo   To stop all services:
echo     taskkill /F /IM python.exe /IM node.exe
echo.

set /p OPEN_BROWSER="  Open browser now? (Y/N): "
if /i "%OPEN_BROWSER%"=="Y" (
    start %FRONTEND_URL%
)

goto :eof

:error
echo.
echo   Script aborted. Fix the issue above and re-run.
echo.
pause
exit /b 1
