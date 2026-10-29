@echo off
setlocal
REM ============================================================
REM  AutoOps - dev mode
REM  backend  : http://127.0.0.1:8000  (FastAPI, hot reload off)
REM  frontend : http://localhost:5173  (Vite HMR)
REM  For production single-process mode use start-prod.bat
REM ============================================================

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\backend\venv\Scripts\activate.bat" (
    echo [error] Python venv not found: %ROOT%\backend\venv
    echo.
    echo   Run these first:
    echo       cd /d "%ROOT%\backend"
    echo       python -m venv venv
    echo       venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\frontend\node_modules" (
    echo [error] frontend dependencies not installed.
    echo         Run: cd /d "%ROOT%\frontend" ^&^& npm install
    pause
    exit /b 1
)

echo [1/2] Starting backend on http://127.0.0.1:8000 ...
start "AutoOps Backend" cmd /k "cd /d "%ROOT%\backend" && call venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [2/2] Starting frontend on http://localhost:5173 ...
start "AutoOps Frontend" cmd /k "cd /d "%ROOT%\frontend" && npm run dev"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://localhost:5173
echo Login:    admin / admin123
pause
